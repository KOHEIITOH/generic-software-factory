from __future__ import annotations

import sys
import types
from pathlib import Path

from sf_factory.copilot_sdk import CopilotSdkRuntime


class AssistantMessageData:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeSession:
    session_id = "copilot-session"

    def __init__(self, response: object = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.session_options: dict[str, object] | None = None
        self.sent_prompt: str | None = None
        self.sent_timeout: int | None = None

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def send_and_wait(self, prompt: str, *, timeout: int) -> object:
        self.sent_prompt = prompt
        self.sent_timeout = timeout
        if self.error is not None:
            raise self.error
        return self.response


class FakeClient:
    def __init__(self, session: FakeSession) -> None:
        self.session = session
        self.session_options: dict[str, object] | None = None

    async def __aenter__(self) -> FakeClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def create_session(self, **kwargs: object) -> FakeSession:
        self.session_options = kwargs
        self.session.session_options = kwargs
        return self.session


def _install_fake_sdk(monkeypatch, session: FakeSession) -> FakeClient:
    client = FakeClient(session)
    copilot_module = types.ModuleType("copilot")
    copilot_module.CopilotClient = lambda: client
    events_module = types.ModuleType("copilot.session_events")
    events_module.AssistantMessageData = AssistantMessageData
    monkeypatch.setitem(sys.modules, "copilot", copilot_module)
    monkeypatch.setitem(sys.modules, "copilot.session_events", events_module)
    return client


def test_execute_normalizes_response_and_disables_tools(
    tmp_path: Path, monkeypatch
) -> None:
    session = FakeSession(types.SimpleNamespace(data=AssistantMessageData("  Hello  ")))
    client = _install_fake_sdk(monkeypatch, session)

    result = CopilotSdkRuntime().execute(
        prompt="Say hello",
        workspace=tmp_path,
        timeout_seconds=17,
    )

    assert result.runtime == "copilot"
    assert result.status == "succeeded"
    assert result.output == "Hello"
    assert result.exit_code == 0
    assert result.session_id == "copilot-session"
    assert client.session_options == {
        "available_tools": [],
        "working_directory": str(tmp_path.resolve()),
        "enable_file_change_tracking": False,
    }
    assert session.sent_prompt == "Say hello"
    assert session.sent_timeout == 17


def test_execute_normalizes_timeout(tmp_path: Path, monkeypatch) -> None:
    _install_fake_sdk(monkeypatch, FakeSession(error=TimeoutError()))

    result = CopilotSdkRuntime().execute(prompt="Wait", workspace=tmp_path, timeout_seconds=1)

    assert result.status == "timed_out"
    assert result.error_kind == "timeout"
    assert result.exit_code is None


def test_execute_normalizes_authentication_failure_without_persisting_error_text(
    tmp_path: Path, monkeypatch
) -> None:
    _install_fake_sdk(
        monkeypatch,
        FakeSession(error=RuntimeError("authentication failed: secret-token-value")),
    )

    result = CopilotSdkRuntime().execute(prompt="Check auth", workspace=tmp_path)

    assert result.status == "failed"
    assert result.error_kind == "authentication"
    assert "secret-token-value" not in (result.error_message or "")
    assert "copilot login" in (result.error_message or "")


def test_execute_fails_when_response_is_not_an_assistant_message(
    tmp_path: Path, monkeypatch
) -> None:
    _install_fake_sdk(monkeypatch, FakeSession(types.SimpleNamespace(data=object())))

    result = CopilotSdkRuntime().execute(prompt="Try", workspace=tmp_path)

    assert result.status == "failed"
    assert result.error_kind == "runtime_error"
    assert result.output == ""
