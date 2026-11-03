import sys
from pathlib import Path

from sf_factory.acp import AcpCommand, AcpRuntime

FAKE_AGENT = """
import json, sys
for line in sys.stdin:
    req = json.loads(line)
    method = req.get("method")
    if method == "initialize":
        result = {"protocolVersion": 1}
    elif method == "session/new":
        result = {"sessionId": "test-session"}
    elif method == "session/prompt":
        print(json.dumps({"jsonrpc": "2.0", "method": "session/update",
          "params": {"update": {"sessionUpdate": "agent_message_chunk",
          "content": {"type": "text", "text": "Hello"}}}}), flush=True)
        result = {"stopReason": "end_turn"}
    else:
        result = {}
    print(json.dumps({"jsonrpc": "2.0", "id": req["id"], "result": result}), flush=True)
"""


def test_acp_happy_path(tmp_path: Path) -> None:
    runtime = AcpRuntime(AcpCommand((sys.executable, "-u", "-c", FAKE_AGENT)))
    result = runtime.execute(prompt="hello", workspace=tmp_path, timeout_seconds=5)
    assert result.status == "succeeded"
    assert result.output == "Hello"
    assert result.session_id == "test-session"


def test_acp_unknown_command_fails(tmp_path: Path) -> None:
    runtime = AcpRuntime(AcpCommand(("nonexistent-factory-acp-command",)))
    result = runtime.execute(prompt="hello", workspace=tmp_path, timeout_seconds=5)
    assert result.status == "failed"


def test_acp_invalid_workspace(tmp_path: Path) -> None:
    runtime = AcpRuntime(AcpCommand((sys.executable,)))
    try:
        runtime.execute(prompt="hello", workspace=tmp_path / "missing")
        assert False
    except ValueError:
        pass


def test_acp_reports_redacted_failure_stage(tmp_path: Path) -> None:
    agent = """
import json, sys
for line in sys.stdin:
    req = json.loads(line)
    print(json.dumps({"jsonrpc": "2.0", "id": req["id"],
      "error": {"code": -32600, "message": "secret token 123"}}), flush=True)
"""
    runtime = AcpRuntime(AcpCommand((sys.executable, "-u", "-c", agent)))
    result = runtime.execute(prompt="hello", workspace=tmp_path, timeout_seconds=5)
    assert result.status == "failed"
    assert result.error_message == "ACP initialize failed (RuntimeError)"
    assert "secret" not in result.error_message
