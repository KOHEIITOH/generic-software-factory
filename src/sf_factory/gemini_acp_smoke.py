"""Opt-in Gemini CLI ACP smoke test; never runs on import or in CI."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path

from sf_factory.acp import AcpCommand, AcpRuntime


def run_gemini_acp_smoke(*, timeout_seconds: int = 90) -> int:
    if timeout_seconds < 1:
        raise ValueError("timeout must be positive")
    if shutil.which("gemini") is None:
        print("Gemini CLI not found in PATH")
        return 2

    # An isolated directory limits accidental workspace exposure, but does not
    # prevent access to files outside it. Do not use with privileged credentials.
    with tempfile.TemporaryDirectory(prefix="sf-gemini-acp-") as temporary:
        workspace = Path(temporary)
        (workspace / "README.txt").write_text(
            "This is a disposable, non-sensitive ACP smoke-test workspace.\n",
            encoding="utf-8",
        )
        runtime = AcpRuntime(
            AcpCommand(("gemini", "--acp", "--approval-mode", "plan")),
            name="gemini-acp",
        )
        result = runtime.execute(
            prompt=(
                "Reply with exactly GEMINI_ACP_OK. "
                "Do not read files, use tools, or execute commands."
            ),
            workspace=workspace,
            timeout_seconds=timeout_seconds,
        )
        print(json.dumps({
            "runtime": result.runtime,
            "status": result.status,
            "output": result.output[:500],
            "error_kind": result.error_kind,
            "error_message": result.error_message,
        }, ensure_ascii=False, indent=2))
        return 0 if result.status == "succeeded" and "GEMINI_ACP_OK" in result.output else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Opt-in Gemini CLI ACP smoke test")
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args()
    return run_gemini_acp_smoke(timeout_seconds=args.timeout)


if __name__ == "__main__":
    raise SystemExit(main())
