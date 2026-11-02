"""Provider-neutral, read-only workflow runner with injected runtime adapters."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sf_factory.policy import Capability, ExecutionPolicy, ExecutionRequest
from sf_factory.runtime import AgentRuntime, RuntimeResult
from sf_factory.workflow import StepState, WorkflowDefinition, evaluate_workflow


@dataclass(frozen=True)
class StepRun:
    step_id: str
    status: str
    result: RuntimeResult | None = None
    reason: str = ""


@dataclass(frozen=True)
class WorkflowRun:
    steps: tuple[StepRun, ...]
    completed: bool


def run_workflow(
    workflow: WorkflowDefinition,
    *,
    runtime_for: Callable[[str], AgentRuntime],
    prompt_for: Callable[[str], str],
    workspace: Path,
    policy: ExecutionPolicy | None = None,
    timeout_seconds: int = 120,
) -> WorkflowRun:
    """Run read-only steps in dependency order; stop on failure or unsafe steps.

    This is an in-process MVP. The caller must provide a sandboxed adapter.
    """
    policy = policy if policy is not None else ExecutionPolicy()
    if not 1 <= timeout_seconds <= policy.max_timeout_seconds:
        raise ValueError("timeout_seconds outside policy limits")
    workflow.validate()
    completed: set[str] = set()
    records: list[StepRun] = []
    while len(completed) < len(workflow.steps):
        evaluations = evaluate_workflow(
            workflow, completed=frozenset(completed), policy=policy
        )
        ready = [item for item in evaluations if item.state is StepState.READY]
        if not ready:
            for item in evaluations:
                if item.id not in completed:
                    records.append(StepRun(item.id, item.state, reason=item.reason))
            return WorkflowRun(tuple(records), False)
        step_id = ready[0].id
        step = next(item for item in workflow.steps if item.id == step_id)
        decision = policy.evaluate(
            ExecutionRequest(capability=step.capability, timeout_seconds=timeout_seconds)
        )
        if not decision.allowed:
            records.append(StepRun(step_id, "blocked", reason=decision.reason))
            return WorkflowRun(tuple(records), False)
        if step.capability is not Capability.READ_ONLY:
            records.append(StepRun(step_id, "blocked", reason="write execution is not supported"))
            return WorkflowRun(tuple(records), False)
        try:
            result = runtime_for(step_id).execute(
                prompt=prompt_for(step_id), workspace=workspace,
                timeout_seconds=timeout_seconds,
            )
        except Exception as exc:
            records.append(StepRun(step_id, "failed", reason=type(exc).__name__))
            return WorkflowRun(tuple(records), False)
        records.append(StepRun(step_id, result.status, result=result))
        if result.status != "succeeded":
            return WorkflowRun(tuple(records), False)
        completed.add(step_id)
    return WorkflowRun(tuple(records), True)
