"""DB-free issue storage on a local POSIX filesystem, with process locking.

A preview of issue persistence, not a complete backend for Factory workflows.
Files are private, bounded, versioned JSON; external imports use a stable key.
"""
from __future__ import annotations

import json
import math
import os
import re
import stat
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from sf_factory.state_store import (
    IssueSnapshot,
    StateConflict,
    StateCorrupt,
    StateNotFound,
    StatePermissionDenied,
    StateUnavailable,
)

try:
    import fcntl
except ImportError:  # File mode must refuse unsupported locking, never use a soft lock.
    fcntl = None  # type: ignore[assignment]

MAX_RECORD_BYTES = 1048576


class FileIssueStore:
    """A cache indexed by external identity; only source observations can add records."""
    def __init__(self, root: Path, *, lock_timeout: float = 5.0):
        if os.name != 'posix' or fcntl is None or not hasattr(os, 'O_NOFOLLOW'):
            raise StateUnavailable('Issue File storage requires POSIX locking')
        if (isinstance(lock_timeout, bool) or not math.isfinite(lock_timeout)
                or not 0 < lock_timeout <= 30):
            raise ValueError('bounded lock timeout required')
        self.root = root.expanduser().resolve()
        self.lock_timeout = lock_timeout
        if any(os.path.lexists(self.root / name) for name in ('tasks-v1', 'dashboard-v1')):
            raise StateConflict('Legacy Task data is unsupported; use a fresh state root')
        if (self.root / 'factory.sqlite3').exists():
            raise StateConflict('use a separate root; SQLite data exists')
        self.root.mkdir(mode=0o700, exist_ok=True)
        self.directory = self.root / 'issues-v2'
        self.directory.mkdir(mode=0o700, exist_ok=True)
        for path in (self.root.parent, self.root, self.directory):
            fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)

    @contextmanager
    def _locked(self) -> Iterator[int]:
        with lock_directory(self.directory, lock_timeout=self.lock_timeout) as directory:
            yield directory

    def _read(self, directory: int, issue_key: str) -> dict:
        if not isinstance(issue_key, str) or not re.fullmatch(r'[a-f0-9]{64}', issue_key):
            raise StateNotFound('issue not found')
        try:
            fd = os.open(issue_key + '.json', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=directory)
        except FileNotFoundError as exc:
            raise StateNotFound('issue not found') from exc
        with os.fdopen(fd, 'rb') as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_RECORD_BYTES:
                raise StateCorrupt('invalid Issue snapshot type or size')
            raw = stream.read(MAX_RECORD_BYTES + 1)
            after = os.fstat(stream.fileno())
        current = os.stat(issue_key + '.json', dir_fd=directory, follow_symlinks=False)
        if (len(raw) > MAX_RECORD_BYTES or len({(s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns,
                s.st_ctime_ns) for s in (before, after, current)}) != 1):
            raise StateCorrupt('Issue snapshot changed while reading')
        try:
            record = json.loads(raw, object_pairs_hook=_unique_object)
            if (set(record) != {'schema_version', 'version', 'issue', 'events'}
                    or type(record['schema_version']) is not int or record['schema_version'] != 2
                    or type(record['version']) is not int or record['version'] < 1):
                raise ValueError('invalid Issue cache schema')
            issue = IssueSnapshot(**record['issue'])
            if issue.key != issue_key or record['events'] != [
                {'event': 'issue.observed', 'at': issue.observed_at}]:
                raise ValueError('Issue reference mismatch')
            return record
        except (ValueError, TypeError, KeyError, RecursionError) as exc:
            raise StateCorrupt('invalid Issue snapshot') from exc

    def _write(self, directory: int, issue: IssueSnapshot, version: int) -> None:
        payload = json.dumps({'schema_version': 2, 'version': version,
            'issue': asdict(issue), 'events': [{'event': 'issue.observed',
                                              'at': issue.observed_at}]},
            sort_keys=True, ensure_ascii=True).encode()
        if len(payload) > MAX_RECORD_BYTES:
            raise ValueError('Issue snapshot exceeds size limit')
        import uuid
        temporary = '.' + uuid.uuid4().hex + '.tmp'
        fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                     0o600, dir_fd=directory)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, issue.key + '.json', src_dir_fd=directory, dst_dir_fd=directory)
            os.fsync(directory)
        finally:
            try:
                os.unlink(temporary, dir_fd=directory)
            except FileNotFoundError:
                pass

    def get_issue(self, issue_key: str) -> IssueSnapshot:
        with self._locked() as directory:
            return IssueSnapshot(**self._read(directory, issue_key)['issue'])

    def import_issue(self, *, provider: str, instance: str, external_id: str,
                     prompt: str, external_url: str | None = None) -> str:
        issue = IssueSnapshot(provider, instance, external_id, prompt, external_url,
                              datetime.now(UTC).isoformat())
        with self._locked() as directory:
            try:
                existing = self._read(directory, issue.key)
            except StateNotFound:
                existing = None
            if existing is not None:
                previous = IssueSnapshot(**existing['issue'])
                if (previous.provider, previous.instance, previous.external_id) != (
                        provider, instance, external_id):
                    raise StateConflict('Issue reference key collision')
                if previous.prompt == prompt and previous.external_url == external_url:
                    os.fsync(directory)
                    return issue.key
            self._write(directory, issue, existing['version'] + 1 if existing else 1)
        return issue.key


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate state record key')
        result[key] = value
    return result


@contextmanager
def lock_directory(path: Path, *, lock_timeout: float = 5.0) -> Iterator[int]:
    """Use the same bounded, no-follow POSIX lock for selection and state writes."""
    if fcntl is None:
        raise StateUnavailable('File locking is unavailable')
    directory = lock = None
    acquired = False
    try:
        directory = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        lock = os.open('.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK,
                       0o600, dir_fd=directory)
        if not stat.S_ISREG(os.fstat(lock).st_mode):
            raise StateCorrupt('invalid state lock file')
        deadline = time.monotonic() + lock_timeout
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
    except StatePermissionDenied:
        raise
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
