"""Atomic per-Run evidence operations; no database connection crosses this boundary."""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from sf_factory.run_evidence import CheckObservation, CheckRequirement, EvidenceSubject


class EvidenceState(Protocol):
    def register(self, run_id: str, subject: EvidenceSubject,
                 checks: tuple[CheckRequirement, ...], *, collector: str,
                 max_attempts: int = 3) -> None: ...

    def record(self, run_id: str, subject: EvidenceSubject, *, attempt: int,
               observation: CheckObservation, collector: str) -> None: ...

    def register_review(self, run_id: str, *, reviewer: str, implementer: str,
                        changed_paths: tuple[str, ...]) -> None: ...

    def record_review(self, run_id: str, subject: EvidenceSubject, *, attempt: int,
                      reviewer: str, response: str) -> None: ...

    def assessment(self, run_id: str, subject: EvidenceSubject
                   ) -> tuple[dict, list[dict], list[dict]]:
        """One consistent snapshot of the exact plan/check/review attempt data."""
        ...
