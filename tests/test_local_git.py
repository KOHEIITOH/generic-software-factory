"""Local Git adapter tests use temporary repositories only."""

import subprocess
from pathlib import Path

import pytest

from sf_factory.local_git import LocalGitAdapter
from sf_factory.repository_contracts import Connection, Visibility


def _git(*args: str) -> None:
    subprocess.run(["git", *args], check=True, capture_output=True, timeout=10)


def test_discovery_is_explicit_and_read_only(tmp_path: Path) -> None:
    root = tmp_path / "sample"
    root.mkdir()
    _git("init", str(root))
    connection = Connection("local", "local-git", "local-principal", "none:local")
    adapter = LocalGitAdapter((root,), "project-1")
    repositories = adapter.list_repositories(connection)
    assert len(repositories) == 1
    repo = repositories[0]
    assert repo.visibility == Visibility.LOCAL
    assert repo.external_id == str(root.resolve())
    assert adapter.capabilities(connection, repo).read
    assert not adapter.capabilities(connection, repo).write
    assert not adapter.capabilities(connection, repo).pull_request


def test_rejects_nested_directory_and_non_git(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _git("init", str(root))
    nested = root / "nested"
    nested.mkdir()
    connection = Connection("local", "local-git", "local", "none:local")
    with pytest.raises(ValueError, match="worktree root"):
        LocalGitAdapter((nested,), "p").list_repositories(connection)
    other = tmp_path / "other"
    other.mkdir()
    with pytest.raises(ValueError, match="not a Git repository"):
        LocalGitAdapter((other,), "p").list_repositories(connection)


def test_provider_mismatch_is_fail_closed(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _git("init", str(root))
    adapter = LocalGitAdapter((root,), "p")
    wrong = Connection("other", "github", "local", "none:local")
    with pytest.raises(ValueError, match="provider mismatch"):
        adapter.list_repositories(wrong)
    valid = Connection("local", "local-git", "local", "none:local")
    repo = adapter.list_repositories(valid)[0]
    assert not adapter.capabilities(wrong, repo).read
