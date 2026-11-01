"""Codex CLI Agent Runtime adapter."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Literal

from sf_factory.runtime import RuntimeErrorKind, RuntimeResult

SandboxMode = Literal["read-only", "workspace-write"]


class CodexCliRuntime:
    """Run Codex through its supported non-interactive codex exec command."""

    def __init__(self, executable: str = "codex", sandbox: SandboxMode = "read-only"):
        self.executable = executable
        self.sandbox = sandbox

    def is_available(self) -> bool:
        """Return whether the configured Codex executable is on PATH."""
        return shutil.which(self.executable) is not None

    def execute(
        self,
        *,
        prompt: str,
        workspace: Path,
        timeout_seconds: int = 600,
    ) -> RuntimeResult:
        """Execute a prompt and normalize Codex JSONL events into a result."""
        if not prompt.strip():
            raise ValueError("prompt must not be empty")
        if timeout_seconds < 1:
            raise ValueError("timeout_seconds must be positive")

        resolved_workspace = workspace.expanduser().resolve()
        if not resolved_workspace.is_dir():
            raise ValueError(f"workspace is not a directory: {resolved_workspace}")

        command = [
            self.executable,
            "exec",
            "--json",
            "--ephemeral",
            "--skip-git-repo-check",
            "--sandbox",
            self.sandbox,
            "--cd",
            str(resolved_workspace),
            prompt,
        ]

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
                runtime="codex",
                status="timed_out",
                output="",
                exit_code=None,
                stderr=_as_text(exc.stderr),
                error_kind="timeout",
                error_message="Codex execution timed out.",
            )

        session_id: str | None = None
        messages: list[str] = []
        error_messages: list[str] = []
        protocol_errors: list[str] = []

        for line_number, line in enumerate(completed.stdout.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                protocol_errors.append(f"Invalid JSONL event at line {line_number}")
                continue

            if not isinstance(event, dict):
                protocol_errors.append(f"Unexpected JSONL event at line {line_number}")
                continue

            event_type = event.get("type")
            if event_type == "thread.started":
                value = event.get("thread_id")
                if isinstance(value, str):
                    session_id = value
            elif event_type == "item.completed":
                item = event.get("item")
                if isinstance(item, dict):
                    if item.get("type") == "agent_message":
                        message = item.get("text")
                        if isinstance(message, str):
                            messages.append(message)
                    elif item.get("type") == "error":
                        message = item.get("message")
                        if isinstance(message, str):
                            error_messages.append(message)
            elif event_type == "error":
                message = event.get("message")
                if isinstance(message, str):
                    error_messages.append(message)
            elif event_type == "turn.failed":
                error = event.get("error")
                if isinstance(error, dict):
                    message = error.get("message")
                    if isinstance(message, str):
                        error_messages.append(message)

        output = "\n".join(messages).strip()
        unique_errors = list(dict.fromkeys(error_messages))
        error_message = "\n".join(unique_errors) or None
        error_kind = _classify_error(error_message) if error_message else None
        stderr = completed.stderr
        if protocol_errors:
            stderr = "\n".join([stderr, *protocol_errors]).strip()

        succeeded = (
            completed.returncode == 0
            and bool(output)
            and not protocol_errors
            and not error_messages
        )
        if not succeeded and error_message is None and completed.returncode != 0:
            error_message = stderr or "Codex exited with a non-zero status."
            error_kind = _classify_error(error_message)

        return RuntimeResult(
            runtime="codex",
            status="succeeded" if succeeded else "failed",
            output=output,
            exit_code=completed.returncode,
            session_id=session_id,
            stderr=stderr,
            error_kind=error_kind,
            error_message=error_message,
        )


def _classify_error(message: str) -> RuntimeErrorKind:
    """Map vendor-specific error text to a provider-neutral error category."""
    normalized = message.lower()
    if "usage limit" in normalized or "hit your usage limit" in normalized:
        return "usage_limit"
    if "rate limit" in normalized or "rate_limit" in normalized:
        return "rate_limit"
    if any(
        marker in normalized
        for marker in ("unauthorized", "authentication", "not logged in", "login required")
    ):
        return "authentication"
    if "model_not_found" in normalized or (
        "model" in normalized and "not supported" in normalized
    ):
        return "model_not_found"
    return "runtime_error"


def _as_text(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""
