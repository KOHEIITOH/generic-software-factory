"""Explicit, scoped authorization for AI workspace writes.

This is an authorization boundary, not process isolation. A separate OS sandbox
must still be provided before executing untrusted agent tools.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from sf_factory.policy import (
    Capability,
    ExecutionPolicy,
    ExecutionRequest,
    PolicyDecision,
)


class AuthorizedOperation(StrEnum):
    IMPLEMENT = "implement"
    PUSH = "push"
    CREATE_DRAFT_PR = "create-draft-pr"
    MERGE = "merge"
    DEPLOY = "deploy"


@dataclass(frozen=True)
class ExecutionGrant:
    issue_key: str
    repository: str
    operation: AuthorizedOperation
    approved: bool = False


def authorize_operation(
    grant: ExecutionGrant,
    *,
    issue_key: str,
    repository: str,
    operation: AuthorizedOperation,
    isolated: bool = False,
    timeout_seconds: int = 120,
) -> None:
    """Fail closed unless the grant matches the exact issue, repo and action."""
    if not issue_key or not repository:
        raise PermissionError("issue and repository are required")
    if not grant.approved:
        raise PermissionError("explicit user approval required")
    if grant.issue_key != issue_key or grant.repository != repository:
        raise PermissionError("grant scope does not match issue and repository")
    if grant.operation != operation:
        raise PermissionError("grant does not authorize this operation")
    if operation is AuthorizedOperation.IMPLEMENT:
        if not isolated:
            raise PermissionError("workspace writes require process isolation")
        capability = Capability.WORKSPACE_WRITE
        policy = ExecutionPolicy(allow_workspace_write=True)
    else:
        capability = Capability.EXTERNAL_ACTION
        policy = ExecutionPolicy(allow_external_actions=True)
    result = policy.evaluate(
        ExecutionRequest(
            capability=capability,
            approved=True,
            timeout_seconds=timeout_seconds,
        )
    )
    if result.decision is not PolicyDecision.ALLOW:
        raise PermissionError(f"execution denied by policy: {result.reason}")
