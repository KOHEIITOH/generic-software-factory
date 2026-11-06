"""Provider-neutral project, repository and connection domain contracts.

These immutable records contain no credentials or vendor-specific installation IDs.
Authentication and network operations belong to future adapters.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol, runtime_checkable


def _required(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")


class Visibility(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"
    LOCAL = "local"


@dataclass(frozen=True)
class Project:
    id: str
    name: str
    owner_id: str

    def __post_init__(self) -> None:
        for field in ("id", "name", "owner_id"):
            _required(getattr(self, field), field)


@dataclass(frozen=True)
class Repository:
    id: str
    project_id: str
    provider_id: str
    external_id: str
    visibility: Visibility

    def __post_init__(self) -> None:
        for field in ("id", "project_id", "provider_id", "external_id"):
            _required(getattr(self, field), field)
        if not isinstance(self.visibility, Visibility):
            raise ValueError("visibility must be a Visibility")


@dataclass(frozen=True)
class Connection:
    id: str
    provider_id: str
    principal_id: str
    credential_ref: str

    def __post_init__(self) -> None:
        for field in ("id", "provider_id", "principal_id", "credential_ref"):
            _required(getattr(self, field), field)


@dataclass(frozen=True)
class RepositoryCapabilities:
    read: bool = False
    write: bool = False
    pull_request: bool = False


@runtime_checkable
class RepositoryDiscovery(Protocol):
    def list_repositories(self, connection: Connection) -> tuple[Repository, ...]:
        """Return a snapshot of repositories visible to the connection principal."""
        ...


@runtime_checkable
class RepositoryAuthorization(Protocol):
    def capabilities(
        self, connection: Connection, repository: Repository
    ) -> RepositoryCapabilities:
        """Return effective capabilities; never infer write from visibility."""
        ...


class ProjectRegistry(Protocol):
    """Local registration operations shared by optional persistence adapters."""

    def add_project(self, project: Project) -> None: ...

    def add_repository(self, repository: Repository) -> None: ...

    def list_projects(self, owner_id: str) -> tuple[Project, ...]: ...

    def list_repositories(self, project_id: str) -> tuple[Repository, ...]: ...


class RepositoryBindingAdapter(Protocol):
    def verify(self, *, provider: str, instance: str, repository: str,
               local_path: Path) -> Path:
        """Verify task scope and local identity; return a canonical existing root.

        Provider naming, source-to-repository rules and remote URL parsing belong
        to the adapter. Verification must not mutate code or perform Git writes.
        """
        ...
