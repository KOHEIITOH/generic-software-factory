"""Harmless, read-only connectivity smoke test for Grok Build."""

from __future__ import annotations

import tempfile
from pathlib import Path

from sf_factory.grok_cli import GrokBuildCliRuntime

EXPECTED_RESPONSE = "FACTORY_GROK_SMOKE_OK"


def run_smoke_test() -> int:
    """Verify Grok Build can answer in an empty temporary workspace."""
    runtime = GrokBuildCliRuntime()
    if not runtime.is_available():
        print("Grok Build CLI was not found. Install it and ensure grok is on PATH.")
        return 1

    print("Starting Grok Build smoke test (read-only tools, temporary workspace)...")
    with tempfile.TemporaryDirectory(prefix="sf-grok-smoke-") as directory:
        result = runtime.execute(
            prompt=f"Do not inspect or modify files. Reply with exactly: {EXPECTED_RESPONSE}",
            workspace=Path(directory),
            timeout_seconds=120,
        )

    if result.output:
        print("\nGrok Build response:")
        print(result.output)
    if result.status != "succeeded" or result.output.strip() != EXPECTED_RESPONSE:
        print("\nGrok Build smoke test failed.")
        if result.error_kind:
            print(f"Error category: {result.error_kind}")
        if result.error_message:
            print(f"Reason: {result.error_message}")
        if result.stderr:
            print(f"Details: {result.stderr}")
        return 1

    print("\nGrok Build smoke test completed.")
    return 0
