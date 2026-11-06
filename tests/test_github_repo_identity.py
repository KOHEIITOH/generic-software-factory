"""Regression tests for selected repository identity."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from sf_factory.github_repo_identity import verify_github_origin


@pytest.mark.parametrize("remote", [
    "https://github.com/Org/Repo.git",
    "git@github.com:Org/Repo.git",
    "ssh://git@github.com/Org/Repo.git",
])
def test_accepts_matching_origin(tmp_path: Path, remote: str) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "remote", "add", "origin", remote], check=True)
    assert verify_github_origin(tmp_path, "org/repo") == tmp_path.resolve()


def test_rejects_mismatched_origin(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run([
        "git", "-C", str(tmp_path), "remote", "add", "origin",
        "https://github.com/org/other.git",
    ], check=True)
    with pytest.raises(ValueError, match="does not match"):
        verify_github_origin(tmp_path, "org/repo")


def test_rejects_missing_origin(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    with pytest.raises(ValueError, match="not configured"):
        verify_github_origin(tmp_path, "org/repo")
