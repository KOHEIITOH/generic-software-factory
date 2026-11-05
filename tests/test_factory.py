from pathlib import Path

from sf_factory.factory import Factory
from sf_factory.runtime import RuntimeResult


def test_task_persists_across_instances(tmp_path: Path) -> None:
    task_id = Factory(tmp_path).create_task("Explain this project")
    assert Factory(tmp_path).show_task(task_id)["task"]["prompt"] == "Explain this project"

def test_run_isolated_and_persisted(tmp_path: Path, monkeypatch) -> None:
    def fake_execute(self, *, prompt, workspace, timeout_seconds=120):
        assert workspace.is_dir()
        assert workspace.parent == tmp_path / "workspaces"
        assert prompt == "hello"
        return RuntimeResult(runtime="codex", status="succeeded", output="OK", exit_code=0)
    monkeypatch.setattr("sf_factory.codex_cli.CodexCliRuntime.execute", fake_execute)
    factory = Factory(tmp_path)
    task_id = factory.create_task("hello")
    run = factory.run_task(task_id, "codex")
    assert run["status"] == "succeeded"
    assert Factory(tmp_path).show_run(run["id"])["output"] == "OK"
    assert len(factory.show_task(task_id)["runs"]) == 1

def test_copilot_runtime_can_run_and_persist_result(tmp_path: Path, monkeypatch) -> None:
    def fake_execute(self, *, prompt, workspace, timeout_seconds=120):
        assert workspace.is_dir()
        assert prompt == "hello"
        return RuntimeResult(
            runtime="copilot",
            status="succeeded",
            output="Copilot response",
            exit_code=0,
            session_id="copilot-session",
        )

    monkeypatch.setattr("sf_factory.copilot_sdk.CopilotSdkRuntime.execute", fake_execute)
    factory = Factory(tmp_path)
    task_id = factory.create_task("hello")

    run = factory.run_task(task_id, "copilot")

    assert run["runtime"] == "copilot"
    assert run["status"] == "succeeded"
    assert run["output"] == "Copilot response"
    assert Factory(tmp_path).show_run(run["id"])["output"] == "Copilot response"

def test_unknown_task_does_not_create_workspace(tmp_path: Path) -> None:
    factory = Factory(tmp_path)
    try:
        factory.run_task("missing", "codex")
        assert False
    except ValueError:
        pass
    assert list(factory.workspaces.iterdir()) == []


def test_external_issue_import_is_idempotent(tmp_path: Path) -> None:
    factory = Factory(tmp_path)
    first = factory.import_external_task(
        provider="jira", instance="https://acme.atlassian.net",
        external_id="PAY-123", prompt="Implement feature",
        external_url="https://acme.atlassian.net/browse/PAY-123",
    )
    again = Factory(tmp_path).import_external_task(
        provider="jira", instance="https://acme.atlassian.net",
        external_id="PAY-123", prompt="Changed title",
    )
    assert first == again
    assert factory.show_task(first)["task"]["prompt"] == "Implement feature"
    assert len(factory.list_tasks()) == 1
    assert factory.list_tasks()[0]["external_id"] == "PAY-123"


def test_external_issue_identity_is_namespaced(tmp_path: Path) -> None:
    factory = Factory(tmp_path)
    one = factory.import_external_task(
        provider="jira", instance="tenant-a", external_id="ABC-1", prompt="A",
    )
    two = factory.import_external_task(
        provider="jira", instance="tenant-b", external_id="ABC-1", prompt="B",
    )
    three = factory.import_external_task(
        provider="github", instance="tenant-a", external_id="ABC-1", prompt="C",
    )
    assert len({one, two, three}) == 3


def test_existing_database_remains_usable_with_source_mapping(tmp_path: Path) -> None:
    factory = Factory(tmp_path)
    local = factory.create_task("Local")
    imported = Factory(tmp_path).import_external_task(
        provider="jira", instance="tenant", external_id="X-1", prompt="External",
    )
    rows = {row["id"]: row for row in Factory(tmp_path).list_tasks()}
    assert rows[local]["provider"] is None
    assert rows[imported]["provider"] == "jira"
