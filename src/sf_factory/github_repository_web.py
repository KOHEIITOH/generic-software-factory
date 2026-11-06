"""Read-only GitHub repository discovery for the local dashboard.

Uses the same server-side credentials as GitHub Issue import.
"""

from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import FastAPI, HTTPException


def install_github_repository_routes(app: FastAPI) -> None:
    @app.get("/api/github/repositories")
    def list_github_repositories():
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if not token:
            raise HTTPException(
                status_code=503, detail="GitHub credentials are not configured"
            )
        request = Request(
            "https://api.github.com/user/repos?per_page=100&sort=updated",
            headers={
                "Authorization": "Bearer " + token,
                "Accept": "application/vnd.github+json",
                "User-Agent": "generic-software-factory",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urlopen(request, timeout=10) as response:
                repositories = json.load(response)
        except (HTTPError, URLError, TimeoutError) as exc:
            raise HTTPException(
                status_code=502, detail="GitHub repository discovery failed"
            ) from exc
        if not isinstance(repositories, list):
            raise HTTPException(status_code=502, detail="Unexpected GitHub response")
        return {"repositories": [
            {
                "full_name": item["full_name"],
                "can_push": bool(item["permissions"].get("push")),
            }
            for item in repositories
            if isinstance(item, dict)
            and isinstance(item.get("full_name"), str)
            and isinstance(item.get("permissions"), dict)
        ]}
