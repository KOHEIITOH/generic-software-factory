"""DB-free, durable, locally serialized delivery intents. No network operations."""
from __future__ import annotations

import os
import re
from dataclasses import asdict, replace
from pathlib import Path

from sf_factory.delivery_plan import DeliveryPlan
from sf_factory.delivery_state import STAGES, DeliveryRecord
from sf_factory.file_document import read_document, write_document
from sf_factory.file_state import lock_directory
from sf_factory.source_control import PreparedCommit, PullRequestReference
from sf_factory.state_store import StateConflict, StateCorrupt, StateNotFound


def _decode(data: dict) -> DeliveryRecord:
    fields = {'run_id', 'fingerprint', 'repository', 'branch', 'base_branch',
              'parent_revision', 'stage', 'commit', 'pull_request'}
    if not isinstance(data, dict) or set(data) != fields:
        raise ValueError('invalid delivery record')
    record = DeliveryRecord(**{**data,
        'commit': PreparedCommit(**data['commit']) if data['commit'] is not None else None,
        'pull_request': PullRequestReference(**data['pull_request'])
            if data['pull_request'] is not None else None})
    record.validate()
    return record


class FileDeliveryState:
    """Use only on durable local POSIX storage shared by the serial controller.

    Existing incomplete initialization, malformed state and uncertain fsync never
    reset intent. Distributed workers need a separate adapter with equivalent CAS.
    """
    def __init__(self, root: Path):
        root = root.expanduser().resolve()
        root.mkdir(mode=0o700, exist_ok=True)
        parent = os.open(root.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
        self.directory = root / 'delivery-v1'
        with lock_directory(root):
            try:
                self.directory.mkdir(mode=0o700)
                created = True
            except FileExistsError:
                created = False
            with lock_directory(self.directory) as directory:
                if created:
                    write_document(directory, {'schema_version': 1, 'version': 1, 'runs': {}})
                    parent = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                    try:
                        os.fsync(parent)
                    finally:
                        os.close(parent)
                self._read(directory)

    @staticmethod
    def _read(directory: int) -> dict:
        state = read_document(directory)
        try:
            if (set(state) != {'schema_version', 'version', 'runs'}
                    or type(state['schema_version']) is not int or state['schema_version'] != 1
                    or type(state['version']) is not int or state['version'] < 1
                    or not isinstance(state['runs'], dict)):
                raise ValueError('invalid delivery state')
            active = set()
            for key, value in state['runs'].items():
                record = _decode(value)
                if key != record.run_id:
                    raise ValueError('delivery identity mismatch')
                if record.stage != 'delivered':
                    if record.repository in active:
                        raise ValueError('parallel unresolved repository delivery')
                    active.add(record.repository)
            return state
        except (ValueError, TypeError, KeyError, RecursionError) as exc:
            raise StateCorrupt('invalid delivery journal; restore or reconcile it') from exc

    def claim(self, plan: DeliveryPlan) -> DeliveryRecord:
        record = DeliveryRecord(plan.run_id, plan.fingerprint, plan.repository, plan.branch,
                                plan.base_branch, plan.parent_revision)
        record.validate()
        with lock_directory(self.directory) as directory:
            state = self._read(directory)
            if (record.run_id in state['runs'] or any(
                row['repository'] == record.repository and row['stage'] != 'delivered'
                for row in state['runs'].values())):
                raise StateConflict('delivery already claimed; reconcile before another write')
            state['runs'][record.run_id] = asdict(record)
            state['version'] += 1
            write_document(directory, state)
        return record

    def active_for_repository(self, repository: str) -> DeliveryRecord | None:
        with lock_directory(self.directory) as directory:
            state = self._read(directory)
            return next((_decode(row) for row in state['runs'].values()
                         if row['repository'] == repository and row['stage'] != 'delivered'), None)

    def get(self, run_id: str) -> DeliveryRecord:
        with lock_directory(self.directory) as directory:
            state = self._read(directory)
            if run_id not in state['runs']:
                raise StateNotFound('delivery not found')
            return _decode(state['runs'][run_id])

    def advance(self, run_id: str, fingerprint: str, *, expected: str, stage: str,
                commit: PreparedCommit | None = None,
                pull_request: PullRequestReference | None = None) -> DeliveryRecord:
        if (not isinstance(fingerprint, str) or not re.fullmatch(r'[a-f0-9]{64}', fingerprint)
                or expected not in STAGES[:-1] or stage != STAGES[STAGES.index(expected) + 1]
                or (commit is not None) != (stage == 'commit_ready')
                or (pull_request is not None) != (stage == 'delivered')):
            raise ValueError('exact next delivery stage/receipt required')
        with lock_directory(self.directory) as directory:
            state = self._read(directory)
            if run_id not in state['runs']:
                raise StateNotFound('delivery not found')
            current = _decode(state['runs'][run_id])
            if current.fingerprint != fingerprint or current.stage != expected:
                raise StateConflict('delivery plan or stage changed')
            record = replace(current, stage=stage, commit=commit or current.commit,
                             pull_request=pull_request)
            record.validate()
            state['runs'][run_id] = asdict(record)
            state['version'] += 1
            write_document(directory, state)
        return record
