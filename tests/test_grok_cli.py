import json
import subprocess
from pathlib import Path

import pytest

from sf_factory.grok_cli import GrokBuildCliRuntime


def test_grok_build_builds_restricted_headless_command(tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        stdout = json.dumps(
            {
                "text": "hello from grok",
                "stopReason": "end_turn",
                "sessionId": "grok-session-123",
            }
        )
        return subprocess.CompletedProcess(command, 0, stdout, "")

    monkeypatch.setattr("sf_factory.grok_cli.subprocess.run", fake_run)
    result = GrokBuildCliRuntime(model="grok-4.6").execute(
        prompt="Say hello",
        workspace=tmp_path,
        timeout_seconds=30,
    )

    command = captured["command"]
    assert isinstance(command, list)
    assert command[:3] == ["grok", "-p", "Say hello"]
    assert "--output-format" in command
    assert command[command.index("--output-format") + 1] == "json"
    assert command[command.index("--tools") + 1] == "read_file,grep,list_dir"
    assert command[command.index("--disallowed-tools") + 1] == "Agent"
    assert command[command.index("--deny") + 1] == "MCPTool(*)"
    assert "--no-auto-update" in command
    assert command[command.index("--model") + 1] == "grok-4.6"
    assert result.status == "succeeded"
    assert result.output == "hello from grok"
    assert result.session_id == "grok-session-123"
    assert captured["cwd"] == tmp_path.resolve()
    assert captured["capture_output"] is True
    assert captured["timeout"] == 30


def test_grok_build_rejects_empty_prompt(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="prompt"):
        GrokBuildCliRuntime().execute(prompt="  ", workspace=tmp_path)


def test_grok_build_rejects_empty_tool_allowlist(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="tools"):
        GrokBuildCliRuntime(tools=()).execute(prompt="hello", workspace=tmp_path)


def test_grok_build_reports_timeout(tmp_path: Path, monkeypatch) -> None:
    def fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, timeout=1, stderr="timed out")

    monkeypatch.setattr("sf_factory.grok_cli.subprocess.run", fake_run)
    result = GrokBuildCliRuntime().execute(
        prompt="Say hello",
        workspace=tmp_path,
        timeout_seconds=1,
    )
    assert result.status == "timed_out"
    assert result.error_kind == "timeout"
    assert result.stderr == "timed out"


def test_grok_build_rejects_invalid_json(tmp_path: Path, monkeypatch) -> None:
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, "not-json", "")

    monkeypatch.setattr("sf_factory.grok_cli.subprocess.run", fake_run)
    result = GrokBuildCliRuntime().execute(prompt="Say hello", workspace=tmp_path)
    assert result.status == "failed"
    assert "invalid JSON" in result.stderr


@pytest.mark.parametrize(
    ("message", "expected_kind"),
    [
        ("Usage limit reached", "usage_limit"),
        ("Rate limit exceeded (429)", "rate_limit"),
        ("Authentication required", "authentication"),
        ("Model not found", "model_not_found"),
    ],
)
def test_grok_build_normalizes_errors(
    tmp_path: Path,
    monkeypatch,
    message: str,
    expected_kind: str,
) -> None:
    def fake_run(command, **kwargs):
        stdout = json.dumps({"text": "", "error": {"message": message}})
        return subprocess.CompletedProcess(command, 1, stdout, "")

    monkeypatch.setattr("sf_factory.grok_cli.subprocess.run", fake_run)
    result = GrokBuildCliRuntime().execute(prompt="Say hello", workspace=tmp_path)

    assert result.status == "failed"
    assert result.error_kind == expected_kind
    assert result.error_message == message
