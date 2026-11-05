"""API smoke tests; skip when optional web dependencies are not installed."""

import pytest

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
    task_id = factory.create_task("Check repository quality")
    with TestClient(create_app(data_dir=tmp_path)) as client:
        tasks = client.get("/api/tasks")
        runs = client.get("/api/runs")
        mutation = client.post("/api/tasks", json={"prompt": "not allowed"})
    assert tasks.status_code == 200
    assert tasks.json()["tasks"][0]["id"] == task_id
    assert runs.status_code == 200
    assert runs.json() == {"runs": []}
    assert mutation.status_code == 403


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
    assert "AI開発チーム" in guide.text
    assert 'href="/onboarding"' in guide.text
    assert onboarding.status_code == 200
    assert "オンボーディング" in onboarding.text
    assert "<h2>" in onboarding.text
    assert "初回オンボーディング" in onboarding.text


def test_create_local_task_requires_same_origin_and_never_runs(tmp_path) -> None:
    from sf_factory.factory import Factory

    headers = {"Origin": "http://127.0.0.1:8000"}
    with TestClient(create_app(data_dir=tmp_path), base_url="http://127.0.0.1:8000") as client:
        assert client.post("/api/tasks", json={"prompt": "hello"}).status_code == 403
        forbidden = client.post(
            "/api/tasks", headers={"Origin": "https://evil.example"},
            json={"prompt": "hello"},
        )
        assert forbidden.status_code == 403
        blank = client.post("/api/tasks", headers=headers, json={"prompt": "   "})
        assert blank.status_code == 422
        created = client.post("/api/tasks", headers=headers, json={"prompt": "  hello  "})
        assert created.status_code == 201
        assert client.get("/api/tasks").json()["tasks"][0]["prompt"] == "hello"
    assert Factory(tmp_path).list_runs() == []
