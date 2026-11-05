"""Provider-neutral text inference contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sf_factory.usage import TokenUsage


@dataclass(frozen=True)
class ModelResponse:
    provider: str
    model_id: str
    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    usage: TokenUsage | None = None


class ModelProvider(Protocol):
    def generate(self, prompt: str) -> ModelResponse:
        """Generate text without granting workspace or tool permissions."""
        ...
