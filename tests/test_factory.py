from pathlib import Path

from issue_fixtures import seed_issue

from sf_factory.factory import Factory
from sf_factory.runtime import RuntimeResult


def test_task_persists_across_instances(tmp_path: Path) -> None:
    issue_key = seed_issue(Factory(tmp_path), "Explain this project")
    assert Factory(tmp_path).show_issue(issue_key)["issue"]["prompt"] == "Explain this project"

def test_run_isolated_and_persisted(tmp_path: Path, monkeypatch) -> None:
    def fake_execute(self, *, prompt, workspace, timeout_seconds=120):
        assert workspace.is_dir()
        assert workspace.parent == tmp_path / "workspaces"
        assert prompt == "hello"
        return RuntimeResult(runtime="codex", status="succeeded", output="OK", exit_code=0)
    monkeypatch.setattr("sf_factory.codex_cli.CodexCliRuntime.execute", fake_execute)
    factory = Factory(tmp_path)
    issue_key = seed_issue(factory, "hello")
    run = factory.run_issue(issue_key, "codex")
    assert run["status"] == "succeeded"
    assert Factory(tmp_path).show_run(run["id"])["output"] == "OK"
    assert len(factory.show_issue(issue_key)["runs"]) == 1

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
    issue_key = seed_issue(factory, "hello")

    run = factory.run_issue(issue_key, "copilot")

    assert run["runtime"] == "copilot"
    assert run["status"] == "succeeded"
    assert run["output"] == "Copilot response"
    assert Factory(tmp_path).show_run(run["id"])["output"] == "Copilot response"

def test_unknown_task_does_not_create_workspace(tmp_path: Path) -> None:
    factory = Factory(tmp_path)
    try:
        factory.run_issue("missing", "codex")
        assert False
    except ValueError:
        pass
    assert list(factory.workspaces.iterdir()) == []


def test_external_issue_import_is_idempotent(tmp_path: Path) -> None:
    factory = Factory(tmp_path)
    first = factory.import_issue(
        provider="jira", instance="https://acme.atlassian.net",
        external_id="PAY-123", prompt="Implement feature",
        external_url="https://acme.atlassian.net/browse/PAY-123",
    )
    again = Factory(tmp_path).import_issue(
        provider="jira", instance="https://acme.atlassian.net",
        external_id="PAY-123", prompt="Changed title",
    )
    assert first == again
    assert factory.show_issue(first)["issue"]["prompt"] == "Changed title"
    assert len(factory.list_issues()) == 1
    assert factory.list_issues()[0]["external_id"] == "PAY-123"


def test_external_issue_identity_is_namespaced(tmp_path: Path) -> None:
    factory = Factory(tmp_path)
    one = factory.import_issue(
        provider="jira", instance="tenant-a", external_id="ABC-1", prompt="A",
    )
    two = factory.import_issue(
        provider="jira", instance="tenant-b", external_id="ABC-1", prompt="B",
    )
    three = factory.import_issue(
        provider="github", instance="tenant-a", external_id="ABC-1", prompt="C",
    )
    assert len({one, two, three}) == 3


def test_existing_database_remains_usable_with_source_mapping(tmp_path: Path) -> None:
    factory = Factory(tmp_path)
    local = seed_issue(factory, "Local")
    imported = Factory(tmp_path).import_issue(
        provider="jira", instance="tenant", external_id="X-1", prompt="External",
    )
    rows = {row["key"]: row for row in Factory(tmp_path).list_issues()}
    assert rows[local]["provider"] == "fixture"
    assert rows[imported]["provider"] == "jira"
