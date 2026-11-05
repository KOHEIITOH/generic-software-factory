"""GitHub Issue UI endpoints use mocked external responses and a temporary DB."""

from unittest.mock import patch

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from sf_factory.task_sources import ExternalIssue
from sf_factory.web_api import create_app


def test_preview_and_confirmed_import(tmp_path):
    issue = ExternalIssue(provider="github", instance="owner/repo", external_id="7",
                          prompt="Fix a bug", external_url="https://github.com/owner/repo/issues/7")
    with patch("sf_factory.github_issue_web.GitHubIssuesSource.fetch_issue", return_value=issue):
        with TestClient(create_app(data_dir=tmp_path)) as client:
            preview = client.get(
                "/api/github/issue", params={"repository": "owner/repo", "number": 7}
            )
            assert preview.status_code == 200
            assert preview.json()["issue"]["prompt"] == "Fix a bug"
            assert client.get("/api/tasks").json()["tasks"] == []
            payload = {"repository": "owner/repo", "number": 7}
            assert client.post("/api/github/import", json=payload).status_code == 403
            headers = {"Origin": "http://testserver"}
            first = client.post("/api/github/import", json=payload, headers=headers)
            second = client.post("/api/github/import", json=payload, headers=headers)
            assert first.status_code == 200
            assert second.status_code == 200
            assert first.json()["task_id"] == second.json()["task_id"]
            assert len(client.get("/api/tasks").json()["tasks"]) == 1


def test_invalid_repository_rejected(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as client:
        result = client.get("/api/github/issue", params={"repository": "invalid", "number": 1})
        assert result.status_code == 422


def test_issue_list_excludes_pull_requests(tmp_path):
    issue = ExternalIssue(
        provider="github", instance="owner/repo", external_id="7",
        prompt="Fix a bug", external_url="https://github.com/owner/repo/issues/7",
    )
    with patch(
        "sf_factory.github_issue_web.GitHubIssuesSource.list_issues",
        return_value=[issue],
    ):
        with TestClient(create_app(data_dir=tmp_path)) as client:
            response = client.get("/api/github/issues", params={"repository": "owner/repo"})
            assert response.status_code == 200
            assert response.json()["issues"][0]["number"] == "7"
            assert client.get("/api/tasks").json()["tasks"] == []


def test_issue_list_invalid_repository(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as client:
        response = client.get("/api/github/issues", params={"repository": "invalid"})
        assert response.status_code == 422
