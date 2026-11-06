"""Binding an imported Issue to a verified local Git repository."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from sf_factory.factory import Factory


def _repo(path: Path, remote: str) -> None:
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(
        ["git", "-C", str(path), "remote", "add", "origin", remote], check=True
    )


def test_imported_issue_can_bind_matching_origin(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    _repo(checkout, "git@github.com:org/repo.git")
    factory = Factory(tmp_path / "data")
    task_id = factory.import_external_task(
        provider="github", instance="org/repo", external_id="59", prompt="Implement"
    )
    result = factory.bind_task_repository(task_id, "org/repo", checkout)
    assert result["local_path"] == str(checkout.resolve())
    with factory._connect() as db:
        row = db.execute(
            "SELECT repository FROM task_repositories WHERE task_id=?", (task_id,)
        ).fetchone()
    assert row["repository"] == "org/repo"
    task = next(item for item in factory.list_tasks() if item["id"] == task_id)
    assert task["bound_repository"] == "org/repo"
    assert task["bound_local_path"] == str(checkout.resolve())


def test_rejects_mismatched_origin(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    _repo(checkout, "https://github.com/org/other.git")
    factory = Factory(tmp_path / "data")
    task_id = factory.import_external_task(
        provider="github", instance="org/repo", external_id="59", prompt="Implement"
    )
    with pytest.raises(ValueError, match="does not match"):
        factory.bind_task_repository(task_id, "org/repo", checkout)


def test_rejects_unrelated_issue(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    _repo(checkout, "https://github.com/org/repo.git")
    factory = Factory(tmp_path / "data")
    task_id = factory.import_external_task(
        provider="github", instance="org/another", external_id="59", prompt="Implement"
    )
    with pytest.raises(ValueError, match="Issue repository"):
        factory.bind_task_repository(task_id, "org/repo", checkout)
