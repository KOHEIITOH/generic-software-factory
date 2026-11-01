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

def test_unknown_task_does_not_create_workspace(tmp_path: Path) -> None:
    factory = Factory(tmp_path)
    try:
        factory.run_task("missing", "codex")
        assert False
    except ValueError:
        pass
    assert list(factory.workspaces.iterdir()) == []
