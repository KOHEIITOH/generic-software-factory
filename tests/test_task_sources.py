from pathlib import Path

import pytest

from sf_factory.factory import Factory
from sf_factory.task_sources import ExternalIssue, import_issue


class StubSource:
    def __init__(self, issue: ExternalIssue):
        self.issue = issue
        self.calls = 0

    def fetch_issue(self, external_id: str) -> ExternalIssue:
        self.calls += 1
        return self.issue


def test_adapter_import_is_idempotent(tmp_path: Path) -> None:
    factory = Factory(tmp_path)
    source = StubSource(ExternalIssue(
        provider="jira", instance="https://example.atlassian.net",
        external_id="PAY-123", prompt="Add feature",
        external_url="https://example.atlassian.net/browse/PAY-123",
    ))
    first = import_issue(factory, source, "PAY-123")
    second = import_issue(factory, source, "PAY-123")
    assert first == second
    assert source.calls == 2
    assert factory.list_tasks()[0]["external_id"] == "PAY-123"


def test_adapter_must_return_requested_issue(tmp_path: Path) -> None:
    source = StubSource(ExternalIssue(
        provider="github", instance="org/repo", external_id="99", prompt="Fix",
    ))
    with pytest.raises(ValueError, match="different"):
        import_issue(Factory(tmp_path), source, "100")
    assert Factory(tmp_path).list_tasks() == []


@pytest.mark.parametrize("url", ["file:///etc/passwd", "javascript:alert(1)", ""])
def test_external_issue_rejects_non_http_url(url: str) -> None:
    with pytest.raises(ValueError, match="HTTP"):
        ExternalIssue("jira", "tenant", "ABC-1", "Task", url)


def test_external_issue_rejects_empty_identity() -> None:
    with pytest.raises(ValueError):
        ExternalIssue("jira", " ", "ABC-1", "Task")
