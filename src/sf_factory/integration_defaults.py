"""Initial integration composition: GitHub is the supported default provider.

Provider selection belongs here, not in Factory persistence or shared workflows.
Alternative providers may later be wired through the existing domain contracts.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sf_factory.repository_contracts import RepositoryBindingAdapter
from sf_factory.source_control import ChangeSourceControl

if TYPE_CHECKING:
    from sf_factory.task_sources import TaskSourceAdapter

DEFAULT_TASK_SOURCE = 'github'
DEFAULT_SOURCE_CONTROL = 'github'


def repository_binding() -> RepositoryBindingAdapter:
    from sf_factory.github_repo_identity import GitHubRepositoryBinding

    return GitHubRepositoryBinding()


def detect_repository(root):
    from sf_factory.github_repo_identity import repository_from_origin

    return repository_from_origin(root)


def source_control() -> ChangeSourceControl:
    from sf_factory.github_source_control import GitHubSourceControl

    return GitHubSourceControl()


def task_source(repository: str) -> TaskSourceAdapter:
    from sf_factory.github_issues_source import GitHubIssuesSource

    return GitHubIssuesSource.from_environment(repository)


def list_open_issues(repository: str, page: int = 1):
    """Read-only selector composition; provider pagination stays in the adapter."""
    from sf_factory.github_issues_source import GitHubIssuesSource

    return GitHubIssuesSource.from_environment(repository).list_issues(page=page)


def describe_integrations() -> dict:
    """Local configuration only. Does not authenticate or call any provider."""
    from sf_factory.github_auth import credential_status

    return {'task_source': DEFAULT_TASK_SOURCE, 'source_control': DEFAULT_SOURCE_CONTROL,
            'credentials': credential_status()}


def repository_choices(cursor: str | None = None):
    from sf_factory.github_source_control import GitHubSourceControl

    return GitHubSourceControl().repository_choices(cursor)


def repository_source():
    from sf_factory.github_source_control import GitHubSourceControl

    return GitHubSourceControl()


def repository_origin(repository: str) -> str:
    from sf_factory.github_repo_identity import _REPO

    if not _REPO.fullmatch(repository) or '..' in repository:
        raise ValueError('valid repository identity required')
    return 'https://github.com/' + repository + '.git'
