"""Opt-in, isolated code-editing smoke test using a bundled safe fixture."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from sf_factory.codex_cli import CodexCliRuntime

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "calculator"
PROMPT = (
    "In calculator.py, implement add(a, b) so it returns a + b. "
    "Only edit calculator.py. Do not modify tests, run shell commands, "
    "access other directories, or use the network."
)


def _snapshot(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
        and "__pycache__" not in path.parts and ".pytest_cache" not in path.parts
    }


def run_dev_smoke(*, runtime: CodexCliRuntime | None = None) -> int:
    """Copy only our fixture to a temporary workspace and run a bounded edit/test cycle."""
    if not FIXTURE.is_dir():
        print("Bundled calculator fixture missing.")
        return 2
    with tempfile.TemporaryDirectory(prefix="sf-dev-smoke-") as directory:
        workspace = Path(directory)
        shutil.copytree(FIXTURE, workspace, dirs_exist_ok=True)
        before = _snapshot(workspace)
        adapter = runtime or CodexCliRuntime(sandbox="workspace-write")
        try:
            result = adapter.execute(prompt=PROMPT, workspace=workspace, timeout_seconds=180)
        except (OSError, ValueError) as exc:
            print(f"Runtime unavailable: {exc}")
            return 1
        after = _snapshot(workspace)
        changed = sorted(
            path for path in before.keys() | after.keys() if before.get(path) != after.get(path)
        )
        if result.status != "succeeded":
            print(json.dumps({"status": result.status, "error": result.error_message}))
            return 1
        if changed != ["calculator.py"]:
            print(json.dumps({"status": "rejected", "changed_files": changed}))
            return 1
        try:
            test = subprocess.run(
                ["python", "-m", "unittest", "discover", "-s", ".", "-p", "test_*.py"],
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(f"Test execution failed: {exc}")
            return 1
        success = test.returncode == 0
        print(
            json.dumps(
                {
                    "status": "succeeded" if success else "failed",
                    "changed_files": changed,
                    "tests_passed": success,
                    "test_output": (test.stdout + test.stderr)[-3000:],
                },
                indent=2,
            )
        )
        return 0 if success else 1
