from pathlib import Path

from sf_factory.policy import Capability
from sf_factory.runtime import RuntimeResult
from sf_factory.workflow import WorkflowDefinition, WorkflowStep
from sf_factory.workflow_runner import run_workflow


class FakeRuntime:
    def __init__(self, status: str = "succeeded"):
        self.status = status
        self.calls: list[str] = []

    def execute(self, *, prompt: str, workspace: Path, timeout_seconds: int = 600):
        self.calls.append(prompt)
        return RuntimeResult("fake", self.status, "result", 0)


def test_runner_executes_dependencies_in_order(tmp_path: Path) -> None:
    runtime = FakeRuntime()
    workflow = WorkflowDefinition((
        WorkflowStep("research"),
        WorkflowStep("report", depends_on=("research",)),
    ))
    result = run_workflow(
        workflow, runtime_for=lambda step: runtime,
        prompt_for=lambda step: f"do {step}", workspace=tmp_path,
    )
    assert result.completed
    assert runtime.calls == ["do research", "do report"]


def test_runner_stops_on_runtime_failure(tmp_path: Path) -> None:
    runtime = FakeRuntime("failed")
    result = run_workflow(
        WorkflowDefinition((WorkflowStep("research"), WorkflowStep("report"))),
        runtime_for=lambda step: runtime,
        prompt_for=lambda step: step, workspace=tmp_path,
    )
    assert not result.completed
    assert runtime.calls == ["research"]


def test_runner_does_not_execute_writes(tmp_path: Path) -> None:
    runtime = FakeRuntime()
    result = run_workflow(
        WorkflowDefinition((WorkflowStep("write", Capability.WORKSPACE_WRITE),)),
        runtime_for=lambda step: runtime,
        prompt_for=lambda step: step, workspace=tmp_path,
    )
    assert not result.completed
    assert runtime.calls == []


def test_runner_rejects_invalid_workflow_before_execution(tmp_path: Path) -> None:
    runtime = FakeRuntime()
    try:
        run_workflow(
            WorkflowDefinition((WorkflowStep("a", depends_on=("missing",)),)),
            runtime_for=lambda step: runtime,
            prompt_for=lambda step: step, workspace=tmp_path,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("expected invalid workflow")
    assert runtime.calls == []
