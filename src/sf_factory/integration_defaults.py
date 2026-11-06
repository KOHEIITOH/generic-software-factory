"""Initial integration composition: GitHub is the supported default provider.

Provider selection belongs here, not in Factory persistence or shared workflows.
Alternative providers may later be wired through the existing domain contracts.
"""
from __future__ import annotations

from sf_factory.repository_contracts import RepositoryBindingAdapter


def repository_binding() -> RepositoryBindingAdapter:
    from sf_factory.github_repo_identity import GitHubRepositoryBinding

    return GitHubRepositoryBinding()
