"""Fail-closed preflight for workspace-bound actions; never executes an action.

This is not an authorization boundary. The caller must establish trusted
workspace ownership, sandbox isolation, allowlists, and user identity.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from sf_factory.risk_policy import ActionContext, Decision, Operation, evaluate_policy


class GuardStatus(StrEnum):
    READY = "ready"
    APPROVAL_REQUIRED = "approval_required"
    DENIED = "denied"


@dataclass(frozen=True)
class GuardResult:
    status: GuardStatus
    reason: str

    @property
    def executable(self) -> bool:
        return self.status is GuardStatus.READY


def preflight(
    action: ActionContext,
    *,
    workspace: Path,
    target: Path | None = None,
) -> GuardResult:
    """Classify a proposed action; do not invoke tools or grant capabilities."""
    decision = evaluate_policy(action)
    if decision is Decision.DENY:
        return GuardResult(GuardStatus.DENIED, "risk_policy_denied")
    if decision is Decision.REQUIRE_APPROVAL:
        return GuardResult(GuardStatus.APPROVAL_REQUIRED, "trusted_approval_not_implemented")

    # No automatic filesystem mutations without a concrete target.
    if action.operation in (Operation.WRITE_FILE, Operation.COMMIT) and target is None:
        return GuardResult(GuardStatus.DENIED, "target_required")

    if target is not None:
        if not target.is_absolute() or not workspace.is_absolute():
            return GuardResult(GuardStatus.DENIED, "absolute_paths_required")
        try:
            root = workspace.resolve(strict=True)
            if not root.is_dir():
                return GuardResult(GuardStatus.DENIED, "workspace_not_directory")
            resolved = target.resolve(strict=False)
            relative = resolved.relative_to(root)
            if relative == Path("."):
                return GuardResult(GuardStatus.DENIED, "workspace_root_is_not_target")
        except (OSError, RuntimeError, ValueError):
            return GuardResult(GuardStatus.DENIED, "target_outside_workspace")

    return GuardResult(GuardStatus.READY, "preflight_only_no_execution")
