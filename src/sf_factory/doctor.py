"""Local environment diagnostics."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import shutil
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str
    required: bool = True


def collect_checks() -> list[Check]:
    """Collect local prerequisites without invoking external services."""
    python_ok = sys.version_info >= (3, 11)
    sdk_installed = importlib.util.find_spec("copilot") is not None

    try:
        sdk_version = importlib.metadata.version("github-copilot-sdk")
    except importlib.metadata.PackageNotFoundError:
        sdk_version = "not installed"

    return [
        Check(
            name="Python",
            ok=python_ok,
            detail=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
            + (" (3.11+ supported)" if python_ok else " (requires 3.11+)"),
        ),
        Check(
            name="Git",
            ok=shutil.which("git") is not None,
            detail=shutil.which("git") or "not found",
        ),
        Check(
            name="Copilot CLI",
            ok=shutil.which("copilot") is not None,
            detail=(
                shutil.which("copilot")
                or "not found (install and authenticate before the smoke test)"
            ),
        ),
        Check(
            name="Copilot Python SDK",
            ok=sdk_installed,
            detail=sdk_version,
        ),
        Check(
            name="Docker",
            ok=shutil.which("docker") is not None,
            detail=shutil.which("docker") or "not found (optional for this smoke test)",
            required=False,
        ),
        Check(
            name="GitHub CLI",
            ok=shutil.which("gh") is not None,
            detail=shutil.which("gh") or "not found (optional for this smoke test)",
            required=False,
        ),
    ]


def run_doctor() -> int:
    checks = collect_checks()
    print("Generic Software Factory — environment doctor\n")

    for check in checks:
        status = "OK" if check.ok else ("MISSING" if check.required else "OPTIONAL")
        print(f"[{status:8}] {check.name}: {check.detail}")

    required_failed = any(not check.ok and check.required for check in checks)
    print()
    if required_failed:
        print("Some required prerequisites are missing.")
        return 1

    print("Local prerequisites look good. Copilot authentication is checked by the smoke test.")
    return 0
