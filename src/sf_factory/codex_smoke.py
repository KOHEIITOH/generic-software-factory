"""Harmless, read-only connectivity smoke test for Codex CLI."""

from __future__ import annotations

import tempfile
from pathlib import Path

from sf_factory.codex_cli import CodexCliRuntime

EXPECTED_RESPONSE = "FACTORY_CODEX_SMOKE_OK"


def run_smoke_test() -> int:
    """Verify Codex can answer a prompt in an empty temporary workspace."""
    runtime = CodexCliRuntime(sandbox="read-only")
    if not runtime.is_available():
        print("Codex CLI was not found. Install it and ensure codex is on PATH.")
        return 1

    print("Starting Codex CLI smoke test (read-only, temporary workspace)...")
    with tempfile.TemporaryDirectory(prefix="sf-codex-smoke-") as directory:
        result = runtime.execute(
            prompt=f"Do not inspect or modify files. Reply with exactly: {EXPECTED_RESPONSE}",
            workspace=Path(directory),
            timeout_seconds=120,
        )

    if result.output:
        print("\nCodex response:")
        print(result.output)
    if result.status != "succeeded" or result.output.strip() != EXPECTED_RESPONSE:
        print("\nCodex smoke test failed.")
        if result.error_kind:
            print(f"Error category: {result.error_kind}")
        if result.error_message:
            print(f"Reason: {result.error_message}")
        if result.stderr:
            print(f"Details: {result.stderr}")
        return 1

    print("\nCodex smoke test completed.")
    return 0
