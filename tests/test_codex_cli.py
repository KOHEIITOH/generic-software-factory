import json
import subprocess
from pathlib import Path

import pytest

from sf_factory.codex_cli import CodexCliRuntime


def test_codex_cli_builds_safe_non_interactive_command(tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        stdout = "\n".join(
            [
                json.dumps({"type": "thread.started", "thread_id": "thread-123"}),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {"type": "agent_message", "text": "hello from codex"},
                    }
                ),
                json.dumps({"type": "turn.completed"}),
            ]
        )
        return subprocess.CompletedProcess(command, 0, stdout, "")

    monkeypatch.setattr("sf_factory.codex_cli.subprocess.run", fake_run)
    result = CodexCliRuntime().execute(
        prompt="Say hello",
        workspace=tmp_path,
        timeout_seconds=30,
    )

    command = captured["command"]
    assert isinstance(command, list)
    assert command[:2] == ["codex", "exec"]
    assert "--json" in command
    assert "--ephemeral" in command
    assert "--skip-git-repo-check" in command
    assert "--sandbox" in command
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert result.status == "succeeded"
    assert result.output == "hello from codex"
    assert result.session_id == "thread-123"
    assert captured["cwd"] == tmp_path.resolve()
    assert captured["capture_output"] is True
    assert captured["timeout"] == 30


def test_codex_cli_rejects_empty_prompt(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="prompt"):
        CodexCliRuntime().execute(prompt="  ", workspace=tmp_path)


def test_codex_cli_reports_timeout(tmp_path: Path, monkeypatch) -> None:
    def fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, timeout=1, stderr="timed out")

    monkeypatch.setattr("sf_factory.codex_cli.subprocess.run", fake_run)
    result = CodexCliRuntime().execute(
        prompt="Say hello",
        workspace=tmp_path,
        timeout_seconds=1,
    )
    assert result.status == "timed_out"
    assert result.error_kind == "timeout"
    assert result.stderr == "timed out"


def test_codex_cli_rejects_invalid_jsonl(tmp_path: Path, monkeypatch) -> None:
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, "not-json\n", "")

    monkeypatch.setattr("sf_factory.codex_cli.subprocess.run", fake_run)
    result = CodexCliRuntime().execute(prompt="Say hello", workspace=tmp_path)
    assert result.status == "failed"
    assert "Invalid JSONL" in result.stderr


@pytest.mark.parametrize(
    ("api_message", "expected_kind"),
    [
        ("You've hit your usage limit. Try again later.", "usage_limit"),
        ("Rate limit exceeded.", "rate_limit"),
        ("The selected model is not supported.", "model_not_found"),
        ("Authentication required.", "authentication"),
    ],
)
def test_codex_cli_normalizes_error_events(
    tmp_path: Path,
    monkeypatch,
    api_message: str,
    expected_kind: str,
) -> None:
    def fake_run(command, **kwargs):
        stdout = "\n".join(
            [
                json.dumps({"type": "thread.started", "thread_id": "thread-error"}),
                json.dumps({"type": "error", "message": api_message}),
                json.dumps({"type": "turn.failed", "error": {"message": api_message}}),
            ]
        )
        return subprocess.CompletedProcess(command, 1, stdout, "")

    monkeypatch.setattr("sf_factory.codex_cli.subprocess.run", fake_run)
    result = CodexCliRuntime().execute(prompt="Say hello", workspace=tmp_path)

    assert result.status == "failed"
    assert result.error_kind == expected_kind
    assert result.error_message == api_message
    assert result.session_id == "thread-error"
