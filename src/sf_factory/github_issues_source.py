"""Read-only GitHub Issues source using the GitHub REST API (stdlib only)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from sf_factory.task_sources import ExternalIssue

_REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_NUMBER = re.compile(r"^[1-9][0-9]*$")


@dataclass(frozen=True)
class GitHubIssuesSource:
    repository: str
    token: str | None = None
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        if not _REPO.fullmatch(self.repository) or ".." in self.repository:
            raise ValueError("repository must be owner/repo")
        if not 0 < self.timeout_seconds <= 60:
            raise ValueError("timeout must be between 0 and 60 seconds")

    def fetch_issue(self, external_id: str) -> ExternalIssue:
        if not _NUMBER.fullmatch(external_id):
            raise ValueError("GitHub issue ID must be a positive integer")
        owner, repo = self.repository.split("/")
        url = (
            "https://api.github.com/repos/"
            f"{quote(owner, safe='')}/{quote(repo, safe='')}/issues/{external_id}"
        )
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "generic-software-factory",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = Request(url, headers=headers)
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.load(response)
        except (HTTPError, URLError, TimeoutError) as exc:
            raise RuntimeError("GitHub issue request failed") from exc
        if not isinstance(payload, dict) or "pull_request" in payload:
            raise ValueError("GitHub response is not an issue")
        if payload.get("number") != int(external_id):
            raise ValueError("GitHub response issue number mismatch")
        title, body = payload.get("title"), payload.get("body")
        if not isinstance(title, str) or not title.strip():
            raise ValueError("GitHub issue has no valid title")
        if body is not None and not isinstance(body, str):
            raise ValueError("GitHub issue body is invalid")
        html_url = payload.get("html_url")
        expected = f"https://github.com/{self.repository}/issues/{external_id}"
        if html_url != expected:
            raise ValueError("GitHub issue URL does not match requested repository")
        prompt = title.strip() + ("\n\n" + body.strip() if body and body.strip() else "")
        return ExternalIssue(
            provider="github", instance=self.repository, external_id=external_id,
            prompt=prompt, external_url=expected,
        )
