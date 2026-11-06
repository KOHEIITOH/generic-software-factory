"""DB-free task storage on a local POSIX filesystem, with process locking.

A preview of task persistence, not a complete backend for Factory workflows.
Files are private, bounded, versioned JSON; external imports use a stable key.
"""
from __future__ import annotations

import json
import math
import os
import re
import stat
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from sf_factory.state_store import (
    StateConflict,
    StateCorrupt,
    StateNotFound,
    StateUnavailable,
    TaskRecord,
    validate_external,
    validate_prompt,
)

try:
    import fcntl
except ImportError:  # File mode must refuse unsupported locking, never use a soft lock.
    fcntl = None  # type: ignore[assignment]

MAX_RECORD_BYTES = 1048576
_NAMESPACE = uuid.UUID('da3eb37a-379f-4a11-8e21-c66a9c8789dd')


class FileStateStore:
    def __init__(self, root: Path, *, lock_timeout: float = 5.0):
        if os.name != 'posix' or fcntl is None or not hasattr(os, 'O_NOFOLLOW'):
            raise StateUnavailable(
                'File state requires supported POSIX locking and filesystem calls'
            )
        if (isinstance(lock_timeout, bool) or not math.isfinite(lock_timeout)
                or not 0 < lock_timeout <= 30):
            raise ValueError('lock timeout must be between zero and thirty seconds')
        self.root = root.expanduser().resolve()
        self.lock_timeout = lock_timeout
        try:
            # Explicit existing parent keeps the durability boundary small and reviewable.
            self.root.mkdir(mode=0o700, exist_ok=True)
            if (self.root / 'factory.sqlite3').exists():
                raise StateConflict('use a separate root; existing SQLite data is not migrated')
            self.directory = self.root / 'tasks-v1'
            self.directory.mkdir(mode=0o700, exist_ok=True)
            for directory in (self.root.parent, self.root, self.directory):
                fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
        except OSError as exc:
            raise StateUnavailable(
                'File state root must support local directory durability'
            ) from exc

    @contextmanager
    def _locked(self) -> Iterator[int]:
        if fcntl is None:
            raise StateUnavailable('File locking is unavailable')
        directory = lock = None
        acquired = False
        try:
            directory = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            lock = os.open('.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK,
                           0o600, dir_fd=directory)
            if not stat.S_ISREG(os.fstat(lock).st_mode):
                raise StateCorrupt('invalid state lock file')
            deadline = time.monotonic() + self.lock_timeout
            while True:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise StateUnavailable('File state lock timed out') from None
                    time.sleep(0.01)
            yield directory
        except OSError as exc:
            raise StateUnavailable('File state operation failed') from exc
        finally:
            try:
                try:
                    if lock is not None:
                        try:
                            if acquired:
                                fcntl.flock(lock, fcntl.LOCK_UN)
                        finally:
                            os.close(lock)
                finally:
                    if directory is not None:
                        os.close(directory)
            except OSError as exc:
                raise StateUnavailable('File state lock cleanup failed') from exc

    def _read(self, directory: int, task_id: str) -> dict:
        if not isinstance(task_id, str) or not re.fullmatch(r'[a-f0-9]{32}', task_id):
            raise StateNotFound('task not found')
        try:
            fd = os.open(task_id + '.json', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=directory)
        except FileNotFoundError as exc:
            raise StateNotFound('task not found') from exc
        with os.fdopen(fd, 'rb') as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_RECORD_BYTES:
                raise StateCorrupt('state record type or size is invalid')
            raw = stream.read(MAX_RECORD_BYTES + 1)
            after = os.fstat(stream.fileno())
        current = os.stat(task_id + '.json', dir_fd=directory, follow_symlinks=False)
        identities = {(s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
                      for s in (metadata, after, current)}
        if len(raw) > MAX_RECORD_BYTES or len(identities) != 1:
            raise StateCorrupt('state record changed or exceeded the size limit')
        try:
            record = json.loads(raw, object_pairs_hook=_unique_object)
            if (not isinstance(record, dict) or set(record) != {
                'schema_version', 'version', 'task', 'source', 'events'
            } or type(record['schema_version']) is not int or record['schema_version'] != 1
                    or type(record['version']) is not int or record['version'] != 1):
                raise ValueError('unsupported record version')
            task = record['task']
            if (not isinstance(task, dict) or set(task) != {'id', 'prompt', 'created_at'}
                    or task['id'] != task_id or not isinstance(task['created_at'], str)):
                raise ValueError('invalid task record')
            validate_prompt(task['prompt'])
            if datetime.fromisoformat(task['created_at']).utcoffset() is None:
                raise ValueError('timezone required')
            source = record['source']
            if source is not None:
                if not isinstance(source, dict) or set(source) != {
                    'provider', 'instance', 'external_id', 'external_url'
                } or (source['external_url'] is not None
                      and not isinstance(source['external_url'], str)):
                    raise ValueError('invalid source')
                validate_external(source['provider'], source['instance'], source['external_id'],
                                  task['prompt'])
            expected_event = 'task.imported' if source is not None else 'task.created'
            if record['events'] != [{'event': expected_event, 'at': task['created_at']}]:
                raise ValueError('invalid task event')
            return record
        except (ValueError, TypeError, KeyError, RecursionError) as exc:
            raise StateCorrupt('invalid or unsupported state record') from exc

    def _write_new(self, directory: int, task: TaskRecord, source: dict | None) -> None:
        payload = json.dumps({
            'schema_version': 1, 'version': 1, 'task': asdict(task), 'source': source,
            'events': [{'event': 'task.imported' if source is not None else 'task.created',
                        'at': task.created_at}],
        }, sort_keys=True, ensure_ascii=True).encode()
        if len(payload) > MAX_RECORD_BYTES:
            raise ValueError('task exceeds File state record size limit')
        temporary = '.' + uuid.uuid4().hex + '.tmp'
        fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                     0o600, dir_fd=directory)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, task.id + '.json', src_dir_fd=directory, dst_dir_fd=directory)
            os.fsync(directory)
        finally:
            try:
                os.unlink(temporary, dir_fd=directory)
            except FileNotFoundError:
                pass

    def create_task(self, prompt: str) -> str:
        validate_prompt(prompt)
        with self._locked() as directory:
            for _ in range(3):
                task_id = uuid.uuid4().hex
                try:
                    self._read(directory, task_id)
                except StateNotFound:
                    task = TaskRecord(task_id, prompt, datetime.now(UTC).isoformat())
                    self._write_new(directory, task, None)
                    return task_id
            raise StateConflict('could not allocate a unique task identity')

    def get_task(self, task_id: str) -> TaskRecord:
        with self._locked() as directory:
            return TaskRecord(**self._read(directory, task_id)['task'])

    def import_external_task(
        self, *, provider: str, instance: str, external_id: str,
        prompt: str, external_url: str | None = None,
    ) -> str:
        validate_external(provider, instance, external_id, prompt)
        if external_url is not None and not isinstance(external_url, str):
            raise ValueError('external URL must be text')
        identity = {'provider': provider, 'instance': instance, 'external_id': external_id}
        task_id = uuid.uuid5(_NAMESPACE, json.dumps(identity, sort_keys=True)).hex
        source = {**identity, 'external_url': external_url}
        with self._locked() as directory:
            try:
                existing = self._read(directory, task_id)
            except StateNotFound:
                task = TaskRecord(task_id, prompt, datetime.now(UTC).isoformat())
                self._write_new(directory, task, source)
                return task_id
            if existing['source'] is None or any(existing['source'][k] != v
                                                  for k, v in identity.items()):
                raise StateConflict('external identity key collision')
            # Confirm directory durability even after an earlier uncertain fsync result.
            os.fsync(directory)
            return task_id


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate state record key')
        result[key] = value
    return result
