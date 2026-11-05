"""Local project registration API tests."""

from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402
from sf_factory.web_api import create_app  # noqa: E402


def test_project_repository_registration_and_duplicate(tmp_path: Path) -> None:
    with TestClient(create_app(data_dir=tmp_path)) as client:
        origin = {"origin": str(client.base_url).rstrip("/")}
        assert client.post("/api/projects", json={"name": "X"}).status_code == 403
        assert client.post("/api/projects", headers={"origin": "https://evil.example"}, json={"name": "X"}).status_code == 403
        assert client.post("/api/projects", headers=origin, json={"name": "  "}).status_code == 422
        created = client.post("/api/projects", headers=origin, json={"name": " Demo "})
        assert created.status_code == 201
        project_id = created.json()["id"]
        assert created.json()["name"] == "Demo"
        assert [p["id"] for p in client.get("/api/projects").json()["projects"]] == [project_id]
        url = f"/api/projects/{project_id}/repositories"
        payload = {"provider_id": "local-git", "external_id": "/tmp/demo", "visibility": "local"}
        assert client.post(url, json=payload).status_code == 403
        assert client.post("/api/projects/unknown/repositories", headers=origin, json=payload).status_code == 404
        added = client.post(url, headers=origin, json=payload)
        assert added.status_code == 201
        assert client.post(url, headers=origin, json=payload).status_code == 409
        assert client.get(url).json()["repositories"][0]["id"] == added.json()["id"]
        assert client.post(url, headers=origin, json={**payload, "visibility": "invalid"}).status_code == 422
