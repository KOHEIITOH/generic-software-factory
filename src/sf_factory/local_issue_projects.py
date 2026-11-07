"""Additive local issue-to-project associations.

Existing issues remain valid without a project. This service is internal only;
server-facing authorization must be implemented before exposing it via API.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


class LocalIssueProjects:
    def __init__(self, database: Path) -> None:
        self.database = database
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS issue_projects (
                    issue_key TEXT PRIMARY KEY REFERENCES issues(issue_key) ON DELETE CASCADE,
                    project_id TEXT NOT NULL REFERENCES projects(id)
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database)
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def assign(self, issue_key: str, project_id: str) -> None:
        """Associate a issue once; reject accidental reassignment."""
        if not issue_key.strip() or not project_id.strip():
            raise ValueError("issue_key and project_id must not be empty")
        with self._connect() as db:
            db.execute(
                "INSERT INTO issue_projects(issue_key,project_id) VALUES (?,?)",
                (issue_key, project_id),
            )

    def project_for_issue(self, issue_key: str) -> str | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT project_id FROM issue_projects WHERE issue_key=?", (issue_key,)
            ).fetchone()
        return str(row[0]) if row is not None else None

    def issues_for_project(self, project_id: str) -> tuple[str, ...]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT issue_key FROM issue_projects WHERE project_id=? ORDER BY issue_key",
                (project_id,),
            ).fetchall()
        return tuple(str(row[0]) for row in rows)
