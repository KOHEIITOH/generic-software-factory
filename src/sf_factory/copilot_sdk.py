"""GitHub Copilot SDK Agent Runtime adapter."""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

from sf_factory.runtime import RuntimeErrorKind, RuntimeResult


class CopilotSdkRuntime:
    """Run one Copilot SDK session without exposing SDK types to the Factory."""

    def is_available(self) -> bool:
        """Return whether the optional Copilot SDK is installed."""
        return importlib.util.find_spec("copilot") is not None

    def execute(
        self,
        *,
        prompt: str,
        workspace: Path,
        timeout_seconds: int = 600,
    ) -> RuntimeResult:
        """Execute a prompt with no tools and normalize the SDK response."""
        if not prompt.strip():
            raise ValueError("prompt must not be empty")
        if timeout_seconds < 1:
            raise ValueError("timeout_seconds must be positive")

        resolved_workspace = workspace.expanduser().resolve()
        if not resolved_workspace.is_dir():
            raise ValueError(f"workspace is not a directory: {resolved_workspace}")

        try:
            from copilot import CopilotClient  # type: ignore[reportMissingImports]
            from copilot.session_events import (  # type: ignore[reportMissingImports]
                AssistantMessageData,
            )
        except ImportError:
            return RuntimeResult(
                runtime="copilot",
                status="failed",
                output="",
                exit_code=None,
                error_kind="runtime_error",
                error_message=(
                    "GitHub Copilot SDK is not installed. Install it with: "
                    "uv sync --extra dev --extra copilot"
                ),
            )

        try:
            response, session_id = asyncio.run(
                asyncio.wait_for(
                    _run_session(
                        CopilotClient,
                        prompt=prompt,
                        workspace=resolved_workspace,
                        timeout_seconds=timeout_seconds,
                    ),
                    timeout=timeout_seconds,
                )
            )
        except TimeoutError:
            return RuntimeResult(
                runtime="copilot",
                status="timed_out",
                output="",
                exit_code=None,
                error_kind="timeout",
                error_message="Copilot SDK execution timed out.",
            )
        except Exception as exc:
            error_kind = _classify_error(str(exc))
            return RuntimeResult(
                runtime="copilot",
                status="failed",
                output="",
                exit_code=None,
                error_kind=error_kind,
                error_message=_error_message(error_kind, type(exc).__name__),
            )

        response_data = getattr(response, "data", None)
        if response is None or not isinstance(response_data, AssistantMessageData):
            return RuntimeResult(
                runtime="copilot",
                status="failed",
                output="",
                exit_code=None,
                session_id=session_id,
                error_kind="runtime_error",
                error_message="Copilot completed without an assistant message.",
            )

        output = getattr(response_data, "content", None)
        if not isinstance(output, str) or not output.strip():
            return RuntimeResult(
                runtime="copilot",
                status="failed",
                output="",
                exit_code=None,
                session_id=session_id,
                error_kind="runtime_error",
                error_message="Copilot completed without a response.",
            )

        return RuntimeResult(
            runtime="copilot",
            status="succeeded",
            output=output.strip(),
            exit_code=0,
            session_id=session_id,
        )


async def _run_session(
    client_type: type,
    *,
    prompt: str,
    workspace: Path,
    timeout_seconds: int,
) -> tuple[object | None, str | None]:
    async with client_type() as client:
        async with await client.create_session(
            available_tools=[],
            working_directory=str(workspace),
            enable_file_change_tracking=False,
        ) as session:
            response = await session.send_and_wait(prompt, timeout=timeout_seconds)
            session_id = getattr(session, "session_id", None)
            return response, session_id if isinstance(session_id, str) else None


def _classify_error(message: str) -> RuntimeErrorKind:
    """Map SDK failures to the Factory's normalized error categories."""
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
    if "timeout" in normalized or "timed out" in normalized:
        return "timeout"
    return "runtime_error"


def _error_message(error_kind: RuntimeErrorKind, exception_name: str) -> str:
    """Return a safe diagnostic without persisting SDK exception contents."""
    messages = {
        "usage_limit": "Copilot usage limit reached.",
        "rate_limit": "Copilot rate limit exceeded.",
        "authentication": "Copilot authentication failed. Sign in with `copilot login`.",
        "model_not_found": "The requested Copilot model is unavailable.",
        "timeout": "Copilot SDK execution timed out.",
        "runtime_error": f"Copilot SDK execution failed ({exception_name}).",
    }
    return messages[error_kind]
