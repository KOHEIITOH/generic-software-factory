"""Local project read-only API regression tests."""
from pathlib import Path

import pytest
from issue_fixtures import seed_issue

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from sf_factory.factory import Factory  # noqa: E402
from sf_factory.local_project_registry import LocalProjectRegistry  # noqa: E402
from sf_factory.repository_contracts import Project, Repository, Visibility  # noqa: E402
from sf_factory.web_api import create_app  # noqa: E402


def test_project_listing_and_origin_guard(tmp_path: Path) -> None:
    factory = Factory(tmp_path)
    registry = LocalProjectRegistry(factory.db)
    registry.add_project(Project("p", "Local", "local"))
    registry.add_repository(Repository("r", "p", "local-git", "/repo", Visibility.LOCAL))
    registry.add_project(Project("hidden", "Other", "other"))
    registry.add_repository(
        Repository("private", "hidden", "fake", "hidden", Visibility.PRIVATE)
    )
    with TestClient(create_app(data_dir=tmp_path)) as client:
        projects = client.get("/api/projects")
        repositories = client.get("/api/projects/p/repositories")
        hidden = client.get("/api/projects/hidden/repositories")
        missing = client.get("/api/projects/missing/repositories")
        write = client.post("/api/projects", json={"name": "not allowed"})
    assert projects.status_code == 200
    assert [p["id"] for p in projects.json()["projects"]] == ["p"]
    assert repositories.json()["repositories"][0]["id"] == "r"
    assert hidden.status_code == 404
    assert missing.status_code == 404
    assert write.status_code == 403


def test_empty_project_listing_does_not_change_tasks(tmp_path: Path) -> None:
    factory = Factory(tmp_path)
    issue = seed_issue(factory, "existing")
    with TestClient(create_app(data_dir=tmp_path)) as client:
        assert client.get("/api/projects").json() == {"projects": []}
    assert Factory(tmp_path).show_issue(issue)["issue"]["prompt"] == "existing"
