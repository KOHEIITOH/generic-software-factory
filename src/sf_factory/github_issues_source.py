"""Read-only GitHub Issues source using the GitHub REST API (stdlib only)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from sf_factory.github_auth import environment_token
from sf_factory.task_sources import ExternalIssue

_REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_NUMBER = re.compile(r"^[1-9][0-9]*$")


@dataclass(frozen=True)
class GitHubIssuesSource:
    repository: str
    token: str | None = field(default=None, repr=False)
    timeout_seconds: float = 10.0

    @classmethod
    def from_environment(cls, repository: str) -> GitHubIssuesSource:
        return cls(repository=repository, token=environment_token())

    def __post_init__(self) -> None:
        if not _REPO.fullmatch(self.repository) or ".." in self.repository:
            raise ValueError("repository must be owner/repo")
        if not 0 < self.timeout_seconds <= 60:
            raise ValueError("timeout must be between 0 and 60 seconds")

    def list_issues(
        self, limit: int = 50, page: int = 1, state: str = "open"
    ) -> tuple[list[ExternalIssue], bool]:
        """Fetch a page of issues; PRs are filtered out of the results."""
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if not 1 <= page <= 10000:
            raise ValueError("page must be between 1 and 10000")
        if state not in ("open", "closed"):
            raise ValueError("state must be open or closed")
        owner, repo = self.repository.split("/")
        url = (
            "https://api.github.com/repos/"
            f"{quote(owner, safe='')}/{quote(repo, safe='')}/issues"
            f"?state={state}&per_page={limit}&page={page}"
        )
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "generic-software-factory",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            with urlopen(Request(url, headers=headers), timeout=self.timeout_seconds) as response:
                payload = json.load(response)
        except (HTTPError, URLError, TimeoutError) as exc:
            raise RuntimeError("GitHub issue list request failed") from exc
        if not isinstance(payload, list):
            raise ValueError("GitHub response is not an issue list")
        issues = []
        for item in payload:
            if not isinstance(item, dict) or "pull_request" in item:
                continue
            number = item.get("number")
            title = item.get("title")
            body = item.get("body")
            if (not isinstance(number, int) or number < 1
                    or not isinstance(title, str) or not title.strip()
                    or (body is not None and not isinstance(body, str))):
                continue
            expected = f"https://github.com/{self.repository}/issues/{number}"
            if item.get("html_url") != expected:
                continue
            prompt = title.strip() + ("\n\n" + body.strip() if body and body.strip() else "")
            issues.append(ExternalIssue(
                provider="github", instance=self.repository, external_id=str(number),
                prompt=prompt, external_url=expected,
            ))
        return issues, len(payload) == limit

    def fetch_issue(self, external_id: str) -> ExternalIssue:
        from sf_factory.operation_control import checkpoint
        checkpoint()
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
