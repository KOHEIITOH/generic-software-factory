"""Fail-closed authorization policy for Factory operations.

This is application-level authorization, not an OS sandbox.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Capability(StrEnum):
    READ_ONLY = "read-only"
    WORKSPACE_WRITE = "workspace-write"
    EXTERNAL_ACTION = "external-action"


class PolicyDecision(StrEnum):
    ALLOW = "allow"
    REQUIRE_APPROVAL = "require-approval"
    DENY = "deny"


@dataclass(frozen=True)
class ExecutionRequest:
    capability: Capability
    approved: bool = False
    timeout_seconds: int = 120
    retry_count: int = 0


@dataclass(frozen=True)
class PolicyResult:
    decision: PolicyDecision
    reason: str

    @property
    def allowed(self) -> bool:
        return self.decision is PolicyDecision.ALLOW


@dataclass(frozen=True)
class ExecutionPolicy:
    """Default-deny for side effects; approvals never bypass unavailable isolation."""

    max_timeout_seconds: int = 600
    max_retries: int = 2
    allow_workspace_write: bool = False
    allow_external_actions: bool = False

    def evaluate(self, request: ExecutionRequest) -> PolicyResult:
        if request.timeout_seconds < 1 or request.timeout_seconds > self.max_timeout_seconds:
            return PolicyResult(PolicyDecision.DENY, "execution timeout outside policy limits")
        if request.retry_count < 0 or request.retry_count > self.max_retries:
            return PolicyResult(PolicyDecision.DENY, "retry count outside policy limits")
        if request.capability is Capability.READ_ONLY:
            return PolicyResult(PolicyDecision.ALLOW, "read-only execution permitted")
        if request.capability is Capability.WORKSPACE_WRITE:
            if not self.allow_workspace_write:
                return PolicyResult(PolicyDecision.DENY, "workspace write disabled by policy")
            if not request.approved:
                return PolicyResult(PolicyDecision.REQUIRE_APPROVAL, "workspace write requires approval")
            return PolicyResult(PolicyDecision.ALLOW, "approved workspace write")
        if request.capability is Capability.EXTERNAL_ACTION:
            if not self.allow_external_actions:
                return PolicyResult(PolicyDecision.DENY, "external actions disabled by policy")
            if not request.approved:
                return PolicyResult(PolicyDecision.REQUIRE_APPROVAL, "external action requires approval")
            return PolicyResult(PolicyDecision.ALLOW, "approved external action")
        return PolicyResult(PolicyDecision.DENY, "unknown capability")
