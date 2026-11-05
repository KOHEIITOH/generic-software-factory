"""Additive local task-to-project associations.

Existing tasks remain valid without a project. This service is internal only;
server-facing authorization must be implemented before exposing it via API.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


class LocalTaskProjects:
    def __init__(self, database: Path) -> None:
        self.database = database
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS task_projects (
                    task_id TEXT PRIMARY KEY REFERENCES tasks(id) ON DELETE CASCADE,
                    project_id TEXT NOT NULL REFERENCES projects(id)
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database)
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def assign(self, task_id: str, project_id: str) -> None:
        """Associate a task once; reject accidental reassignment."""
        if not task_id.strip() or not project_id.strip():
            raise ValueError("task_id and project_id must not be empty")
        with self._connect() as db:
            db.execute(
                "INSERT INTO task_projects(task_id,project_id) VALUES (?,?)",
                (task_id, project_id),
            )

    def project_for_task(self, task_id: str) -> str | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT project_id FROM task_projects WHERE task_id=?", (task_id,)
            ).fetchone()
        return str(row[0]) if row is not None else None

    def tasks_for_project(self, project_id: str) -> tuple[str, ...]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT task_id FROM task_projects WHERE project_id=? ORDER BY task_id",
                (project_id,),
            ).fetchall()
        return tuple(str(row[0]) for row in rows)
