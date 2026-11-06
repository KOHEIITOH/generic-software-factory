"""Security and behavior tests for the explicit Draft PR demo endpoint."""

from fastapi.testclient import TestClient

from sf_factory.web_api import create_app


def test_demo_requires_same_origin_and_confirmation(monkeypatch, tmp_path):
    monkeypatch.setenv("GH_TOKEN", "test-only")
    client = TestClient(create_app(data_dir=tmp_path))
    response = client.post(
        "/api/github/demo/draft-pr",
        json={"repository": "example/repo", "confirmed": True},
    )
    assert response.status_code == 403
    response = client.post(
        "/api/github/demo/draft-pr",
        json={"repository": "example/repo", "confirmed": False},
        headers={"Origin": "http://testserver"},
    )
    assert response.status_code == 422


def test_demo_creates_draft_only_after_permission_check(monkeypatch, tmp_path):
    from sf_factory.github_source_control import GitHubSourceControl

    calls = []

    def fake_github(self, path, method="GET", payload=None):
        calls.append((path, method, payload))
        if path == "/repos/example/repo":
            return {
                "full_name": "example/repo",
                "permissions": {"push": True},
                "default_branch": "main",
            }
        if path.endswith("/git/ref/heads/main"):
            return {"object": {"sha": "a" * 40}}
        if path.endswith("/pulls"):
            return {"html_url": "https://github.com/example/repo/pull/1", "number": 1}
        return {}

    monkeypatch.setattr(GitHubSourceControl, "_request", fake_github)
    client = TestClient(create_app(data_dir=tmp_path))
    response = client.post(
        "/api/github/demo/draft-pr",
        json={"repository": "example/repo", "confirmed": True},
        headers={"Origin": "http://testserver"},
    )
    assert response.status_code == 201
    assert response.json()["number"] == 1
    assert calls[-1][1] == "POST"
    assert calls[-1][2]["draft"] is True
    assert any("/contents/.sf-factory-demo/" in path for path, _, _ in calls)


def test_demo_rejects_read_only_repository(monkeypatch, tmp_path):
    from sf_factory.github_source_control import GitHubSourceControl

    def fake_github(self, path, method="GET", payload=None):
        return {
            "full_name": "example/repo",
            "permissions": {"push": False},
            "default_branch": "main",
        }

    monkeypatch.setattr(GitHubSourceControl, "_request", fake_github)
    client = TestClient(create_app(data_dir=tmp_path))
    response = client.post(
        "/api/github/demo/draft-pr",
        json={"repository": "example/repo", "confirmed": True},
        headers={"Origin": "http://testserver"},
    )
    assert response.status_code == 403


def test_demo_missing_credentials_is_service_error_and_makes_no_request(monkeypatch, tmp_path):
    import pytest

    monkeypatch.delenv('GH_TOKEN', raising=False)
    monkeypatch.delenv('GITHUB_TOKEN', raising=False)
    def unexpected(*args, **kwargs):
        pytest.fail('missing credentials must not send requests')
    monkeypatch.setattr('sf_factory.github_source_control.urlopen', unexpected)
    client = TestClient(create_app(data_dir=tmp_path))
    response = client.post('/api/github/demo/draft-pr',
        json={'repository': 'example/repo', 'confirmed': True},
        headers={'Origin': 'http://testserver'})
    assert response.status_code == 503


def test_demo_does_not_coerce_confirmation_into_approval(monkeypatch, tmp_path):
    import pytest

    def unexpected(*args, **kwargs):
        pytest.fail('invalid confirmation must not reach SCM')
    monkeypatch.setattr('sf_factory.github_source_control.GitHubSourceControl.describe_repository',
                        unexpected)
    client = TestClient(create_app(data_dir=tmp_path))
    for confirmation in ('true', 1, False):
        response = client.post('/api/github/demo/draft-pr',
            json={'repository': 'example/repo', 'confirmed': confirmation},
            headers={'Origin': 'http://testserver'})
        assert response.status_code == 422
