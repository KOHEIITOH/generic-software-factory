"""Bounded, policy-aware improvement loop for injectable executors and evaluators.

This orchestration primitive does not itself invoke an AI, shell, or network.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from time import monotonic
from typing import Generic, TypeVar

from sf_factory.policy import (
    Capability,
    ExecutionPolicy,
    ExecutionRequest,
)

T = TypeVar("T")


class LoopStatus(StrEnum):
    SUCCEEDED = "succeeded"
    EXHAUSTED = "exhausted"
    TIMED_OUT = "timed-out"
    BLOCKED = "blocked"
    FAILED = "failed"


@dataclass(frozen=True)
class LoopLimits:
    max_attempts: int = 3
    timeout_seconds: int = 120

    def validate(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        if self.timeout_seconds < 1:
            raise ValueError("timeout_seconds must be positive")


@dataclass(frozen=True)
class AttemptRecord:
    number: int
    passed: bool
    feedback: str


@dataclass(frozen=True)
class LoopResult(Generic[T]):
    status: LoopStatus
    attempts: tuple[AttemptRecord, ...]
    output: T | None
    reason: str


def run_improvement_loop(
    execute: Callable[[int, str], T],
    evaluate: Callable[[T], tuple[bool, str]],
    *,
    capability: Capability = Capability.READ_ONLY,
    approved: bool = False,
    policy: ExecutionPolicy | None = None,
    limits: LoopLimits = LoopLimits(),
    clock: Callable[[], float] = monotonic,
) -> LoopResult[T]:
    """Iterate only while policy and budget allow; feedback informs next attempt.

    Timeout is cooperative: callbacks must enforce their own execution deadlines.
    """
    limits.validate()
    policy = policy if policy is not None else ExecutionPolicy()
    started = clock()
    attempts: list[AttemptRecord] = []
    feedback = ""
    last_output: T | None = None
    for number in range(1, limits.max_attempts + 1):
        elapsed = clock() - started
        remaining = limits.timeout_seconds - elapsed
        if remaining <= 0:
            return LoopResult(
                LoopStatus.TIMED_OUT, tuple(attempts), last_output, "time budget exhausted"
            )
        decision = policy.evaluate(
            ExecutionRequest(
                capability=capability,
                approved=approved,
                timeout_seconds=max(1, min(policy.max_timeout_seconds, int(remaining))),
                retry_count=number - 1,
            )
        )
        if not decision.allowed:
            return LoopResult(LoopStatus.BLOCKED, tuple(attempts), last_output, decision.reason)
        try:
            output = execute(number, feedback)
            last_output = output
            if clock() - started >= limits.timeout_seconds:
                return LoopResult(
                    LoopStatus.TIMED_OUT, tuple(attempts), last_output, "time budget exhausted"
                )
            passed, feedback = evaluate(output)
        except Exception as exc:
            return LoopResult(
                LoopStatus.FAILED, tuple(attempts), last_output,
                f"attempt {number} raised {type(exc).__name__}",
            )
        attempts.append(AttemptRecord(number, passed, feedback))
        if passed:
            return LoopResult(LoopStatus.SUCCEEDED, tuple(attempts), output, "quality gate passed")
    return LoopResult(
        LoopStatus.EXHAUSTED, tuple(attempts), last_output, "attempt budget exhausted"
    )
