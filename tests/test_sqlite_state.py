"""Legacy compatibility and transactional rollback for the optional SQLite adapter."""
import sqlite3

import pytest

from sf_factory.factory import Factory
from sf_factory.sqlite_state import SqliteIssueStore
from sf_factory.state_store import StateConflict, StateUnavailable


def test_legacy_task_database_is_rejected_without_deleting_data(tmp_path):
    path = tmp_path / 'factory.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE tasks (id TEXT PRIMARY KEY,prompt TEXT,created_at TEXT)')
        db.execute("INSERT INTO tasks VALUES ('legacy-id','keep original','old-time')")
    for open_store in (lambda: SqliteIssueStore(path), lambda: Factory(tmp_path)):
        with pytest.raises(StateConflict, match='Legacy Task data'):
            open_store()
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT * FROM tasks').fetchall() == [
            ('legacy-id', 'keep original', 'old-time')]
        assert db.execute("SELECT name FROM sqlite_master WHERE name='issues'").fetchall() == []


def test_import_rollback_does_not_leave_partial_task(tmp_path):
    path = tmp_path / 'factory.sqlite3'
    store = SqliteIssueStore(path)
    with sqlite3.connect(path) as db:
        db.execute("CREATE TRIGGER fail_audit BEFORE INSERT ON audit "
                   "BEGIN SELECT RAISE(ABORT, 'simulated failure'); END")
    with pytest.raises(StateUnavailable):
        store.import_issue(
            provider='github', instance='a/b', external_id='1', prompt='issue',
        )
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT COUNT(*) FROM issues').fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM audit').fetchone()[0] == 0


def test_reimport_records_single_audit_event(tmp_path):
    path = tmp_path / 'factory.sqlite3'
    store = SqliteIssueStore(path)
    for _ in range(2):
        store.import_issue(
            provider='github', instance='a/b', external_id='1', prompt='issue',
        )
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT event FROM audit').fetchall() == [('issue.observed',)]
