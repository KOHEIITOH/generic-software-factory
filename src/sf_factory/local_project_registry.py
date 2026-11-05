"""Local-only Project/Repository registry with additive SQLite tables.

No GitHub credentials or AI execution are stored or triggered here.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from sf_factory.repository_contracts import Project, Repository, Visibility


class LocalProjectRegistry:
    def __init__(self, database: Path) -> None:
        self.database = database
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    owner_id TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS repositories (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id),
                    provider_id TEXT NOT NULL,
                    external_id TEXT NOT NULL,
                    visibility TEXT NOT NULL,
                    UNIQUE(project_id, provider_id, external_id)
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database)
        db.execute("PRAGMA foreign_keys=ON")
        db.row_factory = sqlite3.Row
        return db

    def add_project(self, project: Project) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO projects(id,name,owner_id) VALUES (?,?,?)",
                (project.id, project.name, project.owner_id),
            )

    def add_repository(self, repository: Repository) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO repositories(id,project_id,provider_id,external_id,visibility) "
                "VALUES (?,?,?,?,?)",
                (
                    repository.id,
                    repository.project_id,
                    repository.provider_id,
                    repository.external_id,
                    repository.visibility.value,
                ),
            )

    def list_projects(self, owner_id: str) -> tuple[Project, ...]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT id,name,owner_id FROM projects WHERE owner_id=? ORDER BY id",
                (owner_id,),
            ).fetchall()
        return tuple(Project(**dict(row)) for row in rows)

    def list_repositories(self, project_id: str) -> tuple[Repository, ...]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT id,project_id,provider_id,external_id,visibility "
                "FROM repositories WHERE project_id=? ORDER BY id",
                (project_id,),
            ).fetchall()
        return tuple(
            Repository(
                id=row["id"],
                project_id=row["project_id"],
                provider_id=row["provider_id"],
                external_id=row["external_id"],
                visibility=Visibility(row["visibility"]),
            )
            for row in rows
        )
