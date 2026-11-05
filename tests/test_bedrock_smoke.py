"""Smoke tests never contact AWS."""

from sf_factory.bedrock_smoke import run_bedrock_smoke
from sf_factory.model_provider_status import BedrockConfiguration
from sf_factory.model_provider import ModelResponse


def test_smoke_requires_confirmation(capsys):
    assert run_bedrock_smoke(confirm_invoke=False) == 2
    assert "confirm-invoke" in capsys.readouterr().err


def test_smoke_requires_configuration(monkeypatch):
    monkeypatch.setattr(
        "sf_factory.bedrock_smoke.bedrock_configuration",
        lambda: BedrockConfiguration(None, None, False),
    )
    assert run_bedrock_smoke(confirm_invoke=True) == 2


def test_smoke_invokes_once_without_printing_prompt(monkeypatch, capsys):
    calls = []

    class FakeProvider:
        def __init__(self, **kwargs):
            calls.append(kwargs)

        def generate(self, prompt):
            calls.append(prompt)
            return ModelResponse("bedrock", "example", "OK", 8, 1)

    monkeypatch.setattr(
        "sf_factory.bedrock_smoke.bedrock_configuration",
        lambda: BedrockConfiguration("example", "ap-northeast-1", True),
    )
    monkeypatch.setattr("sf_factory.bedrock_smoke.BedrockModelProvider", FakeProvider)
    assert run_bedrock_smoke(confirm_invoke=True) == 0
    assert len(calls) == 2
    assert calls[0]["max_tokens"] == 32
    assert "succeeded" in capsys.readouterr().out
