"""Usage tracker tests."""

from sf_factory.model_provider import ModelResponse
from sf_factory.usage import TokenUsage
from sf_factory.usage_tracker import UsageTracker


def test_tracks_multiple_attempts_and_task_isolation():
    tracker = UsageTracker()
    tracker.record("task-1", ModelResponse("bedrock", "a", "ok", 10, 2))
    tracker.record("task-1", ModelResponse("bedrock", "a", "ok", 20, 3), attempt=2)
    tracker.record("task-2", ModelResponse("bedrock", "a", "ok", 100, 100))
    assert tracker.totals("task-1").input_tokens == 30
    assert tracker.totals("task-1").output_tokens == 5
    assert tracker.totals("task-2").input_tokens == 100


def test_unknown_is_not_silently_treated_as_zero():
    tracker = UsageTracker()
    tracker.record("task", ModelResponse("bedrock", "a", "ok", 10, 2))
    tracker.record("task", ModelResponse("bedrock", "a", "ok"))
    assert tracker.totals("task").input_tokens is None
    assert tracker.totals("task").output_tokens is None
    assert tracker.totals("missing").input_tokens is None


def test_uses_normalized_usage_when_available():
    tracker = UsageTracker()
    response = ModelResponse(
        "bedrock", "a", "ok",
        usage=TokenUsage(input_tokens=4, output_tokens=2, cache_read_tokens=1),
    )
    tracker.record("task", response)
    assert tracker.totals("task").cache_read_tokens == 1
