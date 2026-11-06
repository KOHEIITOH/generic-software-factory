"""SQLite implementation of the initial task-state contract; legacy schema compatible."""
from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from sf_factory.state_store import (
    StateNotFound,
    StateUnavailable,
    TaskRecord,
    validate_external,
    validate_prompt,
)


class SqliteStateStore:
    def __init__(self, database: Path):
        self.database = database
        with self._connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY, prompt TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS task_sources (
                    task_id TEXT PRIMARY KEY REFERENCES tasks(id),
                    provider TEXT NOT NULL, instance TEXT NOT NULL,
                    external_id TEXT NOT NULL, external_url TEXT,
                    UNIQUE(provider, instance, external_id)
                );
                CREATE TABLE IF NOT EXISTS audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT,
                    task_id TEXT NOT NULL, event TEXT NOT NULL, at TEXT NOT NULL
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
            raise StateUnavailable('SQLite state operation failed') from exc
        finally:
            if db is not None:
                db.close()

    def create_task(self, prompt: str) -> str:
        validate_prompt(prompt)
        task_id, at = uuid.uuid4().hex, datetime.now(UTC).isoformat()
        with self._connect() as db:
            db.execute('INSERT INTO tasks(id,prompt,created_at) VALUES (?,?,?)',
                       (task_id, prompt, at))
            db.execute('INSERT INTO audit(run_id,task_id,event,at) VALUES (NULL,?,?,?)',
                       (task_id, 'task.created', at))
        return task_id

    def get_task(self, task_id: str) -> TaskRecord:
        with self._connect() as db:
            row = db.execute('SELECT id,prompt,created_at FROM tasks WHERE id=?',
                             (task_id,)).fetchone()
        if row is None:
            raise StateNotFound('task not found')
        return TaskRecord(**dict(row))

    def import_external_task(
        self, *, provider: str, instance: str, external_id: str,
        prompt: str, external_url: str | None = None,
    ) -> str:
        validate_external(provider, instance, external_id, prompt)
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT task_id FROM task_sources WHERE provider=? AND instance=? '
                             'AND external_id=?', (provider, instance, external_id)).fetchone()
            if row is not None:
                return str(row['task_id'])
            task_id, at = uuid.uuid4().hex, datetime.now(UTC).isoformat()
            db.execute('INSERT INTO tasks(id,prompt,created_at) VALUES (?,?,?)',
                       (task_id, prompt, at))
            db.execute(
                'INSERT INTO task_sources(task_id,provider,instance,external_id,external_url) '
                'VALUES (?,?,?,?,?)', (task_id, provider, instance, external_id, external_url),
            )
            db.execute('INSERT INTO audit(run_id,task_id,event,at) VALUES (NULL,?,?,?)',
                       (task_id, 'task.imported', at))
        return task_id
