from sf_factory.improvement import LoopLimits, LoopStatus, run_improvement_loop
from sf_factory.policy import Capability, ExecutionPolicy


def test_retries_using_feedback_until_quality_gate_passes() -> None:
    seen: list[tuple[int, str]] = []

    def execute(number: int, feedback: str) -> int:
        seen.append((number, feedback))
        return number

    def evaluate(value: int) -> tuple[bool, str]:
        return value >= 2, "try again"

    result = run_improvement_loop(execute, evaluate)
    assert result.status is LoopStatus.SUCCEEDED
    assert seen == [(1, ""), (2, "try again")]
    assert len(result.attempts) == 2


def test_exhaustion_stops_at_attempt_budget() -> None:
    result = run_improvement_loop(
        lambda number, feedback: number,
        lambda output: (False, "not yet"),
        limits=LoopLimits(max_attempts=2),
    )
    assert result.status is LoopStatus.EXHAUSTED
    assert len(result.attempts) == 2


def test_default_policy_blocks_writes_before_callback() -> None:
    calls: list[int] = []
    result = run_improvement_loop(
        lambda number, feedback: calls.append(number),
        lambda output: (True, "ok"),
        capability=Capability.WORKSPACE_WRITE,
    )
    assert result.status is LoopStatus.BLOCKED
    assert calls == []


def test_explicit_write_approval_still_respects_retry_policy() -> None:
    result = run_improvement_loop(
        lambda number, feedback: number,
        lambda output: (False, "retry"),
        capability=Capability.WORKSPACE_WRITE,
        approved=True,
        policy=ExecutionPolicy(allow_workspace_write=True, max_retries=1),
        limits=LoopLimits(max_attempts=5),
    )
    assert result.status is LoopStatus.BLOCKED
    assert len(result.attempts) == 2


def test_timeout_before_first_attempt() -> None:
    ticks = iter([0.0, 10.0])
    result = run_improvement_loop(
        lambda number, feedback: number,
        lambda output: (True, "ok"),
        limits=LoopLimits(timeout_seconds=2),
        clock=lambda: next(ticks),
    )
    assert result.status is LoopStatus.TIMED_OUT


def test_callback_exception_fails_without_retry() -> None:
    def broken(number: int, feedback: str) -> int:
        raise RuntimeError("failure")

    result = run_improvement_loop(broken, lambda output: (True, "ok"))
    assert result.status is LoopStatus.FAILED
    assert not result.attempts


def test_invalid_limits_are_rejected() -> None:
    for limits in (LoopLimits(max_attempts=0), LoopLimits(timeout_seconds=0)):
        try:
            limits.validate()
        except ValueError:
            continue
        raise AssertionError("expected ValueError")
