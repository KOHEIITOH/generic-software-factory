"""Private GitHub Issue credentials are supplied by the server environment."""

from __future__ import annotations

import pytest

from sf_factory.github_issue_web import _source


def test_gh_token_preferred(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_TOKEN", "gh-secret")
    monkeypatch.setenv("GITHUB_TOKEN", "github-secret")
    source = _source("org/private")
    assert source.token == "gh-secret"


def test_github_token_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", "github-secret")
    assert _source("org/private").token == "github-secret"


def test_unauthenticated_public_issues_remain_supported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert _source("org/public").token is None
