"""AWS Bedrock Converse model provider (inference only)."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any

from sf_factory.model_provider import ModelResponse
from sf_factory.usage import TokenUsage


@dataclass(frozen=True)
class BedrockModelProvider:
    model_id: str
    region_name: str
    max_tokens: int = 1024
    temperature: float = 0.0

    def __post_init__(self) -> None:
        if not self.model_id.strip():
            raise ValueError("model_id is required")
        if not self.region_name.strip():
            raise ValueError("region_name is required")
        if not 1 <= self.max_tokens <= 8192:
            raise ValueError("max_tokens must be between 1 and 8192")
        if not 0.0 <= self.temperature <= 1.0:
            raise ValueError("temperature must be between 0 and 1")

    def generate(self, prompt: str) -> ModelResponse:
        if not prompt.strip():
            raise ValueError("prompt must not be empty")
        try:
            boto3 = import_module("boto3")
        except ImportError as exc:
            raise RuntimeError("Install the bedrock extra: pip install -e '.[bedrock]'") from exc

        try:
            client = boto3.client("bedrock-runtime", region_name=self.region_name)
            response: dict[str, Any] = client.converse(
                modelId=self.model_id,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={
                    "maxTokens": self.max_tokens,
                    "temperature": self.temperature,
                },
            )
        except Exception as exc:
            # Do not expose credential or request internals to callers.
            raise RuntimeError("AWS Bedrock inference failed; check model access and IAM") from exc
        content = response.get("output", {}).get("message", {}).get("content", [])
        text = "".join(block["text"] for block in content if isinstance(block, dict)
                       and isinstance(block.get("text"), str))
        if not text:
            raise RuntimeError("AWS Bedrock returned no text content")
        usage = response.get("usage", {})
        return ModelResponse(
            provider="bedrock", model_id=self.model_id, text=text,
            input_tokens=usage.get("inputTokens"),
            output_tokens=usage.get("outputTokens"),
            usage=TokenUsage(
                input_tokens=usage.get("inputTokens"),
                output_tokens=usage.get("outputTokens"),
                cache_read_tokens=usage.get("cacheReadInputTokens"),
                cache_write_tokens=usage.get("cacheWriteInputTokens"),
            ),
        )
