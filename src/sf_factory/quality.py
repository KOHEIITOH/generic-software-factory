"""Provider-neutral quality evidence and fail-closed gate evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class GateStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    MISSING = "missing"


@dataclass(frozen=True)
class QualityEvidence:
    """An independently produced observation; no commands are executed here."""

    check_id: str
    passed: bool
    detail: str = ""
    source: str = ""


@dataclass(frozen=True)
class QualityGate:
    id: str
    required: bool = True


@dataclass(frozen=True)
class GateResult:
    id: str
    status: GateStatus
    detail: str = ""
    source: str = ""


@dataclass(frozen=True)
class QualityReport:
    passed: bool
    gates: tuple[GateResult, ...]

    @property
    def feedback(self) -> str:
        return "\n".join(
            f"{gate.id}: {gate.status.value} {gate.detail}".strip()
            for gate in self.gates
            if gate.status is not GateStatus.PASSED
        )


def evaluate_quality(
    gates: tuple[QualityGate, ...],
    evidence: tuple[QualityEvidence, ...],
) -> QualityReport:
    """Match evidence by check ID; required checks without evidence fail closed."""
    ids = [gate.id for gate in gates]
    if any(not item.strip() for item in ids) or len(ids) != len(set(ids)):
        raise ValueError("gate IDs must be non-empty and unique")
    evidence_ids = [item.check_id for item in evidence]
    if any(not item.strip() for item in evidence_ids):
        raise ValueError("evidence check IDs must be non-empty")
    if len(evidence_ids) != len(set(evidence_ids)):
        raise ValueError("duplicate evidence check IDs")
    observed = {item.check_id: item for item in evidence}
    results: list[GateResult] = []
    passed = True
    for gate in gates:
        item = observed.get(gate.id)
        if item is None:
            results.append(GateResult(gate.id, GateStatus.MISSING))
            if gate.required:
                passed = False
        else:
            status = GateStatus.PASSED if item.passed else GateStatus.FAILED
            results.append(GateResult(gate.id, status, item.detail, item.source))
            if gate.required and not item.passed:
                passed = False
    return QualityReport(passed, tuple(results))
