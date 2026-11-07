"""Minimal provider-neutral SCM operations used by the existing Draft PR demo."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from sf_factory.repository_contracts import RepositoryCapabilities

SourceControlErrorKind = Literal[
    'not_configured', 'access_denied', 'unavailable', 'invalid_response',
]


class SourceControlError(RuntimeError):
    def __init__(self, kind: SourceControlErrorKind, message: str):
        super().__init__(message)
        self.kind = kind


@dataclass(frozen=True)
class RepositoryInfo:
    external_id: str
    default_branch: str
    capabilities: RepositoryCapabilities


@dataclass(frozen=True)
class PullRequestReference:
    external_id: str
    url: str


class SourceControl(Protocol):
    def describe_repository(self, repository: str) -> RepositoryInfo: ...

    def branch_revision(self, repository: str, branch: str) -> str: ...

    def create_branch(self, repository: str, branch: str, revision: str) -> None: ...

    def write_file(self, repository: str, *, branch: str, path: str,
                   content: bytes, message: str) -> None: ...

    def create_draft_pull_request(self, repository: str, *, title: str, head: str,
                                  base: str, body: str) -> PullRequestReference: ...


@dataclass(frozen=True)
class CommitChange:
    path: str
    before: bytes | None
    after: bytes
    executable: bool = False


@dataclass(frozen=True)
class PreparedCommit:
    external_id: str
    tree_id: str
    parent_id: str


class ChangeSourceControl(SourceControl, Protocol):
    def prepare_commit(self, repository: str, *, parent_revision: str,
                       changes: tuple[CommitChange, ...], message: str) -> PreparedCommit: ...
