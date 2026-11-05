"""Provider-neutral token usage tests."""

import pytest

from sf_factory.model_provider import ModelResponse
from sf_factory.usage import TokenUsage


def test_unknown_metrics_remain_unknown():
    usage = TokenUsage(input_tokens=12, output_tokens=3)
    assert usage.reasoning_tokens is None
    assert usage.cache_read_tokens is None


@pytest.mark.parametrize("value", [-1, True, 1.5, "3"])
def test_invalid_token_counts(value):
    with pytest.raises(ValueError):
        TokenUsage(input_tokens=value)


def test_model_response_legacy_fields_remain_supported():
    response = ModelResponse("bedrock", "model", "ok", 5, 2)
    assert response.input_tokens == 5
    assert response.output_tokens == 2
    assert response.usage is None


def test_model_response_accepts_normalized_usage():
    usage = TokenUsage(input_tokens=5, output_tokens=2)
    response = ModelResponse("bedrock", "model", "ok", 5, 2, usage)
    assert response.usage == usage
