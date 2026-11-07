"""Custom agent tests with a fake model; never call real providers."""

from pathlib import Path

import pytest

from sf_factory.custom_agent import analyze_issue
from sf_factory.model_provider import ModelResponse
from sf_factory.usage_tracker import UsageTracker


class FakeProvider:
    def __init__(self):
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> ModelResponse:
        self.prompts.append(prompt)
        return ModelResponse("fake", "test", "analysis", 20, 3)


def test_readonly_analysis_tracks_usage(tmp_path: Path):
    (tmp_path / "main.py").write_text("print('hello')", encoding="utf-8")
    provider = FakeProvider()
    tracker = UsageTracker()
    result = analyze_issue(
        "issue-1", "Review code", tmp_path, ["main.py"], provider, tracker=tracker
    )
    assert result.response.text == "analysis"
    assert result.context.characters == len("print('hello')")
    assert "main.py" in provider.prompts[0]
    assert tracker.totals("issue-1").input_tokens == 20


def test_empty_context_does_not_invoke_model(tmp_path: Path):
    provider = FakeProvider()
    with pytest.raises(ValueError):
        analyze_issue("issue", "Review", tmp_path, ["missing.py"], provider)
    assert provider.prompts == []


def test_rejects_actual_nul_byte(tmp_path: Path):
    (tmp_path / "binary.txt").write_bytes(b"a" + bytes([0]) + b"b")
    provider = FakeProvider()
    with pytest.raises(ValueError):
        analyze_issue("issue", "Review", tmp_path, ["binary.txt"], provider)
    assert provider.prompts == []
