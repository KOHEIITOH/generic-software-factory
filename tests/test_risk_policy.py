"""Conservative risk policy tests; never perform real operations."""

import pytest

from sf_factory.risk_policy import (
    ActionContext,
    Decision,
    Environment,
    Operation,
    evaluate_policy,
)


@pytest.mark.parametrize("operation", [Operation.READ, Operation.ANALYZE])
def test_read_operations_require_verified_scope(operation):
    assert evaluate_policy(ActionContext(operation, Environment.DEVELOPMENT)) is Decision.DENY
    assert evaluate_policy(ActionContext(
        operation, Environment.DEVELOPMENT, scope_verified=True
    )) is Decision.AUTO


@pytest.mark.parametrize("operation", [
    Operation.WRITE_FILE, Operation.RUN_CHECK, Operation.COMMIT, Operation.CREATE_PR,
])
def test_routine_work_is_auto_only_with_verified_isolation(operation):
    action = ActionContext(
        operation, Environment.ISOLATED,
        sandbox_verified=True, scope_verified=True, allowlisted=True,
    )
    assert evaluate_policy(action) is Decision.AUTO
    assert evaluate_policy(ActionContext(
        operation, Environment.ISOLATED, sandbox_verified=False,
        scope_verified=True, allowlisted=True,
    )) is Decision.DENY
    assert evaluate_policy(ActionContext(
        operation, Environment.DEVELOPMENT, sandbox_verified=True,
        scope_verified=True, allowlisted=True,
    )) is Decision.DENY


@pytest.mark.parametrize("operation", [
    Operation.MERGE_PR, Operation.DEPLOY,
    Operation.CHANGE_SECRET, Operation.CHANGE_PERMISSION,
])
def test_sensitive_operations_require_approval(operation):
    assert evaluate_policy(ActionContext(operation, Environment.PRODUCTION)) is (
        Decision.REQUIRE_APPROVAL
    )


def test_unknown_commands_and_production_writes_are_denied():
    assert evaluate_policy(ActionContext(
        Operation.RUN_COMMAND, Environment.ISOLATED,
        sandbox_verified=True, scope_verified=True, allowlisted=True,
    )) is Decision.DENY
    assert evaluate_policy(ActionContext(
        Operation.WRITE_FILE, Environment.PRODUCTION,
        sandbox_verified=True, scope_verified=True, allowlisted=True,
    )) is Decision.DENY
