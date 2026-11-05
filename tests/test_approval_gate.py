"""Approval gate tests; no filesystem writes or commands are executed."""

import pytest

from sf_factory.approval_gate import (
    ActionKind,
    ApprovalDecision,
    ProposedAction,
    require_approval,
)


def test_requires_matching_explicit_approval():
    action = ProposedAction("task-1", ActionKind.WRITE_FILE, "Update README")
    with pytest.raises(PermissionError):
        require_approval(action, None)
    with pytest.raises(PermissionError):
        require_approval(action, ApprovalDecision(action, False, "reviewer"))
    with pytest.raises(PermissionError):
        require_approval(
            action,
            ApprovalDecision(
                ProposedAction("task-2", ActionKind.WRITE_FILE, "Update README"),
                True,
                "reviewer",
            ),
        )
    require_approval(action, ApprovalDecision(action, True, "reviewer"))


def test_rejects_invalid_action_and_decision():
    with pytest.raises(ValueError):
        ProposedAction("", ActionKind.RELEASE, "Release")
    with pytest.raises(ValueError):
        ProposedAction("task", ActionKind.RUN_COMMAND, "")
    action = ProposedAction("task", ActionKind.RELEASE, "Release")
    with pytest.raises(ValueError):
        ApprovalDecision(action, True, "")
    with pytest.raises(ValueError):
        ApprovalDecision(action, 1, "reviewer")
