"""In-memory, provider-neutral usage tracking without price assumptions."""

from __future__ import annotations

from dataclasses import dataclass, field

from sf_factory.model_provider import ModelResponse
from sf_factory.usage import TokenUsage


@dataclass(frozen=True)
class UsageRecord:
    task_id: str
    provider: str
    model_id: str
    usage: TokenUsage
    attempt: int = 1

    def __post_init__(self) -> None:
        if not self.task_id.strip():
            raise ValueError("task_id is required")
        if self.attempt < 1:
            raise ValueError("attempt must be positive")


@dataclass
class UsageTracker:
    """Collect per-attempt usage. No persistence, prices or automatic calls."""

    records: list[UsageRecord] = field(default_factory=list)

    def record(self, task_id: str, response: ModelResponse, *, attempt: int = 1) -> UsageRecord:
        usage = response.usage or TokenUsage(
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
        )
        record = UsageRecord(task_id, response.provider, response.model_id, usage, attempt)
        self.records.append(record)
        return record

    def totals(self, task_id: str) -> TokenUsage:
        selected = [record.usage for record in self.records if record.task_id == task_id]

        def sum_known(field_name: str) -> int | None:
            values = [getattr(usage, field_name) for usage in selected]
            if not values or any(value is None for value in values):
                return None
            return sum(values)

        return TokenUsage(
            input_tokens=sum_known("input_tokens"),
            output_tokens=sum_known("output_tokens"),
            reasoning_tokens=sum_known("reasoning_tokens"),
            cache_read_tokens=sum_known("cache_read_tokens"),
            cache_write_tokens=sum_known("cache_write_tokens"),
        )
