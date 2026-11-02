from pathlib import Path

import pytest

from sf_factory.agent_registry import AgentRuntimeRegistry, default_runtime_registry
from sf_factory.factory import Factory
from sf_factory.runtime import RuntimeResult


class FakeRuntime:
    def execute(self, *, prompt: str, workspace: Path, timeout_seconds: int = 600) -> RuntimeResult:
        assert workspace.is_dir()
        assert prompt == "hello"
        return RuntimeResult(runtime="custom", status="succeeded", output="OK", exit_code=0)


def test_default_registry_contains_existing_adapters() -> None:
    registry = default_runtime_registry()
    assert registry.names() == ("codex", "copilot", "grok")


def test_custom_runtime_uses_same_factory_path(tmp_path: Path) -> None:
    registry = AgentRuntimeRegistry()
    registry.register("custom", FakeRuntime)
    factory = Factory(tmp_path, runtime_registry=registry)
    task_id = factory.create_task("hello")
    run = factory.run_task(task_id, "custom")
    assert run["status"] == "succeeded"
    assert run["runtime"] == "custom"
    assert run["output"] == "OK"
    assert factory.show_run(run["id"])["output"] == "OK"


def test_duplicate_or_blank_names_rejected() -> None:
    registry = AgentRuntimeRegistry()
    with pytest.raises(ValueError):
        registry.register(" ", FakeRuntime)
    registry.register("custom", FakeRuntime)
    with pytest.raises(ValueError):
        registry.register("custom", FakeRuntime)


def test_unknown_runtime_rejected_before_workspace_creation(tmp_path: Path) -> None:
    registry = AgentRuntimeRegistry()
    factory = Factory(tmp_path, runtime_registry=registry)
    task_id = factory.create_task("hello")
    with pytest.raises(ValueError, match="unsupported runtime"):
        factory.run_task(task_id, "unknown")
    assert not list(factory.workspaces.iterdir())
