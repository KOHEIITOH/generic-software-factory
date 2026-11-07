"""Implementation preflight never starts execution or authorizes writes."""
from fastapi.testclient import TestClient
from issue_fixtures import seed_issue

from sf_factory.factory import Factory
from sf_factory.web_api import create_app


def test_preflight_is_read_only_and_fail_closed(tmp_path):
    factory = Factory(tmp_path)
    issue_key = seed_issue(factory, "Change the application")
    client = TestClient(create_app(data_dir=tmp_path))

    response = client.get(
        f"/api/issues/{issue_key}/implementation-preflight"
    )
    assert response.status_code == 200
    result = response.json()
    assert result["ready_for_implementation"] is False
    assert result["execution_started"] is False
    assert "GitHub Issue source required" in result["blockers"]
    assert "Verified local repository binding required" in result["blockers"]
    assert "Workspace write is disabled by default" in result["blockers"]
    assert factory.list_runs() == []


def test_preflight_unknown_task_returns_404(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path))
    response = client.get(
        "/api/issues/missing/implementation-preflight"
    )
    assert response.status_code == 404



def test_preflight_bound_github_task_still_cannot_execute(tmp_path):
    factory = Factory(tmp_path)
    issue_key = factory.import_issue(
        provider="github", instance="example/repo", external_id="42",
        prompt="Implement issue", external_url="https://github.com/example/repo/issues/42",
    )
    with factory._connect() as db:
        db.execute(
            "INSERT INTO issue_repositories(issue_key,repository,local_path,linked_at) "
            "VALUES (?,?,?,?)",
            (issue_key, "example/repo", str(tmp_path), "2026-01-01T00:00:00Z"),
        )
    client = TestClient(create_app(data_dir=tmp_path))
    result = client.get(
        f"/api/issues/{issue_key}/implementation-preflight"
    ).json()
    assert result["repository"] == "example/repo"
    assert result["ready_for_implementation"] is False
    assert result["execution_started"] is False
    assert "GitHub Issue source required" not in result["blockers"]
    assert "Verified local repository binding required" not in result["blockers"]
    assert "Isolated write-capable agent execution is not implemented" in result["blockers"]
    assert factory.list_runs() == []
