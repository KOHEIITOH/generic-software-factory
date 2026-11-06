"""Implementation preflight never starts execution or authorizes writes."""

from fastapi.testclient import TestClient

from sf_factory.factory import Factory
from sf_factory.web_api import create_app


def test_preflight_is_read_only_and_fail_closed(tmp_path):
    factory = Factory(tmp_path)
    task_id = factory.create_task("Change the application")
    client = TestClient(create_app(data_dir=tmp_path))

    response = client.get(
        f"/api/tasks/{task_id}/implementation-preflight"
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
        "/api/tasks/missing/implementation-preflight"
    )
    assert response.status_code == 404
