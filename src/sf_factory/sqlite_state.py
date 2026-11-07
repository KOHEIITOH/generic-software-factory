"""Optional SQLite cache of external Issues, with no independent Task table."""
from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from sf_factory.issue_reference import IssueSnapshot
from sf_factory.state_store import StateConflict, StateCorrupt, StateNotFound, StateUnavailable


class SqliteIssueStore:
    def __init__(self, database: Path):
        self.database = database
        if any((database.parent / name).exists() for name in
               ('tasks-v1', 'dashboard-v1', 'issues-v2', 'dashboard-v2')):
            raise StateConflict('use a separate root; existing File state is not migrated')
        with self._connect() as db:
            tables = {row['name'] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            if tables & {'tasks', 'task_sources', 'task_repositories', 'task_projects'}:
                raise StateConflict('Legacy Task data is unsupported; use a fresh state root')
            if 'issues' in tables:
                columns = {row['name'] for row in db.execute('PRAGMA table_info(issues)')}
                if columns != {'issue_key', 'provider', 'instance', 'external_id',
                               'prompt', 'external_url', 'observed_at'}:
                    raise StateConflict('Unsupported Issue schema; use a fresh state root')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS issues (
                    issue_key TEXT PRIMARY KEY, provider TEXT NOT NULL, instance TEXT NOT NULL,
                    external_id TEXT NOT NULL, prompt TEXT NOT NULL, external_url TEXT,
                    observed_at TEXT NOT NULL, UNIQUE(provider,instance,external_id)
                );
                CREATE TABLE IF NOT EXISTS audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT,
                    issue_key TEXT NOT NULL, event TEXT NOT NULL, at TEXT NOT NULL
                );
            ''')

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = None
        try:
            db = sqlite3.connect(self.database, timeout=10)
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA foreign_keys=ON')
            with db:
                yield db
        except sqlite3.Error as exc:
            raise StateUnavailable('SQLite Issue operation failed') from exc
        finally:
            if db is not None:
                db.close()

    def get_issue(self, issue_key: str) -> IssueSnapshot:
        with self._connect() as db:
            row = db.execute('SELECT * FROM issues WHERE issue_key=?', (issue_key,)).fetchone()
        if row is None:
            raise StateNotFound('issue not found')
        value = dict(row)
        key = value.pop('issue_key')
        try:
            issue = IssueSnapshot(**value)
            if issue.key != key:
                raise ValueError('Issue reference mismatch')
            return issue
        except (ValueError, TypeError) as exc:
            raise StateCorrupt('invalid Issue snapshot') from exc

    def import_issue(self, *, provider: str, instance: str, external_id: str,
                     prompt: str, external_url: str | None = None) -> str:
        issue = IssueSnapshot(provider, instance, external_id, prompt, external_url,
                              datetime.now(UTC).isoformat())
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute('SELECT * FROM issues WHERE issue_key=?', (issue.key,)).fetchone()
            if existing and (existing['provider'], existing['instance'],
                             existing['external_id']) != (
                    provider, instance, external_id):
                raise StateConflict('Issue reference key collision')
            if (existing and existing['prompt'] == prompt
                    and existing['external_url'] == external_url):
                return issue.key
            db.execute('''INSERT INTO issues VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(issue_key) DO UPDATE SET prompt=excluded.prompt,
                external_url=excluded.external_url,observed_at=excluded.observed_at''',
                (issue.key, provider, instance, external_id, prompt, external_url,
                 issue.observed_at))
            db.execute('INSERT INTO audit(run_id,issue_key,event,at) VALUES (NULL,?,?,?)',
                       (issue.key, 'issue.observed', issue.observed_at))
        return issue.key
