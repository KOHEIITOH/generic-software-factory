"""Safety checks for Issue worktree preparation."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from sf_factory.issue_worktree import prepare_issue_worktree


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def make_repo(path: Path) -> None:
    git("init", "-q", str(path))
    git("-C", str(path), "config", "user.email", "test@example.com")
    git("-C", str(path), "config", "user.name", "Test")
    git("-C", str(path), "remote", "add", "origin", "https://github.com/org/repo.git")
    (path / "readme.txt").write_text("original")
    git("-C", str(path), "add", "readme.txt")
    git("-C", str(path), "commit", "-qm", "initial")


def test_worktree_is_separate_from_source_checkout(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    make_repo(checkout)
    destination = tmp_path / "workspaces" / "issue-59"
    actual = prepare_issue_worktree(checkout, "org/repo", destination, "sf/issue-59")
    assert actual == destination
    assert (actual / "readme.txt").read_text() == "original"
    (actual / "readme.txt").write_text("changed")
    assert (checkout / "readme.txt").read_text() == "original"
    assert git("-C", str(checkout), "status", "--porcelain") == ""


def test_rejects_destination_inside_checkout(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    make_repo(checkout)
    with pytest.raises(ValueError, match="outside"):
        prepare_issue_worktree(
            checkout, "org/repo", checkout / "workspaces" / "issue", "sf/issue-59"
        )


def test_rejects_mismatched_github_origin(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    make_repo(checkout)
    with pytest.raises(ValueError, match="does not match"):
        prepare_issue_worktree(
            checkout, "org/other", tmp_path / "workspaces" / "issue", "sf/issue-59"
        )


def test_rejects_existing_destination(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    make_repo(checkout)
    destination = tmp_path / "existing"
    destination.mkdir()
    with pytest.raises(ValueError, match="already exists"):
        prepare_issue_worktree(checkout, "org/repo", destination, "sf/issue-59")


def test_rejects_symlink_into_checkout(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    make_repo(checkout)
    alias = tmp_path / "alias"
    alias.symlink_to(checkout, target_is_directory=True)
    with pytest.raises(ValueError, match="outside"):
        prepare_issue_worktree(
            checkout, "org/repo", alias / "nested", "sf/issue-59"
        )
