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
    codex_path = shutil.which("codex")
    git_path = shutil.which("git")
    copilot_path = shutil.which("copilot")
    copilot_sdk_installed = importlib.util.find_spec("copilot") is not None

    try:
        copilot_sdk_version = importlib.metadata.version("github-copilot-sdk")
    except importlib.metadata.PackageNotFoundError:
        copilot_sdk_version = "not installed (optional)"

    return [
        Check(
            name="Python",
            ok=python_ok,
            detail=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
            + (" (3.11+ supported)" if python_ok else " (requires 3.11+)"),
        ),
        Check(name="Git", ok=git_path is not None, detail=git_path or "not found"),
        Check(
            name="Codex CLI",
            ok=codex_path is not None,
            detail=codex_path or "not found (required for the initial Runtime)",
        ),
        Check(
            name="Copilot CLI",
            ok=copilot_path is not None,
            detail=copilot_path or "not found (optional)",
            required=False,
        ),
        Check(
            name="Copilot Python SDK",
            ok=copilot_sdk_installed,
            detail=copilot_sdk_version,
            required=False,
        ),
        Check(
            name="Docker",
            ok=shutil.which("docker") is not None,
            detail=shutil.which("docker") or "not found (optional at this stage)",
            required=False,
        ),
        Check(
            name="GitHub CLI",
            ok=shutil.which("gh") is not None,
            detail=shutil.which("gh") or "not found (optional at this stage)",
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

    print("Local prerequisites look good. Runtime authentication is checked by its smoke test.")
    return 0
