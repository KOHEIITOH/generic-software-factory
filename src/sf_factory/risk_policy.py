"""Conservative risk-based policy classification; no execution authority."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Decision(StrEnum):
    AUTO = "auto"
    REQUIRE_APPROVAL = "require_approval"
    DENY = "deny"


class Operation(StrEnum):
    READ = "read"
    ANALYZE = "analyze"
    WRITE_FILE = "write_file"
    RUN_CHECK = "run_check"
    RUN_COMMAND = "run_command"
    COMMIT = "commit"
    CREATE_PR = "create_pr"
    MERGE_PR = "merge_pr"
    DEPLOY = "deploy"
    CHANGE_SECRET = "change_secret"
    CHANGE_PERMISSION = "change_permission"


class Environment(StrEnum):
    ISOLATED = "isolated"
    DEVELOPMENT = "development"
    PRODUCTION = "production"


@dataclass(frozen=True)
class ActionContext:
    operation: Operation
    environment: Environment
    sandbox_verified: bool = False
    scope_verified: bool = False
    allowlisted: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.operation, Operation):
            raise ValueError("Invalid operation")
        if not isinstance(self.environment, Environment):
            raise ValueError("Invalid environment")
        for name in ("sandbox_verified", "scope_verified", "allowlisted"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be boolean")


def evaluate_policy(action: ActionContext) -> Decision:
    """Classify actions; this does not grant capabilities or prove approval."""
    if action.operation in (Operation.CHANGE_SECRET, Operation.CHANGE_PERMISSION):
        return Decision.REQUIRE_APPROVAL
    if action.operation in (Operation.MERGE_PR, Operation.DEPLOY):
        return Decision.REQUIRE_APPROVAL
    if action.environment is Environment.PRODUCTION:
        return Decision.DENY
    if action.operation in (Operation.READ, Operation.ANALYZE):
        return Decision.AUTO if action.scope_verified else Decision.DENY
    if action.operation in (
        Operation.WRITE_FILE,
        Operation.RUN_CHECK,
        Operation.COMMIT,
        Operation.CREATE_PR,
    ):
        if (action.environment is Environment.ISOLATED
                and action.sandbox_verified and action.scope_verified
                and action.allowlisted):
            return Decision.AUTO
        return Decision.DENY
    return Decision.DENY
