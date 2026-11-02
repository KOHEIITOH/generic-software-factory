import pytest

from sf_factory.improvement import LoopLimits, LoopStatus
from sf_factory.policy import Capability
from sf_factory.quality import QualityEvidence, QualityGate
from sf_factory.quality_loop import run_quality_improvement_loop


def test_failed_check_feedback_drives_next_attempt() -> None:
    seen: list[tuple[int, str]] = []

    def execute(number: int, feedback: str) -> int:
        seen.append((number, feedback))
        return number

    def collect(number: int) -> tuple[QualityEvidence, ...]:
        return (QualityEvidence("tests", number > 1, "tests failed" if number == 1 else ""),)

    result = run_quality_improvement_loop(
        execute, collect, gates=(QualityGate("tests"),)
    )
    assert result.status is LoopStatus.SUCCEEDED
    assert len(result.attempts) == 2
    assert seen == [(1, ""), (2, "tests: failed tests failed")]


def test_missing_required_evidence_exhausts_budget() -> None:
    result = run_quality_improvement_loop(
        lambda number, feedback: number,
        lambda output: (),
        gates=(QualityGate("tests"),),
        limits=LoopLimits(max_attempts=2),
    )
    assert result.status is LoopStatus.EXHAUSTED
    assert len(result.attempts) == 2
    assert all(not attempt.passed for attempt in result.attempts)


def test_default_policy_blocks_write_before_execution() -> None:
    calls: list[int] = []
    result = run_quality_improvement_loop(
        lambda number, feedback: calls.append(number),
        lambda output: (QualityEvidence("tests", True),),
        gates=(QualityGate("tests"),),
        capability=Capability.WORKSPACE_WRITE,
    )
    assert result.status is LoopStatus.BLOCKED
    assert not calls


def test_invalid_gate_configuration_fails_before_execution() -> None:
    calls: list[int] = []
    with pytest.raises(ValueError):
        run_quality_improvement_loop(
            lambda number, feedback: calls.append(number),
            lambda output: (),
            gates=(),
        )
    assert not calls


def test_collector_exception_fails_closed() -> None:
    def broken(output: int) -> tuple[QualityEvidence, ...]:
        raise RuntimeError("collector failure")

    result = run_quality_improvement_loop(
        lambda number, feedback: number,
        broken,
        gates=(QualityGate("tests"),),
    )
    assert result.status is LoopStatus.FAILED
