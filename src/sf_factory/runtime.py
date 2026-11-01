"""Small, provider-neutral contracts shared by Agent Runtime adapters."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

RuntimeStatus = Literal["succeeded", "failed", "timed_out"]
RuntimeErrorKind = Literal[
    "usage_limit",
    "rate_limit",
    "authentication",
    "model_not_found",
    "timeout",
    "runtime_error",
]


@dataclass(frozen=True)
class RuntimeResult:
    """Normalized result returned by an Agent Runtime."""

    runtime: str
    status: RuntimeStatus
    output: str
    exit_code: int | None
    session_id: str | None = None
    stderr: str = ""
    error_kind: RuntimeErrorKind | None = None
    error_message: str | None = None


class AgentRuntime(Protocol):
    """Minimal synchronous contract for a single non-interactive agent run."""

    def execute(
        self,
        *,
        prompt: str,
        workspace: Path,
        timeout_seconds: int = 600,
    ) -> RuntimeResult:
        ...
