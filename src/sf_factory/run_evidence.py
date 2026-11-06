"""Append-only, revision-bound check records for trusted local collectors.

This service records observations, not arbitrary commands or permission to ship.
The controller must verify producer identity and the actual checked revision.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from sf_factory import evidence_rules as rules
from sf_factory.factory import Factory
from sf_factory.quality import QualityEvidence, QualityGate, evaluate_quality


@dataclass(frozen=True)
class EvidenceSubject:
    revision: str
    bundle_hash: str
    diff_sha256: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r'(?:[a-f0-9]{40}|[a-f0-9]{64})', self.revision):
            raise ValueError('exact checked revision required')
        for value in (self.bundle_hash, self.diff_sha256):
            if not re.fullmatch(r'[a-f0-9]{64}', value):
                raise ValueError('exact bundle and diff hashes required')


@dataclass(frozen=True)
class CheckRequirement:
    id: str
    kind: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', self.id):
            raise ValueError('bounded check identifier required')
        if self.kind not in {'tests', 'lint', 'build', 'security'}:
            raise ValueError('unsupported check kind')


@dataclass(frozen=True)
class CheckObservation:
    check_id: str
    status: str
    exit_code: int | None
    report_sha256: str
    tests_run: int | None = None
    run_id: str = ''

    def __post_init__(self) -> None:
        if not re.fullmatch(r'[a-f0-9]{32}', self.run_id):
            raise ValueError('source Run identifier required')
        if not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', self.check_id):
            raise ValueError('bounded check identifier required')
        if self.status not in {'completed', 'failed', 'skipped', 'error'}:
            raise ValueError('unsupported check outcome')
        if self.exit_code is not None and (
            type(self.exit_code) is not int or not 0 <= self.exit_code <= 255
        ):
            raise ValueError('invalid exit code')
        if self.tests_run is not None and (type(self.tests_run) is not int or self.tests_run < 0):
            raise ValueError('nonnegative executed test count required')
        if not re.fullmatch(r'[a-f0-9]{64}', self.report_sha256):
            raise ValueError('checked report hash required')
        if self.status == 'completed' and self.exit_code != 0:
            raise ValueError('completed checks require exit code zero')
        if self.status == 'failed' and self.exit_code in {None, 0}:
            raise ValueError('failed checks require a nonzero exit code')
        if self.status in {'skipped', 'error'} and self.exit_code is not None:
            raise ValueError('unexecuted checks cannot have an exit code')


def _identity(value: str) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > 128 or '\x00' in value:
        raise ValueError('verified collector identity required')


def _encoded(value: dict) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


class RunEvidenceService:
    """Keep a frozen check plan and bounded attempts with optional persistence adapters.

    Registration is a trusted controller action after implementation; it does
    not independently prove commit ancestry, snapshot integrity, or identity.
    An attempt never reuses successful results from a different attempt.
    """

    def __init__(self, factory: Factory):
        self.factory = factory
        self.state = factory.evidence_state()

    def register(
        self, run_id: str, subject: EvidenceSubject, checks: tuple[CheckRequirement, ...],
        *, collector: str, max_attempts: int = 3,
    ) -> None:
        _identity(collector)
        if (not checks or len(checks) > 32 or len({c.id for c in checks}) != len(checks)
                or not any(c.kind == 'tests' for c in checks)):
            raise ValueError('unique required checks including tests are required')
        if type(max_attempts) is not int or not 1 <= max_attempts <= 3:
            raise ValueError('attempt limit must be between one and three')
        self.state.register(run_id, subject, checks, collector=collector, max_attempts=max_attempts)

    def record(
        self, run_id: str, subject: EvidenceSubject, *, attempt: int,
        observation: CheckObservation, collector: str,
    ) -> None:
        _identity(collector)
        if type(attempt) is not int or attempt < 1:
            raise ValueError('positive attempt required')
        self.state.record(run_id, subject, attempt=attempt,
                          observation=observation, collector=collector)

    def register_review(
        self, run_id: str, *, reviewer: str, implementer: str, changed_paths: tuple[str, ...],
    ) -> None:
        rules.review_plan(reviewer, implementer, changed_paths)
        self.state.register_review(run_id, reviewer=reviewer, implementer=implementer,
                                   changed_paths=changed_paths)

    def record_review(
        self, run_id: str, subject: EvidenceSubject, *, attempt: int, reviewer: str, response: str,
    ) -> None:
        _identity(reviewer)
        if type(attempt) is not int or attempt < 1:
            raise ValueError('positive review attempt required')
        self.state.record_review(run_id, subject, attempt=attempt,
                                 reviewer=reviewer, response=response)

    def assess(self, run_id: str, subject: EvidenceSubject) -> dict:
        plan, rows, review_rows = self.state.assessment(run_id, subject)
        latest = max((row['attempt'] for row in rows), default=0)
        review = next((json.loads(row['summary']) for row in review_rows
                       if row['attempt'] == latest), None)
        review_status = 'missing'
        if review is not None:
            if review['status'] != 'completed':
                review_status = 'failed'
            elif not review['complete'] or review['truncated']:
                review_status = 'incomplete'
            elif review['must_fix']:
                review_status = 'must_fix'
            else:
                review_status = 'passed'
        observed = {item['check_id']: item for item in (
            json.loads(row['observation']) for row in rows if row['attempt'] == latest
        )}
        requirements = json.loads(plan['checks'])['requirements']
        evidence = []
        outcomes = []
        for requirement in requirements:
            item = observed.get(requirement['id'])
            outcome = 'missing'
            if item is not None:
                outcome = item['status']
                passed = outcome == 'completed' and item['exit_code'] == 0
                if requirement['kind'] == 'tests' and not (item['tests_run'] or 0) > 0:
                    passed = False
                    if outcome == 'completed':
                        outcome = 'zero_or_unknown_tests'
                evidence.append(QualityEvidence(requirement['id'], passed,
                                                detail=outcome, source=plan['collector']))
            outcomes.append({'id': requirement['id'], 'outcome': outcome})
        report = evaluate_quality(
            tuple(QualityGate(c['id']) for c in requirements), tuple(evidence),
        )
        return {
            'subject': json.loads(plan['subject']), 'attempt': latest,
            'checks_passed': report.passed, 'checks': outcomes,
            'review_status': review_status, 'review': review,
            'evidence_complete': report.passed and review_status == 'passed',
            'eligible_for_delivery': False,
        }
