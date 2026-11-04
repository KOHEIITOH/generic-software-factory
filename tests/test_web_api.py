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
