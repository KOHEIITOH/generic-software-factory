import sys

from sf_factory.cli import build_parser, main


def test_doctor_command_parses() -> None:
    args = build_parser().parse_args(["doctor"])
    assert args.command == "doctor"


def test_codex_smoke_command_parses() -> None:
    args = build_parser().parse_args(["codex-smoke"])
    assert args.command == "codex-smoke"


def test_copilot_smoke_command_parses() -> None:
    args = build_parser().parse_args(["copilot-smoke"])
    assert args.command == "copilot-smoke"


def test_grok_smoke_command_parses() -> None:
    args = build_parser().parse_args(["grok-smoke"])
    assert args.command == "grok-smoke"


def test_task_run_accepts_copilot_runtime() -> None:
    args = build_parser().parse_args(["task", "run", "task-id", "--runtime", "copilot"])
    assert args.runtime == "copilot"


def test_task_run_dispatches_to_copilot_runtime(tmp_path, monkeypatch, capsys) -> None:
    calls: list[tuple[str, str, int]] = []

    def fake_run_task(self, task_id: str, runtime_name: str, timeout_seconds: int) -> dict:
        calls.append((task_id, runtime_name, timeout_seconds))
        return {"id": "run-id", "status": "succeeded"}

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sf_factory.factory.Factory.run_task", fake_run_task)
    monkeypatch.setattr(
        sys,
        "argv",
        ["sf", "task", "run", "task-id", "--runtime", "copilot", "--timeout", "45"],
    )

    assert main() == 0
    assert calls == [("task-id", "copilot", 45)]
    assert '"status": "succeeded"' in capsys.readouterr().out
