"""Append-only, revision-bound check records for trusted local collectors.

This service records observations, not arbitrary commands or permission to ship.
The controller must verify producer identity and the actual checked revision.
"""
from __future__ import annotations

import json
import re
from contextlib import closing
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath

from sf_factory.factory import Factory, _now
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
    """Keep a frozen check plan and bounded attempts, using the existing Factory DB.

    Registration is a trusted controller action after implementation; it does
    not independently prove commit ancestry, snapshot integrity, or identity.
    An attempt never reuses successful results from a different attempt.
    """

    def __init__(self, factory: Factory):
        self.factory = factory
        with closing(factory._connect()) as db, db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS run_evidence_plans (
                    run_id TEXT PRIMARY KEY REFERENCES runs(id), subject TEXT NOT NULL,
                    checks TEXT NOT NULL, collector TEXT NOT NULL, max_attempts INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS run_review_plans (
                    run_id TEXT PRIMARY KEY REFERENCES run_evidence_plans(run_id),
                    reviewer TEXT NOT NULL, implementer TEXT NOT NULL, paths TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS run_review_observations (
                    run_id TEXT NOT NULL REFERENCES run_review_plans(run_id),
                    attempt INTEGER NOT NULL, summary TEXT NOT NULL, recorded_at TEXT NOT NULL,
                    PRIMARY KEY(run_id,attempt)
                );
                CREATE TABLE IF NOT EXISTS run_check_observations (
                    run_id TEXT NOT NULL REFERENCES run_evidence_plans(run_id),
                    attempt INTEGER NOT NULL, check_id TEXT NOT NULL,
                    observation TEXT NOT NULL, recorded_at TEXT NOT NULL,
                    PRIMARY KEY(run_id,attempt,check_id)
                );
            ''')

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
        with closing(self.factory._connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute(
                'SELECT r.task_id,r.status,m.manifest FROM runs r '
                'JOIN run_harness_manifests m ON m.run_id=r.id WHERE r.id=?', (run_id,),
            ).fetchone()
            if row is None or row['status'] != 'prepared':
                raise ValueError('a prepared Harness Run is required')
            manifest = json.loads(row['manifest'])
            if manifest['request']['bundle_hash'] != subject.bundle_hash:
                raise PermissionError('evidence does not match approved Harness bundle')
            db.execute('INSERT INTO run_evidence_plans VALUES (?,?,?,?,?)', (
                run_id, _encoded(asdict(subject)),
                _encoded({'requirements': [asdict(c) for c in sorted(checks, key=lambda c: c.id)]}),
                collector, max_attempts,
            ))
            db.execute('INSERT INTO audit(run_id,task_id,event,at) VALUES (?,?,?,?)',
                       (run_id, row['task_id'], 'run.check_plan_registered', _now()))

    def record(
        self, run_id: str, subject: EvidenceSubject, *, attempt: int,
        observation: CheckObservation, collector: str,
    ) -> None:
        _identity(collector)
        if type(attempt) is not int or attempt < 1:
            raise ValueError('positive attempt required')
        with closing(self.factory._connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            plan = db.execute(
                'SELECT * FROM run_evidence_plans WHERE run_id=?', (run_id,),
            ).fetchone()
            if plan is None:
                raise ValueError('check plan not found')
            run = db.execute('SELECT status FROM runs WHERE id=?', (run_id,)).fetchone()
            if run is None or run['status'] != 'prepared':
                raise ValueError('Run is no longer in the supported prepared state')
            if (plan['subject'] != _encoded(asdict(subject)) or collector != plan['collector']
                    or observation.run_id != run_id):
                raise PermissionError('wrong revision, bundle, diff or collector')
            latest = db.execute('SELECT COALESCE(MAX(attempt),0) FROM run_check_observations '
                                'WHERE run_id=?', (run_id,)).fetchone()[0]
            if attempt > plan['max_attempts'] or attempt < latest or attempt > latest + 1:
                raise ValueError('stale, skipped or exhausted attempt')
            checks = {c['id']: c['kind'] for c in json.loads(plan['checks'])['requirements']}
            if observation.check_id not in checks:
                raise ValueError('unplanned check')
            if checks[observation.check_id] != 'tests' and observation.tests_run is not None:
                raise ValueError('test counts apply only to test checks')
            db.execute('INSERT INTO run_check_observations VALUES (?,?,?,?,?)', (
                run_id, attempt, observation.check_id, _encoded(asdict(observation)), _now(),
            ))
            task_id = db.execute('SELECT task_id FROM runs WHERE id=?', (run_id,)).fetchone()[0]
            db.execute('INSERT INTO audit(run_id,task_id,event,at) VALUES (?,?,?,?)',
                       (run_id, task_id, 'run.check_observed', _now()))

    def register_review(
        self, run_id: str, *, reviewer: str, implementer: str, changed_paths: tuple[str, ...],
    ) -> None:
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
        with closing(self.factory._connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            run = db.execute('SELECT status,task_id FROM runs WHERE id=?', (run_id,)).fetchone()
            if run is None or run['status'] != 'prepared':
                raise ValueError('prepared Run required')
            db.execute('INSERT INTO run_review_plans VALUES (?,?,?,?)',
                       (run_id, reviewer, implementer, _encoded({'paths': sorted(changed_paths)})))
            db.execute('INSERT INTO audit(run_id,task_id,event,at) VALUES (?,?,?,?)',
                       (run_id, run['task_id'], 'run.review_plan_registered', _now()))

    def record_review(
        self, run_id: str, subject: EvidenceSubject, *, attempt: int, reviewer: str, response: str,
    ) -> None:
        from sf_factory.run_review import parse_review

        _identity(reviewer)
        if type(attempt) is not int or attempt < 1:
            raise ValueError('positive review attempt required')
        with closing(self.factory._connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            plan = db.execute(
                'SELECT p.subject,r.reviewer,r.paths FROM run_evidence_plans p '
                'JOIN run_review_plans r ON r.run_id=p.run_id WHERE p.run_id=?', (run_id,),
            ).fetchone()
            run = db.execute('SELECT status,task_id FROM runs WHERE id=?', (run_id,)).fetchone()
            if plan is None or run is None or run['status'] != 'prepared':
                raise ValueError('active review plan required')
            if plan['subject'] != _encoded(asdict(subject)) or reviewer != plan['reviewer']:
                raise PermissionError('review subject or producer mismatch')
            latest = db.execute('SELECT COALESCE(MAX(attempt),0) FROM run_check_observations '
                                'WHERE run_id=?', (run_id,)).fetchone()[0]
            if latest != attempt:
                raise ValueError('review must match latest check attempt')
            summary = parse_review(response, run_id=run_id, subject=subject,
                                   required_paths=tuple(json.loads(plan['paths'])['paths']))
            db.execute('INSERT INTO run_review_observations VALUES (?,?,?,?)',
                       (run_id, attempt, _encoded(asdict(summary)), _now()))
            db.execute('INSERT INTO audit(run_id,task_id,event,at) VALUES (?,?,?,?)',
                       (run_id, run['task_id'], 'run.review_observed', _now()))

    def assess(self, run_id: str, subject: EvidenceSubject) -> dict:
        with closing(self.factory._connect()) as db, db:
            db.execute('BEGIN')
            plan = db.execute(
                'SELECT * FROM run_evidence_plans WHERE run_id=?', (run_id,),
            ).fetchone()
            if plan is None:
                raise ValueError('check plan not found')
            run = db.execute('SELECT status FROM runs WHERE id=?', (run_id,)).fetchone()
            if run is None or run['status'] != 'prepared':
                raise ValueError('Run is no longer in the supported prepared state')
            if plan['subject'] != _encoded(asdict(subject)):
                raise PermissionError('assessment subject does not match the check plan')
            # One read transaction so a concurrent new attempt cannot mix observations.
            rows = db.execute('SELECT attempt,observation FROM run_check_observations '
                              'WHERE run_id=? ORDER BY attempt,check_id', (run_id,)).fetchall()
            review_rows = db.execute('SELECT attempt,summary FROM run_review_observations '
                                     'WHERE run_id=?', (run_id,)).fetchall()
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
