"""Prepare an isolated Git worktree without modifying the user's checkout.

This is workspace separation, NOT an OS security sandbox.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from sf_factory.github_repo_identity import verify_github_origin

_SAFE_REF = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._/-]{0,180}$")


def prepare_issue_worktree(
    checkout: Path, repository: str, destination: Path, branch: str
) -> Path:
    """Create a new detached-from-user-checkout branch at the current HEAD.

    No checkout changes, network operations, pushes, or agent execution occur.
    """
    root = verify_github_origin(checkout, repository)
    if not _SAFE_REF.fullmatch(branch) or ".." in branch or "@{" in branch:
        raise ValueError("invalid worktree branch name")
    destination = destination.expanduser().absolute()
    if destination.exists():
        raise ValueError("worktree destination already exists")
    if root == destination or root in destination.parents:
        raise ValueError("worktree must be outside the source checkout")
    destination.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "git", "-C", str(root), "worktree", "add",
        "-b", branch, "--", str(destination), "HEAD",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("could not prepare isolated worktree") from exc
    if result.returncode != 0:
        raise ValueError("could not create worktree (branch may already exist)")
    return destination
