"""Domain snapshot registration; payload publication precedes state registration."""
from __future__ import annotations

import json
from contextlib import closing
from typing import TYPE_CHECKING, Protocol

from sf_factory.state_store import StateConflict

if TYPE_CHECKING:
    from sf_factory.factory import Factory
    from sf_factory.file_dashboard import FileDashboardFactory


class SourceState(Protocol):
    def register(self, run_id: str, snapshot_id: str, fingerprint: str, manifest: dict) -> None:
        """Atomically register one immutable source record and its Run audit event."""
        ...

    def get(self, run_id: str) -> dict | None: ...


def check_snapshot_scope(run: dict, manifest: dict, *, require_prepared: bool = True) -> None:
    if (require_prepared and run['status'] != 'prepared') or 'harness_manifest' not in run:
        raise ValueError('Run no longer prepared')
    request = run['harness_manifest']['request']
    if (manifest['schema_version'] != 1 or manifest['run_id'] != run['id']
            or manifest['revision'] != request['revision']
            or manifest['bundle_hash'] != request['bundle_hash']):
        raise ValueError('snapshot scope differs from approved Run')


class SqliteSourceState:
    def __init__(self, factory: Factory):
        self.factory = factory
        with closing(factory._connect()) as db, db:
            db.execute('''CREATE TABLE IF NOT EXISTS run_source_snapshots (
                run_id TEXT PRIMARY KEY REFERENCES runs(id), snapshot_id TEXT NOT NULL UNIQUE,
                fingerprint TEXT NOT NULL, manifest TEXT NOT NULL
            )''')

    def register(self, run_id: str, snapshot_id: str, fingerprint: str, manifest: dict) -> None:
        with closing(self.factory._connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT r.*,m.manifest AS harness_manifest FROM runs r '
                             'JOIN run_harness_manifests m ON m.run_id=r.id WHERE r.id=?',
                             (run_id,)).fetchone()
            if row is None:
                raise ValueError('Run no longer prepared')
            run = dict(row)
            run['harness_manifest'] = json.loads(run['harness_manifest'])
            check_snapshot_scope(run, manifest)
            db.execute('INSERT INTO run_source_snapshots VALUES (?,?,?,?)',
                       (run_id, snapshot_id, fingerprint, json.dumps(manifest, sort_keys=True)))
            from sf_factory.factory import _now

            db.execute('INSERT INTO audit(run_id,task_id,event,at) VALUES (?,?,?,?)',
                       (run_id, run['task_id'], 'run.source_snapshotted', _now()))

    def get(self, run_id: str) -> dict | None:
        with closing(self.factory._connect()) as db:
            row = db.execute('SELECT * FROM run_source_snapshots WHERE run_id=?',
                             (run_id,)).fetchone()
        return dict(row) if row else None


class FileSourceState:
    def __init__(self, factory: FileDashboardFactory):
        self.factory = factory

    def register(self, run_id: str, snapshot_id: str, fingerprint: str, manifest: dict) -> None:
        with self.factory._document(edit=True) as state:
            run = state['runs'].get(run_id)
            if run is None:
                raise ValueError('Run no longer prepared')
            entry = state['harness']['manifests'].get(run_id)
            run = {**run, 'harness_manifest': json.loads(entry['manifest'])} if entry else run
            check_snapshot_scope(run, manifest)
            if (run_id in state['snapshots'] or any(r['snapshot_id'] == snapshot_id
                                                   for r in state['snapshots'].values())):
                raise StateConflict('source snapshot already registered')
            state['snapshots'][run_id] = {
                'run_id': run_id, 'snapshot_id': snapshot_id, 'fingerprint': fingerprint,
                'manifest': json.dumps(manifest, sort_keys=True),
            }
            from sf_factory.factory import _now

            state['events'].append({'run_id': run_id, 'task_id': run['task_id'],
                                    'event': 'run.source_snapshotted', 'at': _now()})

    def get(self, run_id: str) -> dict | None:
        with self.factory._document() as state:
            return state['snapshots'].get(run_id)


def validate_source_state(state: dict) -> None:
    import hashlib
    import re

    if not isinstance(state['snapshots'], dict):
        raise ValueError('invalid source snapshot collection')
    identities = set()
    for run_id, entry in state['snapshots'].items():
        if (set(entry) != {'run_id', 'snapshot_id', 'fingerprint', 'manifest'}
                or run_id != entry['run_id']
                or not re.fullmatch(r'[a-f0-9]{32}', entry['snapshot_id'])
                or entry['snapshot_id'] in identities):
            raise ValueError('invalid source snapshot record')
        identities.add(entry['snapshot_id'])
        manifest = json.loads(entry['manifest'])
        encoded = json.dumps(manifest, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
        if hashlib.sha256(encoded.encode()).hexdigest() != entry['fingerprint']:
            raise ValueError('source manifest fingerprint differs')
        run = state['runs'][run_id]
        harness = state['harness']['manifests'][run_id]
        check_snapshot_scope({**run, 'harness_manifest': json.loads(harness['manifest'])},
                             manifest, require_prepared=False)
