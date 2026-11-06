"""Explicitly confirmed Draft PR demo, without AI execution or app code changes."""

from __future__ import annotations

import base64
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi import Request as BrowserRequest
from pydantic import BaseModel, Field

_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class DraftPRDemoRequest(BaseModel):
    repository: str = Field(min_length=3, max_length=200)
    confirmed: bool = False


def _github(path: str, method: str = "GET", payload: dict | None = None):
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise HTTPException(503, "GitHub credentials are not configured")
    headers = {
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "User-Agent": "generic-software-factory",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    data = json.dumps(payload).encode() if payload is not None else None
    if data is not None:
        headers["Content-Type"] = "application/json"
    try:
        with urlopen(
            Request("https://api.github.com" + path, data=data,
                    headers=headers, method=method),
            timeout=15,
        ) as response:
            return json.load(response)
    except HTTPError as exc:
        if exc.code in (401, 403, 404):
            raise HTTPException(403, "GitHub access denied or unavailable") from exc
        raise HTTPException(502, "GitHub request failed") from exc
    except (URLError, TimeoutError) as exc:
        raise HTTPException(502, "GitHub unavailable") from exc


def install_github_pr_demo_routes(app: FastAPI) -> None:
    @app.post("/api/github/demo/draft-pr", status_code=201)
    def create_demo_pr(payload: DraftPRDemoRequest, request: BrowserRequest):
        origin = request.headers.get("origin", "").rstrip("/")
        if (origin != str(request.base_url).rstrip("/")
                or request.headers.get("sec-fetch-site") == "cross-site"
                or request.headers.get("content-type", "").split(";")[0].strip()
                != "application/json"):
            raise HTTPException(403, "Same-origin JSON request required")
        if not payload.confirmed:
            raise HTTPException(422, "Explicit confirmation required")
        name = payload.repository
        if not _REPOSITORY.fullmatch(name) or ".." in name:
            raise HTTPException(422, "Invalid repository")
        base = "/repos/" + "/".join(quote(x, safe="") for x in name.split("/"))
        repo = _github(base)
        if repo.get("full_name", "").casefold() != name.casefold():
            raise HTTPException(422, "Repository identity mismatch")
        if not repo.get("permissions", {}).get("push"):
            raise HTTPException(403, "Push permission required")
        default_branch = repo.get("default_branch")
        if not isinstance(default_branch, str) or not default_branch:
            raise HTTPException(422, "Default branch unavailable")
        ref = _github(base + "/git/ref/heads/" + quote(default_branch, safe=""))
        sha = ref.get("object", {}).get("sha")
        if not isinstance(sha, str) or not re.fullmatch(r"[a-f0-9]{40}", sha):
            raise HTTPException(502, "Invalid base branch SHA")
        branch = "sf-demo-" + uuid4().hex[:12]
        _github(base + "/git/refs", "POST", {
            "ref": "refs/heads/" + branch, "sha": sha,
        })
        marker = ".sf-factory-demo/" + branch + ".md"
        content = (
            "# Software Factory Draft PR demo\n\n"
            "This is a harmless demo marker. No AI or application code was changed.\n"
        )
        _github(base + "/contents/" + marker, "PUT", {
            "message": "docs: add Software Factory demo marker",
            "content": base64.b64encode(content.encode()).decode(),
            "branch": branch,
        })
        pr = _github(base + "/pulls", "POST", {
            "title": "docs: Software Factory Draft PR demo",
            "head": branch, "base": default_branch, "draft": True,
            "body": "Created explicitly from the Software Factory local dashboard. "
                    "Demo marker only; no AI execution.",
        })
        return {"url": pr["html_url"], "number": pr["number"], "branch": branch}
