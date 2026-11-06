"""SQLite persistence for frozen evidence plans and append-only observations."""
from __future__ import annotations

import json
from contextlib import closing
from dataclasses import asdict

from sf_factory.factory import Factory, _now
from sf_factory.run_evidence import (
    CheckObservation,
    CheckRequirement,
    EvidenceSubject,
    _encoded,
)
from sf_factory.run_review import parse_review


class SqliteEvidenceState:
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

    def assessment(self, run_id: str, subject: EvidenceSubject):
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
        return dict(plan), [dict(row) for row in rows], [dict(row) for row in review_rows]

