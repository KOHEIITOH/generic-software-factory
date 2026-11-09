"""API smoke tests; skip when optional web dependencies are not installed."""
import pytest
from issue_fixtures import seed_issue

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from sf_factory.web_api import create_app  # noqa: E402


def test_health_endpoint() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_runtime_endpoint_only_lists_names() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/runtimes")
    assert response.status_code == 200
    assert response.json() == {"runtimes": ["codex", "copilot", "grok"]}


def test_mutating_requests_are_not_exposed() -> None:
    with TestClient(create_app()) as client:
        response = client.post("/api/runtimes")
    assert response.status_code == 405


def test_task_and_run_listing_requires_origin_for_mutation(tmp_path) -> None:
    from sf_factory.factory import Factory

    factory = Factory(tmp_path)
    issue_key = seed_issue(factory, "Check repository quality")
    with TestClient(create_app(data_dir=tmp_path)) as client:
        issues = client.get("/api/issues")
        runs = client.get("/api/runs")
        mutation = client.post("/api/issues", json={"prompt": "not allowed"})
    assert issues.status_code == 200
    assert issues.json()["issues"][0]["key"] == issue_key
    assert runs.status_code == 200
    assert runs.json() == {"runs": []}
    assert mutation.status_code == 405


def test_local_documentation_routes(tmp_path) -> None:
    static_dir = tmp_path / "dist"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html>dashboard</html>")
    (static_dir / "assets").mkdir()
    with TestClient(create_app(static_dir=static_dir, data_dir=tmp_path)) as client:
        guide = client.get("/guide")
        onboarding = client.get("/onboarding")
        root = client.get("/")
    assert root.status_code == 200
    assert guide.status_code == 200
    assert "同意して実行・Draft PR作成" in guide.text
    assert 'href="/onboarding"' in guide.text
    assert onboarding.status_code == 200
    assert "オンボーディング" in onboarding.text
    assert "<h2>" in onboarding.text
    assert "初回オンボーディング" in onboarding.text
    assert "sf operator register" in onboarding.text
    assert "Web UIからのTask作成" not in guide.text + onboarding.text


def test_standalone_task_creation_api_is_removed(tmp_path) -> None:
    with TestClient(create_app(data_dir=tmp_path)) as client:
        assert client.get('/api/tasks').status_code == 404
        assert client.post('/api/tasks', json={'prompt': 'local'}).status_code == 404
        assert client.post('/api/issues', json={'prompt': 'local'}).status_code == 405
        paths = client.get('/openapi.json').json()['paths']
        assert not any('/tasks' in path for path in paths)
        assert 'post' not in paths['/api/issues']
