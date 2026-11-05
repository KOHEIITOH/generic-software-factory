"""Provider-neutral token usage; unavailable metrics remain unknown."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None

    def __post_init__(self) -> None:
        for name in ("input_tokens", "output_tokens", "reasoning_tokens", "cache_read_tokens", "cache_write_tokens"):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError(f"{name} must be a non-negative integer or None")
