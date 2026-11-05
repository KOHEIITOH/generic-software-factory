"""Explicit, read-only discovery of a Git worktree from a chosen directory."""

from __future__ import annotations

import subprocess
from pathlib import Path


def discover_git_root(directory: Path) -> Path:
    """Return the worktree root; never scan sibling directories or mutate Git."""
    location = directory.expanduser().resolve(strict=True)
    if not location.is_dir():
        raise ValueError("repository directory must be a directory")
    try:
        result = subprocess.run(
            ["git", "-C", str(location), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("could not inspect local Git repository") from exc
    if result.returncode != 0 or not result.stdout.strip():
        raise ValueError("not inside a Git worktree")
    return Path(result.stdout.strip()).resolve(strict=True)
