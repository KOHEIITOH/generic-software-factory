"""Backend-neutral validation of revision/producer/attempt-bound evidence."""
from __future__ import annotations

import json
from dataclasses import asdict
from typing import TYPE_CHECKING

from sf_factory.state_store import StatePermissionDenied

if TYPE_CHECKING:
    from sf_factory.run_evidence import CheckObservation, EvidenceSubject


def encoded(value: dict) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def registration(row: dict | None, subject: EvidenceSubject) -> None:
    if row is None or row['status'] != 'prepared':
        raise ValueError('a prepared Harness Run is required')
    if json.loads(row['manifest'])['request']['bundle_hash'] != subject.bundle_hash:
        raise StatePermissionDenied('evidence does not match approved Harness bundle')


def active_plan(plan: dict | None, run: dict | None) -> dict:
    if plan is None:
        raise ValueError('check plan not found')
    if run is None or run['status'] != 'prepared':
        raise ValueError('Run is no longer in the supported prepared state')
    return plan


def check_observation(plan: dict, *, run_id: str, subject: EvidenceSubject, collector: str,
                      observation: CheckObservation, attempt: int, latest: int) -> None:
    if (plan['subject'] != encoded(asdict(subject)) or collector != plan['collector']
            or observation.run_id != run_id):
        raise StatePermissionDenied('wrong revision, bundle, diff or collector')
    if attempt > plan['max_attempts'] or attempt < latest or attempt > latest + 1:
        raise ValueError('stale, skipped or exhausted attempt')
    checks = {c['id']: c['kind'] for c in json.loads(plan['checks'])['requirements']}
    if observation.check_id not in checks:
        raise ValueError('unplanned check')
    if checks[observation.check_id] != 'tests' and observation.tests_run is not None:
        raise ValueError('test counts apply only to test checks')


def review_observation(plan: dict | None, run: dict | None, *, subject: EvidenceSubject,
                       reviewer: str, attempt: int, latest: int) -> None:
    if plan is None or run is None or run['status'] != 'prepared':
        raise ValueError('active review plan required')
    if plan['subject'] != encoded(asdict(subject)) or reviewer != plan['reviewer']:
        raise StatePermissionDenied('review subject or producer mismatch')
    if latest != attempt:
        raise ValueError('review must match latest check attempt')


def assessment_subject(plan: dict, subject: EvidenceSubject) -> None:
    if plan['subject'] != encoded(asdict(subject)):
        raise StatePermissionDenied('assessment subject does not match the check plan')


def review_plan(reviewer: str, implementer: str, changed_paths: tuple[str, ...]) -> None:
    from pathlib import PurePosixPath

    from sf_factory.run_evidence import _identity

    _identity(reviewer)
    _identity(implementer)
    if reviewer == implementer:
        raise ValueError('independent reviewer identity required')
    if (not changed_paths or len(changed_paths) > 256
            or len(set(changed_paths)) != len(changed_paths)):
        raise ValueError('bounded unique changed paths required')
    for path in changed_paths:
        relative = PurePosixPath(path)
        if (not path or len(path) > 512 or '\\' in path or '\x00' in path
                or relative.is_absolute() or '..' in relative.parts
                or not relative.parts or relative.as_posix() != path):
            raise ValueError('canonical relative changed paths required')
