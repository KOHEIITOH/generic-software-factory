"""Single repository discovery regression tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from sf_factory.repo_discovery import discover_git_root


def test_detect_root_from_nested_directory(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    nested = tmp_path / "src" / "feature"
    nested.mkdir(parents=True)
    assert discover_git_root(nested) == tmp_path.resolve()


def test_reject_non_repository(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not inside a Git worktree"):
        discover_git_root(tmp_path)


def test_reject_file_path(tmp_path: Path) -> None:
    target = tmp_path / "file.txt"
    target.write_text("hello")
    with pytest.raises(ValueError, match="must be a directory"):
        discover_git_root(target)
