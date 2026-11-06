"""Persist exact, expiring, single-use Harness decisions for a trusted controller.

This module does not authenticate reviewers, expose HTTP approval, or authorize
AI execution. The caller must establish identity and review permissions first.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sf_factory.harness_validation import HarnessValidation


def harness_bundle_hash(validation: HarnessValidation) -> str:
    """Fingerprint validated candidates and references; do not resolve rule conflicts."""
    if (validation.schema_version != 1 or not validation.valid or validation.issues
            or not validation.discovery.complete or validation.discovery.issues
            or not validation.discovery.candidates):
        raise ValueError('a nonempty validated inventory without unresolved issues is required')
    payload = {
        'schema_version': 1,
        'candidates': sorted((asdict(c) for c in validation.discovery.candidates),
                             key=lambda c: c['path']),
        'profiles': sorted((asdict(p) for p in validation.profiles), key=lambda p: p['path']),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class HarnessApprovalRequest:
    project_id: str
    repository_id: str
    task_id: str
    revision: str
    bundle_hash: str
    operation: str = 'apply_harness'

    def __post_init__(self) -> None:
        for value in (self.project_id, self.repository_id, self.task_id):
            if (not isinstance(value, str) or not value.strip()
                    or len(value) > 512 or '\x00' in value):
                raise ValueError('bounded project, repository and task identifiers required')
        if not re.fullmatch(r'(?:[a-f0-9]{40}|[a-f0-9]{64})', self.revision):
            raise ValueError('exact repository revision required')
        if not re.fullmatch(r'[a-f0-9]{64}', self.bundle_hash):
            raise ValueError('exact bundle hash required')
        if self.operation != 'apply_harness':
            raise ValueError('Harness decisions cannot authorize other operations')


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('timezone-aware timestamps required')
    return value.astimezone(UTC)


class HarnessApprovalStore:
    """Local persistence only; consume atomically before applying an exact bundle.

    Store outside untrusted repository snapshots. Reviewer identity/permissions
    must be supplied by an authenticated controller, never repository content.
    """

    def __init__(self, database: Path, *, clock: Callable[[], datetime] | None = None):
        self.database = database
        self.clock = clock or (lambda: datetime.now(UTC))
        with self._connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS harness_approvals (
                    id TEXT PRIMARY KEY, request TEXT NOT NULL, reviewer TEXT NOT NULL,
                    approved INTEGER NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
                    revoked INTEGER NOT NULL DEFAULT 0, consumed INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS harness_approval_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    approval_id TEXT NOT NULL REFERENCES harness_approvals(id),
                    event TEXT NOT NULL, actor TEXT NOT NULL, at TEXT NOT NULL
                );
            ''')

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.database, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _request(request: HarnessApprovalRequest) -> str:
        return json.dumps(asdict(request), sort_keys=True, separators=(',', ':'))

    @staticmethod
    def _actor(actor: str) -> None:
        if not isinstance(actor, str) or not actor.strip() or len(actor) > 512 or '\x00' in actor:
            raise ValueError('verified reviewer or controller identity required')

    def record(
        self, request: HarnessApprovalRequest, *, reviewer: str,
        approved: bool, expires_at: datetime,
    ) -> str:
        """Record a human decision after caller authentication; never execute anything."""
        self._actor(reviewer)
        if type(approved) is not bool:
            raise ValueError('explicit boolean decision required')
        now, expiry = _utc(self.clock()), _utc(expires_at)
        if not now < expiry <= now + timedelta(hours=24):
            raise ValueError('expiry must be in the next 24 hours')
        approval_id = uuid.uuid4().hex
        with self._connect() as db:
            db.execute(
                'INSERT INTO harness_approvals '
                '(id,request,reviewer,approved,created_at,expires_at) VALUES (?,?,?,?,?,?)',
                (approval_id, self._request(request), reviewer, int(approved),
                 now.isoformat(), expiry.isoformat()),
            )
            db.execute('INSERT INTO harness_approval_events(approval_id,event,actor,at) '
                       'VALUES (?,?,?,?)',
                       (approval_id, 'approved' if approved else 'rejected',
                        reviewer, now.isoformat()))
        return approval_id

    def consume(
        self, approval_id: str, request: HarnessApprovalRequest, *, controller: str,
    ) -> None:
        """Atomically claim once; caller must revalidate current revision/bundle first."""
        self._actor(controller)
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._consume_in_transaction(db, approval_id, request, controller=controller)

    def _consume_in_transaction(
        self, db: sqlite3.Connection, approval_id: str, request: HarnessApprovalRequest,
        *, controller: str,
    ) -> None:
        """Internal shared-DB hook so Run insertion and approval claim commit together."""
        self._actor(controller)
        if not db.in_transaction:
            raise ValueError('an explicit transaction is required')
        now = _utc(self.clock())
        row = db.execute(
            'SELECT * FROM harness_approvals WHERE id=?', (approval_id,),
        ).fetchone()
        if (row is None or row['request'] != self._request(request) or not row['approved']
                or row['revoked'] or row['consumed']
                or datetime.fromisoformat(row['expires_at']) <= now
                or datetime.fromisoformat(row['created_at']) > now):
            raise PermissionError('no matching active Harness approval')
        db.execute('UPDATE harness_approvals SET consumed=1 WHERE id=?', (approval_id,))
        db.execute('INSERT INTO harness_approval_events(approval_id,event,actor,at) '
                   'VALUES (?,?,?,?)', (approval_id, 'consumed', controller, now.isoformat()))

    def revoke(self, approval_id: str, *, reviewer: str) -> None:
        """Record revocation; cancelling already-started work requires the run controller."""
        self._actor(reviewer)
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            updated = db.execute('UPDATE harness_approvals SET revoked=1 '
                                 'WHERE id=? AND revoked=0', (approval_id,))
            if updated.rowcount != 1:
                raise ValueError('active approval not found')
            db.execute('INSERT INTO harness_approval_events(approval_id,event,actor,at) '
                       'VALUES (?,?,?,?)',
                       (approval_id, 'revoked', reviewer, _utc(self.clock()).isoformat()))

    def events(self, approval_id: str) -> tuple[dict, ...]:
        with self._connect() as db:
            return tuple(dict(row) for row in db.execute(
                'SELECT event,actor,at FROM harness_approval_events WHERE approval_id=? '
                'ORDER BY sequence', (approval_id,),
            ))
