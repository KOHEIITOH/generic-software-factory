"""Declarative, policy-aware workflow planning without fixed development stages."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from sf_factory.policy import (
    Capability,
    ExecutionPolicy,
    ExecutionRequest,
    PolicyDecision,
)


class StepState(StrEnum):
    READY = "ready"
    WAITING = "waiting"
    BLOCKED = "blocked"
    COMPLETED = "completed"


@dataclass(frozen=True)
class WorkflowStep:
    id: str
    capability: Capability = Capability.READ_ONLY
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkflowDefinition:
    steps: tuple[WorkflowStep, ...]

    def validate(self) -> None:
        steps = {step.id: step for step in self.steps}
        if len(steps) != len(self.steps) or any(not step.id.strip() for step in self.steps):
            raise ValueError("workflow step ids must be unique and non-empty")
        for step in self.steps:
            if step.id in step.depends_on:
                raise ValueError("workflow step cannot depend on itself")
            if len(step.depends_on) != len(set(step.depends_on)):
                raise ValueError("duplicate step dependency")
            if any(dep not in steps for dep in step.depends_on):
                raise ValueError("workflow references an unknown dependency")
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(step_id: str) -> None:
            if step_id in visiting:
                raise ValueError("workflow contains a dependency cycle")
            if step_id in visited:
                return
            visiting.add(step_id)
            for dependency in steps[step_id].depends_on:
                visit(dependency)
            visiting.remove(step_id)
            visited.add(step_id)

        for step in self.steps:
            visit(step.id)


@dataclass(frozen=True)
class StepEvaluation:
    id: str
    state: StepState
    reason: str


def evaluate_workflow(
    workflow: WorkflowDefinition,
    *,
    completed: frozenset[str] = frozenset(),
    approvals: frozenset[str] = frozenset(),
    policy: ExecutionPolicy | None = None,
) -> tuple[StepEvaluation, ...]:
    """Evaluate ready steps; never executes tools or mutates a repository."""
    workflow.validate()
    known = {step.id for step in workflow.steps}
    if not completed <= known or not approvals <= known:
        raise ValueError("unknown step in completed or approvals")
    policy = policy if policy is not None else ExecutionPolicy()
    result: list[StepEvaluation] = []
    for step in workflow.steps:
        if step.id in completed:
            result.append(StepEvaluation(step.id, StepState.COMPLETED, "already completed"))
            continue
        if not set(step.depends_on) <= completed:
            result.append(StepEvaluation(step.id, StepState.WAITING, "dependencies incomplete"))
            continue
        decision = policy.evaluate(
            ExecutionRequest(capability=step.capability, approved=step.id in approvals)
        )
        if decision.decision is PolicyDecision.DENY:
            result.append(StepEvaluation(step.id, StepState.BLOCKED, decision.reason))
        elif decision.decision is PolicyDecision.REQUIRE_APPROVAL:
            result.append(StepEvaluation(step.id, StepState.WAITING, decision.reason))
        else:
            result.append(StepEvaluation(step.id, StepState.READY, decision.reason))
    return tuple(result)
