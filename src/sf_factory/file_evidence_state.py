"""Atomic frozen evidence plans and observations in the local File document."""
from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import datetime
from typing import TYPE_CHECKING

from sf_factory import evidence_rules as rules
from sf_factory.factory import _now
from sf_factory.run_evidence import CheckObservation, CheckRequirement, EvidenceSubject, _identity
from sf_factory.run_review import parse_review
from sf_factory.state_store import StateConflict

if TYPE_CHECKING:
    from sf_factory.file_dashboard import FileDashboardFactory


def empty_evidence() -> dict:
    return {'plans': {}, 'review_plans': {}, 'checks': {}, 'reviews': {}}


class FileEvidenceState:
    def __init__(self, factory: FileDashboardFactory):
        self.factory = factory

    @staticmethod
    def _audit(state: dict, run_id: str, event: str) -> None:
        state['events'].append({'run_id': run_id, 'issue_key': state['runs'][run_id]['issue_key'],
                                'event': event, 'at': _now()})

    def register(self, run_id: str, subject: EvidenceSubject,
                 checks: tuple[CheckRequirement, ...], *, collector: str,
                 max_attempts: int = 3) -> None:
        with self.factory._document(edit=True) as state:
            run = state['runs'].get(run_id)
            manifest = state['harness']['manifests'].get(run_id)
            row = {**run, 'manifest': manifest['manifest']} if run and manifest else None
            rules.registration(row, subject)
            data = state['evidence']
            if run_id in data['plans']:
                raise StateConflict('check plan already registered')
            data['plans'][run_id] = {
                'run_id': run_id, 'subject': rules.encoded(asdict(subject)),
                'checks': rules.encoded({'requirements': [asdict(c)
                    for c in sorted(checks, key=lambda c: c.id)]}),
                'collector': collector, 'max_attempts': max_attempts,
            }
            self._audit(state, run_id, 'run.check_plan_registered')

    def record(self, run_id: str, subject: EvidenceSubject, *, attempt: int,
               observation: CheckObservation, collector: str) -> None:
        with self.factory._document(edit=True) as state:
            data = state['evidence']
            plan = rules.active_plan(data['plans'].get(run_id), state['runs'].get(run_id))
            rows = data['checks'].get(run_id, [])
            latest = max((row['attempt'] for row in rows), default=0)
            rules.check_observation(plan, run_id=run_id, subject=subject, collector=collector,
                                    observation=observation, attempt=attempt, latest=latest)
            if any(row['attempt'] == attempt and row['check_id'] == observation.check_id
                   for row in rows):
                raise StateConflict('check observation already recorded')
            data['checks'].setdefault(run_id, []).append({
                'attempt': attempt, 'check_id': observation.check_id,
                'observation': rules.encoded(asdict(observation)), 'recorded_at': _now(),
            })
            self._audit(state, run_id, 'run.check_observed')

    def register_review(self, run_id: str, *, reviewer: str, implementer: str,
                        changed_paths: tuple[str, ...]) -> None:
        with self.factory._document(edit=True) as state:
            data = state['evidence']
            run = state['runs'].get(run_id)
            if run is None or run['status'] != 'prepared':
                raise ValueError('prepared Run required')
            if run_id not in data['plans'] or run_id in data['review_plans']:
                raise StateConflict('check plan required and review plan must be new')
            data['review_plans'][run_id] = {
                'reviewer': reviewer, 'implementer': implementer,
                'paths': rules.encoded({'paths': sorted(changed_paths)}),
            }
            self._audit(state, run_id, 'run.review_plan_registered')

    def record_review(self, run_id: str, subject: EvidenceSubject, *, attempt: int,
                      reviewer: str, response: str) -> None:
        with self.factory._document(edit=True) as state:
            data = state['evidence']
            plan = data['plans'].get(run_id)
            review = data['review_plans'].get(run_id)
            joined = {**plan, **review} if plan and review else None
            latest = max((row['attempt'] for row in data['checks'].get(run_id, [])), default=0)
            rules.review_observation(joined, state['runs'].get(run_id), subject=subject,
                                     reviewer=reviewer, attempt=attempt, latest=latest)
            assert joined is not None
            summary = parse_review(response, run_id=run_id, subject=subject,
                                   required_paths=tuple(json.loads(joined['paths'])['paths']))
            if any(row['attempt'] == attempt for row in data['reviews'].get(run_id, [])):
                raise StateConflict('review observation already recorded')
            data['reviews'].setdefault(run_id, []).append({
                'attempt': attempt, 'summary': rules.encoded(asdict(summary)),
                'recorded_at': _now(),
            })
            self._audit(state, run_id, 'run.review_observed')

    def assessment(self, run_id: str, subject: EvidenceSubject
                   ) -> tuple[dict, list[dict], list[dict]]:
        with self.factory._document() as state:
            data = state['evidence']
            plan = rules.active_plan(data['plans'].get(run_id), state['runs'].get(run_id))
            rules.assessment_subject(plan, subject)
            return plan, data['checks'].get(run_id, []), data['reviews'].get(run_id, [])


def validate_evidence_state(state: dict) -> None:
    data = state['evidence']
    if set(data) != set(empty_evidence()) or not all(isinstance(v, dict) for v in data.values()):
        raise ValueError('invalid evidence collections')
    for run_id, plan in data['plans'].items():
        if set(plan) != {'run_id', 'subject', 'checks', 'collector', 'max_attempts'}:
            raise ValueError('invalid check plan')
        subject = EvidenceSubject(**json.loads(plan['subject']))
        if plan['run_id'] != run_id or plan['subject'] != rules.encoded(asdict(subject)):
            raise ValueError('invalid plan subject')
        _identity(plan['collector'])
        checks = tuple(CheckRequirement(**c) for c in json.loads(plan['checks'])['requirements'])
        canonical = rules.encoded({'requirements': [asdict(c)
            for c in sorted(checks, key=lambda c: c.id)]})
        if (plan['checks'] != canonical or not checks or len(checks) > 32
                or len({c.id for c in checks}) != len(checks)
                or not any(c.kind == 'tests' for c in checks)
                or type(plan['max_attempts']) is not int or not 1 <= plan['max_attempts'] <= 3):
            raise ValueError('invalid required check plan')
        manifest = state['harness']['manifests'][run_id]['manifest']
        rules.registration({'status': 'prepared', 'manifest': manifest}, subject)
    for run_id, plan in data['review_plans'].items():
        if run_id not in data['plans'] or set(plan) != {'reviewer', 'implementer', 'paths'}:
            raise ValueError('invalid review plan')
        rules.review_plan(plan['reviewer'], plan['implementer'],
                          tuple(json.loads(plan['paths'])['paths']))
    for run_id, rows in data['checks'].items():
        plan = data['plans'][run_id]
        subject = EvidenceSubject(**json.loads(plan['subject']))
        if not isinstance(rows, list) or not rows:
            raise ValueError('invalid check observations')
        seen = set()
        attempts = set()
        for row in rows:
            if (set(row) != {'attempt', 'check_id', 'observation', 'recorded_at'}
                    or type(row['attempt']) is not int or row['attempt'] < 1):
                raise ValueError('invalid observation row')
            observation = CheckObservation(**json.loads(row['observation']))
            identity = (row['attempt'], row['check_id'])
            if (identity in seen or row['check_id'] != observation.check_id
                    or datetime.fromisoformat(row['recorded_at']).utcoffset() is None):
                raise ValueError('invalid observation identity/time')
            seen.add(identity)
            attempts.add(row['attempt'])
            rules.check_observation(plan, run_id=run_id, subject=subject,
                                    collector=plan['collector'], observation=observation,
                                    attempt=row['attempt'], latest=row['attempt'])
        if attempts != set(range(1, max(attempts) + 1)):
            raise ValueError('skipped evidence attempt')
    for run_id, rows in data['reviews'].items():
        if run_id not in data['review_plans'] or not isinstance(rows, list) or not rows:
            raise ValueError('invalid review observations')
        attempts = {row['attempt'] for row in data['checks'].get(run_id, [])}
        seen = set()
        for row in rows:
            if (set(row) != {'attempt', 'summary', 'recorded_at'}
                    or type(row['attempt']) is not int or row['attempt'] not in attempts
                    or row['attempt'] in seen
                    or datetime.fromisoformat(row['recorded_at']).utcoffset() is None):
                raise ValueError('invalid review attempt/time')
            seen.add(row['attempt'])
            summary = json.loads(row['summary'])
            if (set(summary) != {'status', 'complete', 'truncated', 'must_fix', 'should',
                                 'nit', 'report_sha256'}
                    or summary['status'] not in {'completed', 'failed'}
                    or any(type(summary[k]) is not bool for k in ('complete', 'truncated'))
                    or any(type(summary[k]) is not int or not 0 <= summary[k] <= 100
                           for k in ('must_fix', 'should', 'nit'))
                    or not re.fullmatch(r'[a-f0-9]{64}', summary['report_sha256'])):
                raise ValueError('invalid review summary')
