"""Explicit local-only GitHub Issue preview and task import endpoints."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from sf_factory.factory import Factory
from sf_factory.github_issues_source import GitHubIssuesSource


class IssueInput(BaseModel):
    repository: str = Field(min_length=3, max_length=200)
    number: int = Field(ge=1)


def _fetch(repository: str, number: int):
    try:
        source = GitHubIssuesSource(repository=repository)
        return source.fetch_issue(str(number))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail="GitHub Issueを取得できませんでした") from exc


def install_github_issue_routes(app: FastAPI, data_dir: Path | None) -> None:
    @app.get("/api/github/issue")
    def preview(repository: str, number: int):
        issue = _fetch(repository, number)
        return {"issue": {"repository": issue.instance, "number": issue.external_id,
                          "prompt": issue.prompt, "url": issue.external_url}}

    @app.post("/api/github/import")
    def import_issue(selection: IssueInput, request: Request):
        # This local API has no authentication: require same-origin browser requests.
        origin = request.headers.get("origin", "")
        parsed = urlsplit(origin)
        if (parsed.scheme not in ("http", "https")
                or parsed.netloc != request.headers.get("host")
                or request.headers.get("content-type", "").split(";")[0].strip() != "application/json"):
            raise HTTPException(status_code=403, detail="Same-origin JSON request required")
        issue = _fetch(selection.repository, selection.number)
        task_id = Factory(data_dir or Path(".sf-factory")).import_external_task(
            provider=issue.provider, instance=issue.instance,
            external_id=issue.external_id, prompt=issue.prompt,
            external_url=issue.external_url,
        )
        return {"task_id": task_id, "external_url": issue.external_url}
