"""Legacy compatibility and transactional rollback for the optional SQLite adapter."""
import sqlite3

import pytest

from sf_factory.factory import Factory
from sf_factory.sqlite_state import SqliteStateStore
from sf_factory.state_store import StateUnavailable


def test_existing_task_ids_and_schema_are_preserved(tmp_path):
    path = tmp_path / 'factory.sqlite3'
    store = SqliteStateStore(path)
    with sqlite3.connect(path) as db:
        db.execute('INSERT INTO tasks VALUES (?,?,?)', ('legacy-id', 'legacy prompt', 'old-time'))
    assert store.get_task('legacy-id').id == 'legacy-id'
    assert Factory(tmp_path).show_task('legacy-id')['task']['created_at'] == 'old-time'


def test_import_rollback_does_not_leave_partial_task(tmp_path):
    path = tmp_path / 'factory.sqlite3'
    store = SqliteStateStore(path)
    with sqlite3.connect(path) as db:
        db.execute("CREATE TRIGGER fail_audit BEFORE INSERT ON audit "
                   "BEGIN SELECT RAISE(ABORT, 'simulated failure'); END")
    with pytest.raises(StateUnavailable):
        store.import_external_task(
            provider='github', instance='a/b', external_id='1', prompt='task',
        )
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM task_sources').fetchone()[0] == 0


def test_reimport_records_single_audit_event(tmp_path):
    path = tmp_path / 'factory.sqlite3'
    store = SqliteStateStore(path)
    for _ in range(2):
        store.import_external_task(
            provider='github', instance='a/b', external_id='1', prompt='task',
        )
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT event FROM audit').fetchall() == [('task.imported',)]
