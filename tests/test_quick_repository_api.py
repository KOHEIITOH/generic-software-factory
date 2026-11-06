"""Quick repository detection API tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from sf_factory.web_api import create_app  # noqa: E402


def test_quick_repository_detects_server_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    nested = tmp_path / "nested"
    nested.mkdir()
    monkeypatch.chdir(nested)
    with TestClient(create_app(data_dir=tmp_path / "data")) as client:
        result = client.get("/api/quick/repository")
    assert result.status_code == 200
    assert result.json() == {
        "detected": True,
        "repository_root": str(tmp_path.resolve()),
        "provider": "local-git",
    }


def test_quick_repository_handles_non_git_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    with TestClient(create_app(data_dir=tmp_path / "data")) as client:
        result = client.get("/api/quick/repository")
    assert result.status_code == 200
    assert result.json() == {
        "detected": False,
        "repository_root": None,
        "provider": None,
    }


def test_explicit_repository_inspection_requires_same_origin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.chdir(outside)
    base = "http://127.0.0.1:8000"
    with TestClient(create_app(data_dir=tmp_path / "data"), base_url=base) as client:
        payload = {"path": str(repository)}
        assert client.post("/api/quick/repository/inspect", json=payload).status_code == 403
        assert client.post(
            "/api/quick/repository/inspect",
            headers={"Origin": "https://evil.example"},
            json=payload,
        ).status_code == 403
        response = client.post(
            "/api/quick/repository/inspect",
            headers={"Origin": base},
            json=payload,
        )
        invalid = client.post(
            "/api/quick/repository/inspect",
            headers={"Origin": base},
            json={"path": str(outside)},
        )
    assert response.status_code == 200
    assert response.json()["repository_root"] == str(repository.resolve())
    assert invalid.status_code == 422
