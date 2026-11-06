"""Implementation planning must not accidentally execute agent code."""

from sf_factory.agent_registry import AgentRuntimeRegistry
from sf_factory.execution_authorization import AuthorizedOperation, ExecutionGrant
from sf_factory.implementation_plan import plan_implementation


def registry():
    result = AgentRuntimeRegistry()
    result.register("test", lambda: (_ for _ in ()).throw(
        AssertionError("Runtime must not be constructed during planning")
    ))
    return result


def test_default_plan_denies_execution():
    plan = plan_implementation(
        task_id="task1", repository="owner/repo", runtime="test", registry=registry()
    )
    assert not plan.ready
    assert len(plan.blockers) == 2


def test_worktree_without_os_isolation_stays_denied():
    grant = ExecutionGrant(
        task_id="task1", repository="owner/repo",
        operation=AuthorizedOperation.IMPLEMENT, approved=True,
    )
    plan = plan_implementation(
        task_id="task1", repository="owner/repo", runtime="test",
        registry=registry(), grant=grant,
    )
    assert not plan.ready
    assert any("OS process isolation" in reason for reason in plan.blockers)


def test_wrong_scope_and_unknown_runtime_are_denied():
    grant = ExecutionGrant(
        task_id="other", repository="owner/repo",
        operation=AuthorizedOperation.IMPLEMENT, approved=True,
    )
    plan = plan_implementation(
        task_id="task1", repository="owner/repo", runtime="unknown",
        registry=registry(), grant=grant, process_isolated=True,
    )
    assert not plan.ready
    assert any("not registered" in reason for reason in plan.blockers)
    assert any("scope" in reason for reason in plan.blockers)


def test_valid_plan_does_not_execute():
    grant = ExecutionGrant(
        task_id="task1", repository="owner/repo",
        operation=AuthorizedOperation.IMPLEMENT, approved=True,
    )
    plan = plan_implementation(
        task_id="task1", repository="owner/repo", runtime="test",
        registry=registry(), grant=grant, process_isolated=True,
    )
    assert plan.ready
    assert not plan.blockers
