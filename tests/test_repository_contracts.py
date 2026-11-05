"""Provider-neutral repository contract regression tests."""

import pytest

from sf_factory.repository_contracts import (
    Connection,
    Project,
    Repository,
    RepositoryCapabilities,
    RepositoryAuthorization,
    RepositoryDiscovery,
    Visibility,
)


class FakeSource:
    def __init__(self, repositories: tuple[Repository, ...]) -> None:
        self.repositories = repositories

    def list_repositories(self, connection: Connection) -> tuple[Repository, ...]:
        return self.repositories

    def capabilities(
        self, connection: Connection, repository: Repository
    ) -> RepositoryCapabilities:
        return RepositoryCapabilities(read=True)


def test_provider_neutral_discovery_and_authorization() -> None:
    project = Project("project-1", "Sample", "local-principal")
    repo = Repository("repo-1", project.id, "fake-scm", "external-1", Visibility.PRIVATE)
    connection = Connection("conn-1", "fake-scm", project.owner_id, "secret-store:key")
    adapter = FakeSource((repo,))
    assert isinstance(adapter, RepositoryDiscovery)
    assert isinstance(adapter, RepositoryAuthorization)
    assert adapter.list_repositories(connection) == (repo,)
    assert adapter.capabilities(connection, repo) == RepositoryCapabilities(read=True)
    assert not adapter.capabilities(connection, repo).write


def test_multiple_repositories_share_one_project() -> None:
    repos = (
        Repository("frontend", "p", "local-git", "frontend", Visibility.LOCAL),
        Repository("backend", "p", "other-scm", "backend", Visibility.PRIVATE),
    )
    assert {repo.project_id for repo in repos} == {"p"}
    assert {repo.provider_id for repo in repos} == {"local-git", "other-scm"}


@pytest.mark.parametrize("field", ["id", "name", "owner_id"])
def test_project_rejects_empty_identity(field: str) -> None:
    values = {"id": "p", "name": "Name", "owner_id": "owner"}
    values[field] = " "
    with pytest.raises(ValueError):
        Project(**values)


def test_connection_contains_reference_not_secret_value() -> None:
    connection = Connection("c", "github", "local", "keyring:github/123")
    assert connection.credential_ref == "keyring:github/123"


def test_visibility_requires_explicit_enum() -> None:
    with pytest.raises(ValueError):
        Repository("r", "p", "git", "x", "private")
