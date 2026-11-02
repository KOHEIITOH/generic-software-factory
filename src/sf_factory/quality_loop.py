"""Connect independent quality evidence to the bounded improvement loop."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from sf_factory.improvement import LoopLimits, LoopResult, run_improvement_loop
from sf_factory.policy import Capability, ExecutionPolicy
from sf_factory.quality import QualityEvidence, QualityGate, evaluate_quality

T = TypeVar("T")


def run_quality_improvement_loop(
    execute: Callable[[int, str], T],
    collect_evidence: Callable[[T], tuple[QualityEvidence, ...]],
    *,
    gates: tuple[QualityGate, ...],
    capability: Capability = Capability.READ_ONLY,
    approved: bool = False,
    policy: ExecutionPolicy | None = None,
    limits: LoopLimits = LoopLimits(),
) -> LoopResult[T]:
    """Retry failed quality checks within policy limits.

    The evidence collector must be independently trusted by the caller.
    This wrapper does not execute shell commands or verify evidence provenance.
    """
    # Validate configuration before invoking an executor.
    evaluate_quality(gates, ())

    def evaluate(output: T) -> tuple[bool, str]:
        report = evaluate_quality(gates, collect_evidence(output))
        return report.passed, report.feedback

    return run_improvement_loop(
        execute,
        evaluate,
        capability=capability,
        approved=approved,
        policy=policy,
        limits=limits,
    )
