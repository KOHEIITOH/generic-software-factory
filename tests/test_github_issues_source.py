import io
import json
from pathlib import Path

import pytest

from sf_factory.factory import Factory
from sf_factory.github_issues_source import GitHubIssuesSource
from sf_factory.task_sources import import_issue


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return io.BytesIO(json.dumps(self.payload).encode())

    def __exit__(self, *args):
        return False


def test_fetch_and_import_issue(tmp_path: Path, monkeypatch) -> None:
    def fake_open(request, timeout):
        assert request.full_url == "https://api.github.com/repos/org/repo/issues/42"
        assert request.get_header("Authorization") == "Bearer secret"
        assert timeout == 10.0
        return FakeResponse({
            "number": 42, "title": "Fix tests", "body": "Run CI",
            "html_url": "https://github.com/org/repo/issues/42",
        })

    monkeypatch.setattr("sf_factory.github_issues_source.urlopen", fake_open)
    source = GitHubIssuesSource("org/repo", token="secret")
    factory = Factory(tmp_path)
    first = import_issue(factory, source, "42")
    assert first == import_issue(factory, source, "42")
    assert factory.list_tasks()[0]["prompt"] == "Fix tests\n\nRun CI"


def test_pull_request_is_not_imported(monkeypatch) -> None:
    monkeypatch.setattr(
        "sf_factory.github_issues_source.urlopen",
        lambda *a, **kw: FakeResponse({
            "number": 42, "title": "PR", "pull_request": {},
            "html_url": "https://github.com/org/repo/issues/42",
        }),
    )
    with pytest.raises(ValueError, match="not an issue"):
        GitHubIssuesSource("org/repo").fetch_issue("42")


@pytest.mark.parametrize("issue_id", ["0", "-1", "abc", "1/../../secrets"])
def test_invalid_issue_ids_rejected(issue_id: str) -> None:
    with pytest.raises(ValueError):
        GitHubIssuesSource("org/repo").fetch_issue(issue_id)


@pytest.mark.parametrize("repository", ["org", "../repo", "org/../repo", "org/repo/extra"])
def test_invalid_repository_rejected(repository: str) -> None:
    with pytest.raises(ValueError):
        GitHubIssuesSource(repository)


def test_list_issues_pagination_and_pull_request_filter(monkeypatch) -> None:
    def fake_open(request, timeout):
        assert "state=closed&per_page=2&page=3" in request.full_url
        return FakeResponse([
            {"number": 4, "title": "Closed task", "body": "Details",
             "html_url": "https://github.com/org/repo/issues/4"},
            {"number": 5, "title": "Pull request", "pull_request": {},
             "html_url": "https://github.com/org/repo/issues/5"},
        ])

    monkeypatch.setattr("sf_factory.github_issues_source.urlopen", fake_open)
    issues, has_more = GitHubIssuesSource("org/repo").list_issues(
        limit=2, page=3, state="closed"
    )
    assert has_more is True
    assert len(issues) == 1
    assert issues[0].external_id == "4"
    assert issues[0].prompt == "Closed task\\n\\nDetails"


@pytest.mark.parametrize("kwargs", [
    {"page": 0}, {"page": 10001}, {"state": "all"}, {"limit": 0},
])
def test_invalid_list_parameters(kwargs) -> None:
    with pytest.raises(ValueError):
        GitHubIssuesSource("org/repo").list_issues(**kwargs)
