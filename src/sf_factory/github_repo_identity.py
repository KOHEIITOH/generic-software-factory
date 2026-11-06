"""Read-only verification of a local repository's GitHub origin."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from sf_factory.repo_discovery import discover_git_root

_REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_HTTPS = re.compile(r"^https://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$")
_SSH = re.compile(r"^git@github\.com:([^/]+)/([^/]+?)(?:\.git)?/?$")
_SSH_URL = re.compile(r"^ssh://git@github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$")


def verify_github_origin(directory: Path, repository: str) -> Path:
    """Verify identity without network access, authentication, or mutation."""
    if not _REPO.fullmatch(repository) or ".." in repository:
        raise ValueError("repository must be owner/repo")
    root = discover_git_root(directory)
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("could not inspect Git origin") from exc
    if result.returncode != 0:
        raise ValueError("Git origin is not configured")
    remote = result.stdout.strip()
    match = next((m for pattern in (_HTTPS, _SSH, _SSH_URL)
                  if (m := pattern.fullmatch(remote)) is not None), None)
    if match is None:
        raise ValueError("Git origin must be a GitHub HTTPS or SSH URL")
    actual = f"{match.group(1)}/{match.group(2)}"
    if actual.casefold() != repository.casefold():
        raise ValueError("selected GitHub repository does not match Git origin")
    return root
