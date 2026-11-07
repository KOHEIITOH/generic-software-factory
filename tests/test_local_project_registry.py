"""Registry preserves existing issue tables and scopes projects by owner."""

import sqlite3
from pathlib import Path

import pytest

from sf_factory.local_project_registry import LocalProjectRegistry
from sf_factory.repository_contracts import Project, Repository, Visibility


def test_additive_schema_and_multiple_repositories(tmp_path: Path) -> None:
    database = tmp_path / "factory.sqlite3"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE issues (id TEXT PRIMARY KEY, prompt TEXT)")
        db.execute("INSERT INTO issues VALUES ('old', 'keep')")
    registry = LocalProjectRegistry(database)
    registry.add_project(Project("p", "Example", "local"))
    registry.add_repository(Repository("fe", "p", "local-git", "/fe", Visibility.LOCAL))
    registry.add_repository(Repository("be", "p", "fake", "be", Visibility.PRIVATE))
    assert len(registry.list_repositories("p")) == 2
    assert registry.list_projects("other") == ()
    assert registry.list_projects("local") == (Project("p", "Example", "local"),)
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT prompt FROM issues WHERE id='old'").fetchone()[0] == "keep"


def test_missing_project_and_duplicate_repository_fail(tmp_path: Path) -> None:
    registry = LocalProjectRegistry(tmp_path / "factory.sqlite3")
    repo = Repository("r", "missing", "local-git", "/repo", Visibility.LOCAL)
    with pytest.raises(sqlite3.IntegrityError):
        registry.add_repository(repo)
    registry.add_project(Project("p", "Project", "local"))
    first = Repository("r", "p", "local-git", "/repo", Visibility.LOCAL)
    registry.add_repository(first)
    with pytest.raises(sqlite3.IntegrityError):
        registry.add_repository(
            Repository("different", "p", "local-git", "/repo", Visibility.LOCAL)
        )


def test_reopen_preserves_records(tmp_path: Path) -> None:
    database = tmp_path / "factory.sqlite3"
    LocalProjectRegistry(database).add_project(Project("p", "Project", "local"))
    assert LocalProjectRegistry(database).list_projects("local")[0].id == "p"
