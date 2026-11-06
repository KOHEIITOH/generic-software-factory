"""Fail-closed preflight for a future containerized agent executor.

Checking Docker availability is NOT proof of sandbox security. The executor
must enforce mounts, network, capabilities, credentials and resource limits.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class SandboxPreflight:
    available: bool
    reason: str


def docker_preflight(*, timeout_seconds: int = 5) -> SandboxPreflight:
    """Check that Docker is installed and its daemon responds; run no agent."""
    if timeout_seconds < 1 or timeout_seconds > 30:
        return SandboxPreflight(False, "invalid preflight timeout")
    executable = shutil.which("docker")
    if executable is None:
        return SandboxPreflight(False, "Docker CLI not installed")
    try:
        result = subprocess.run(
            [executable, "info", "--format", "{{.ServerVersion}}"],
            capture_output=True, text=True, timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return SandboxPreflight(False, "Docker daemon unavailable")
    if result.returncode != 0 or not result.stdout.strip():
        return SandboxPreflight(False, "Docker daemon unavailable")
    return SandboxPreflight(True, "Docker daemon reachable; isolation not verified")
