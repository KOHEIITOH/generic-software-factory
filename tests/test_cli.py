import sys
from pathlib import Path

import pytest

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


def test_analyze_command_requires_explicit_send_confirmation() -> None:
    args = build_parser().parse_args(["analyze", "/tmp/repo"])
    assert args.command == "analyze"
    assert args.repository == Path("/tmp/repo")
    assert args.confirm_send is False


def test_analyze_command_reports_scope_and_analysis(tmp_path: Path, monkeypatch, capsys) -> None:
    from sf_factory.repo_analysis import RepositoryAnalysis
    from sf_factory.runtime import RuntimeResult

    analysis = RepositoryAnalysis(
        runtime_result=RuntimeResult(
            runtime="copilot",
            status="succeeded",
            output="Repository overview",
            exit_code=0,
        ),
        files_included=("README.md",),
        exclusions={"symlinks": 1},
        limits_reached=("file_count",),
        bytes_included=10,
    )
    calls: list[tuple[Path, bool, int]] = []

    def fake_analyze(
        repository: Path, *, timeout_seconds: int, confirm_send: bool
    ) -> RepositoryAnalysis:
        calls.append((repository, confirm_send, timeout_seconds))
        return analysis

    monkeypatch.setattr("sf_factory.repo_analysis.analyze_repository", fake_analyze)
    monkeypatch.setattr(
        sys,
        "argv",
        ["sf", "analyze", str(tmp_path), "--confirm-send", "--timeout", "45"],
    )
    monkeypatch.chdir(tmp_path)

    assert main() == 0
    output = capsys.readouterr().out
    assert '"files_included": [' in output
    assert '"limits_reached": [' in output
    assert "Repository overview" in output
    assert calls == [(tmp_path, True, 45)]
    assert not (tmp_path / ".sf-factory").exists()


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


def test_task_run_requires_explicit_runtime() -> None:
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["task", "run", "task-id"])
    assert exc.value.code == 2
