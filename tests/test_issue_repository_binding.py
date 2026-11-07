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
    issue_key = factory.import_issue(
        provider="github", instance="org/repo", external_id="59", prompt="Implement"
    )
    result = factory.bind_issue_repository(issue_key, "org/repo", checkout)
    assert result["local_path"] == str(checkout.resolve())
    with factory._connect() as db:
        row = db.execute(
            "SELECT repository FROM issue_repositories WHERE issue_key=?", (issue_key,)
        ).fetchone()
    assert row["repository"] == "org/repo"
    issue = next(item for item in factory.list_issues() if item["key"] == issue_key)
    assert issue["bound_repository"] == "org/repo"
    assert issue["bound_local_path"] == str(checkout.resolve())


def test_rejects_mismatched_origin(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    _repo(checkout, "https://github.com/org/other.git")
    factory = Factory(tmp_path / "data")
    issue_key = factory.import_issue(
        provider="github", instance="org/repo", external_id="59", prompt="Implement"
    )
    with pytest.raises(ValueError, match="does not match"):
        factory.bind_issue_repository(issue_key, "org/repo", checkout)


def test_rejects_unrelated_issue(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    _repo(checkout, "https://github.com/org/repo.git")
    factory = Factory(tmp_path / "data")
    issue_key = factory.import_issue(
        provider="github", instance="org/another", external_id="59", prompt="Implement"
    )
    with pytest.raises(ValueError, match="Issue repository"):
        factory.bind_issue_repository(issue_key, "org/repo", checkout)
