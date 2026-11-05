"""Bedrock provider tests do not require AWS credentials."""

import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from sf_factory.bedrock_provider import BedrockModelProvider


def test_bedrock_converse(monkeypatch):
    client = Mock()
    client.converse.return_value = {
        "output": {"message": {"content": [{"text": "Hello"}, {"text": " world"}]}},
        "usage": {"inputTokens": 4, "outputTokens": 2},
    }
    boto3 = SimpleNamespace(client=Mock(return_value=client))
    monkeypatch.setitem(sys.modules, "boto3", boto3)
    result = BedrockModelProvider("test-model", "ap-northeast-1").generate("Hi")
    assert result.text == "Hello world"
    assert result.input_tokens == 4
    boto3.client.assert_called_once_with("bedrock-runtime", region_name="ap-northeast-1")
    assert client.converse.call_args.kwargs["modelId"] == "test-model"


@pytest.mark.parametrize("kwargs", [
    {"model_id": ""}, {"region_name": ""}, {"max_tokens": 0}, {"temperature": -1.0},
])
def test_invalid_configuration(kwargs):
    options = {"model_id": "test-model", "region_name": "ap-northeast-1"}
    options.update(kwargs)
    with pytest.raises(ValueError):
        BedrockModelProvider(**options)


def test_empty_prompt_rejected():
    with pytest.raises(ValueError):
        BedrockModelProvider("test-model", "ap-northeast-1").generate("  ")


def test_bedrock_error_redacted(monkeypatch):
    client = Mock()
    client.converse.side_effect = RuntimeError("sensitive AWS error")
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=lambda *a, **kw: client))
    with pytest.raises(RuntimeError, match="AWS Bedrock inference failed") as exc:
        BedrockModelProvider("test-model", "ap-northeast-1").generate("Hi")
    assert "sensitive" not in str(exc.value)


def test_bedrock_client_creation_error_redacted(monkeypatch):
    def fail_client(*args, **kwargs):
        raise RuntimeError("sensitive AWS credentials")

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=fail_client))
    with pytest.raises(RuntimeError, match="AWS Bedrock inference failed") as exc:
        BedrockModelProvider("test-model", "ap-northeast-1").generate("Hi")
    assert "sensitive" not in str(exc.value)
