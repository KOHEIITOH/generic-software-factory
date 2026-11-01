"""Grok Build CLI Agent Runtime adapter."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from sf_factory.runtime import RuntimeErrorKind, RuntimeResult

DEFAULT_READ_ONLY_TOOLS = ("read_file", "grep", "list_dir")


class GrokBuildCliRuntime:
    """Run Grok Build in headless JSON mode with an explicit read-only tool set."""

    def __init__(
        self,
        executable: str = "grok",
        model: str | None = None,
        tools: tuple[str, ...] = DEFAULT_READ_ONLY_TOOLS,
    ) -> None:
        self.executable = executable
        self.model = model
        self.tools = tools

    def is_available(self) -> bool:
        """Return whether the configured Grok executable is on PATH."""
        return shutil.which(self.executable) is not None

    def execute(
        self,
        *,
        prompt: str,
        workspace: Path,
        timeout_seconds: int = 600,
    ) -> RuntimeResult:
        """Execute one headless prompt and normalize Grok's JSON response."""
        if not prompt.strip():
            raise ValueError("prompt must not be empty")
        if timeout_seconds < 1:
            raise ValueError("timeout_seconds must be positive")
        if not self.tools:
            raise ValueError("tools must contain at least one explicitly allowed tool")
        if any(not tool.strip() or "," in tool for tool in self.tools):
            raise ValueError("tool names must be non-empty and must not contain commas")

        resolved_workspace = workspace.expanduser().resolve()
        if not resolved_workspace.is_dir():
            raise ValueError(f"workspace is not a directory: {resolved_workspace}")

        command = [
            self.executable,
            "-p",
            prompt,
            "--output-format",
            "json",
            "--cwd",
            str(resolved_workspace),
            "--tools",
            ",".join(self.tools),
            "--disallowed-tools",
            "Agent",
            "--deny",
            "MCPTool(*)",
            "--no-auto-update",
        ]
        if self.model:
            command.extend(["--model", self.model])

        try:
            completed = subprocess.run(
                command,
                cwd=resolved_workspace,
                text=True,
                capture_output=True,
                check=False,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            return RuntimeResult(
                runtime="grok-build",
                status="timed_out",
                output="",
                exit_code=None,
                stderr=_as_text(exc.stderr),
                error_kind="timeout",
                error_message="Grok Build execution timed out.",
            )

        output = ""
        session_id: str | None = None
        error_message: str | None = None
        protocol_error: str | None = None

        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError:
            payload = None
            if completed.stdout.strip():
                protocol_error = "Grok Build returned invalid JSON output."

        if isinstance(payload, dict):
            text = payload.get("text")
            if isinstance(text, str):
                output = text.strip()
            session = payload.get("sessionId")
            if isinstance(session, str):
                session_id = session
            error = payload.get("error")
            if isinstance(error, str):
                error_message = error
            elif isinstance(error, dict):
                message = error.get("message")
                if isinstance(message, str):
                    error_message = message
        elif payload is not None:
            protocol_error = "Grok Build returned an unexpected JSON response."

        stderr = completed.stderr
        if protocol_error:
            stderr = "\n".join(part for part in (stderr, protocol_error) if part)

        if completed.returncode != 0 and error_message is None:
            error_message = stderr.strip() or "Grok Build exited with a non-zero status."
        if completed.returncode == 0 and not output and error_message is None:
            error_message = "Grok Build completed without a response."

        succeeded = completed.returncode == 0 and bool(output) and not protocol_error
        return RuntimeResult(
            runtime="grok-build",
            status="succeeded" if succeeded else "failed",
            output=output,
            exit_code=completed.returncode,
            session_id=session_id,
            stderr=stderr,
            error_kind=_classify_error(error_message) if error_message else None,
            error_message=error_message,
        )


def _classify_error(message: str) -> RuntimeErrorKind:
    """Map common CLI/provider errors to the Factory's normalized categories."""
    normalized = message.lower()
    if "usage limit" in normalized or "quota" in normalized:
        return "usage_limit"
    if "rate limit" in normalized or "rate_limit" in normalized or "429" in normalized:
        return "rate_limit"
    if any(
        marker in normalized
        for marker in ("unauthorized", "authentication", "not logged in", "login required")
    ):
        return "authentication"
    if "model_not_found" in normalized or (
        "model" in normalized and ("not found" in normalized or "not supported" in normalized)
    ):
        return "model_not_found"
    return "runtime_error"


def _as_text(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""
