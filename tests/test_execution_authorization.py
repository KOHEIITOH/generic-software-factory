"""No operation can inherit approval for a different action or repository."""

import pytest

from sf_factory.execution_authorization import (
    AuthorizedOperation,
    ExecutionGrant,
    authorize_operation,
)


def grant(operation: AuthorizedOperation = AuthorizedOperation.IMPLEMENT) -> ExecutionGrant:
    return ExecutionGrant("task-1", "org/repo", operation, approved=True)


def test_implementation_requires_isolation() -> None:
    with pytest.raises(PermissionError, match="isolation"):
        authorize_operation(
            grant(), task_id="task-1", repository="org/repo",
            operation=AuthorizedOperation.IMPLEMENT,
        )


def test_approved_isolated_implementation() -> None:
    authorize_operation(
        grant(), task_id="task-1", repository="org/repo",
        operation=AuthorizedOperation.IMPLEMENT, isolated=True,
    )


@pytest.mark.parametrize("operation", [
    AuthorizedOperation.PUSH,
    AuthorizedOperation.CREATE_DRAFT_PR,
    AuthorizedOperation.MERGE,
    AuthorizedOperation.DEPLOY,
])
def test_implementation_approval_never_authorizes_external_action(
    operation: AuthorizedOperation,
) -> None:
    with pytest.raises(PermissionError, match="operation"):
        authorize_operation(
            grant(), task_id="task-1", repository="org/repo", operation=operation,
            isolated=True,
        )


def test_approval_must_match_task_and_repository() -> None:
    for task, repo in [("task-2", "org/repo"), ("task-1", "other/repo")]:
        with pytest.raises(PermissionError, match="scope"):
            authorize_operation(
                grant(), task_id=task, repository=repo,
                operation=AuthorizedOperation.IMPLEMENT, isolated=True,
            )


def test_unapproved_grant_denied() -> None:
    with pytest.raises(PermissionError, match="approval"):
        authorize_operation(
            ExecutionGrant("task-1", "org/repo", AuthorizedOperation.IMPLEMENT),
            task_id="task-1", repository="org/repo",
            operation=AuthorizedOperation.IMPLEMENT, isolated=True,
        )


def test_timeout_policy_cannot_be_bypassed() -> None:
    with pytest.raises(PermissionError, match="timeout"):
        authorize_operation(
            grant(), task_id="task-1", repository="org/repo",
            operation=AuthorizedOperation.IMPLEMENT, isolated=True,
            timeout_seconds=9999,
        )


def test_draft_pr_approval_does_not_grant_merge() -> None:
    authorize_operation(
        grant(AuthorizedOperation.CREATE_DRAFT_PR),
        task_id="task-1", repository="org/repo",
        operation=AuthorizedOperation.CREATE_DRAFT_PR,
    )
    with pytest.raises(PermissionError, match="operation"):
        authorize_operation(
            grant(AuthorizedOperation.CREATE_DRAFT_PR),
            task_id="task-1", repository="org/repo",
            operation=AuthorizedOperation.MERGE,
        )
