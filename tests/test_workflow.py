import pytest

from sf_factory.policy import Capability, ExecutionPolicy
from sf_factory.workflow import (
    StepState,
    WorkflowDefinition,
    WorkflowStep,
    evaluate_workflow,
)


def test_can_start_from_implementation_without_planning_stage() -> None:
    workflow = WorkflowDefinition((
        WorkflowStep("implement"),
        WorkflowStep("test", depends_on=("implement",)),
    ))
    assert [item.state for item in evaluate_workflow(workflow)] == [
        StepState.READY, StepState.WAITING
    ]
    next_steps = evaluate_workflow(workflow, completed=frozenset({"implement"}))
    assert next_steps[1].state is StepState.READY


def test_can_start_from_discovery_and_parallel_steps() -> None:
    workflow = WorkflowDefinition((
        WorkflowStep("research"),
        WorkflowStep("interview"),
        WorkflowStep("requirements", depends_on=("research", "interview")),
    ))
    assert [item.state for item in evaluate_workflow(workflow)] == [
        StepState.READY, StepState.READY, StepState.WAITING
    ]


def test_policy_blocks_write_without_opt_in() -> None:
    workflow = WorkflowDefinition((WorkflowStep("code", Capability.WORKSPACE_WRITE),))
    assert evaluate_workflow(workflow)[0].state is StepState.BLOCKED
    opted_in = ExecutionPolicy(allow_workspace_write=True)
    assert evaluate_workflow(workflow, policy=opted_in)[0].state is StepState.WAITING
    approved = evaluate_workflow(workflow, policy=opted_in, approvals=frozenset({"code"}))
    assert approved[0].state is StepState.READY


@pytest.mark.parametrize("steps", [
    (WorkflowStep("a"), WorkflowStep("a")),
    (WorkflowStep("a", depends_on=("missing",)),),
    (WorkflowStep("a", depends_on=("a",)),),
    (WorkflowStep("a", depends_on=("b",)), WorkflowStep("b", depends_on=("a",))),
    (WorkflowStep("a", depends_on=("b", "b")), WorkflowStep("b")),
])
def test_invalid_workflows_are_rejected(steps: tuple[WorkflowStep, ...]) -> None:
    with pytest.raises(ValueError):
        WorkflowDefinition(steps).validate()


def test_unknown_completed_or_approval_rejected() -> None:
    workflow = WorkflowDefinition((WorkflowStep("a"),))
    with pytest.raises(ValueError):
        evaluate_workflow(workflow, completed=frozenset({"other"}))
    with pytest.raises(ValueError):
        evaluate_workflow(workflow, approvals=frozenset({"other"}))
