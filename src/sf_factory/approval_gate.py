"""Provider-neutral, explicit approval gate for proposed write actions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ActionKind(str, Enum):
    WRITE_FILE = "write_file"
    RUN_COMMAND = "run_command"
    RELEASE = "release"


@dataclass(frozen=True)
class ProposedAction:
    task_id: str
    kind: ActionKind
    summary: str

    def __post_init__(self) -> None:
        if not self.task_id.strip() or not self.summary.strip():
            raise ValueError("task_id and summary are required")
        if not isinstance(self.kind, ActionKind):
            raise ValueError("kind must be an ActionKind")


@dataclass(frozen=True)
class ApprovalDecision:
    action: ProposedAction
    approved: bool
    reviewer: str

    def __post_init__(self) -> None:
        if type(self.approved) is not bool:
            raise ValueError("approved must be a boolean")
        if not self.reviewer.strip():
            raise ValueError("reviewer is required")


def require_approval(action: ProposedAction, decision: ApprovalDecision | None) -> None:
    """Fail closed unless the exact proposed action was explicitly approved."""
    if decision is None or not decision.approved or decision.action != action:
        raise PermissionError("Explicit approval for this action is required")
