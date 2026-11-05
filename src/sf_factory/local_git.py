"""Read-only local Git repository adapter.

Discovery is explicitly configured, never a recursive filesystem scan. No
credentials, network calls, branch mutation or arbitrary Git command input.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from sf_factory.repository_contracts import (
    Connection,
    Repository,
    RepositoryCapabilities,
    Visibility,
)

LOCAL_GIT_PROVIDER = "local-git"


class LocalGitAdapter:
    def __init__(self, paths: tuple[Path, ...], project_id: str) -> None:
        if not project_id.strip():
            raise ValueError("project_id must not be empty")
        self._project_id = project_id
        self._paths = tuple(path.resolve(strict=True) for path in paths)

    def list_repositories(self, connection: Connection) -> tuple[Repository, ...]:
        if connection.provider_id != LOCAL_GIT_PROVIDER:
            raise ValueError("connection provider mismatch")
        repositories: list[Repository] = []
        for path in self._paths:
            result = subprocess.run(
                ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            if result.returncode != 0:
                raise ValueError(f"not a Git repository: {path}")
            root = Path(result.stdout.strip()).resolve(strict=True)
            if root != path:
                raise ValueError(f"path is not the Git worktree root: {path}")
            repositories.append(
                Repository(
                    id=f"local:{root}",
                    project_id=self._project_id,
                    provider_id=LOCAL_GIT_PROVIDER,
                    external_id=str(root),
                    visibility=Visibility.LOCAL,
                )
            )
        return tuple(repositories)

    def capabilities(
        self, connection: Connection, repository: Repository
    ) -> RepositoryCapabilities:
        if connection.provider_id != LOCAL_GIT_PROVIDER:
            return RepositoryCapabilities()
        if repository.provider_id != LOCAL_GIT_PROVIDER:
            return RepositoryCapabilities()
        if repository.project_id != self._project_id:
            return RepositoryCapabilities()
        if not any(repository.external_id == str(path) for path in self._paths):
            return RepositoryCapabilities()
        return RepositoryCapabilities(read=True)
