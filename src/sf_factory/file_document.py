"""Bounded durable JSON documents; callers must hold the File state process lock."""
from __future__ import annotations

import json
import os
import stat
import uuid

from sf_factory.file_state import _unique_object
from sf_factory.state_store import StateCorrupt

MAX_DOCUMENT_BYTES = 16 * 1024 * 1024


def read_document(directory: int) -> dict:
    try:
        fd = os.open('state.json', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=directory)
    except FileNotFoundError as exc:
        raise StateCorrupt('dashboard state is missing; restore from backup') from exc
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_DOCUMENT_BYTES:
            raise StateCorrupt('invalid dashboard document type or size')
        raw = stream.read(MAX_DOCUMENT_BYTES + 1)
        after = os.fstat(stream.fileno())
    current = os.stat('state.json', dir_fd=directory, follow_symlinks=False)
    identities = {(s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
                  for s in (before, after, current)}
    if len(raw) > MAX_DOCUMENT_BYTES or len(identities) != 1:
        raise StateCorrupt('dashboard document changed while reading')
    try:
        result = json.loads(raw, object_pairs_hook=_unique_object)
        if not isinstance(result, dict):
            raise ValueError('object required')
        return result
    except (ValueError, RecursionError) as exc:
        raise StateCorrupt('invalid dashboard JSON') from exc


def write_document(directory: int, record: dict) -> None:
    payload = json.dumps(record, sort_keys=True, ensure_ascii=True, allow_nan=False).encode()
    if len(payload) > MAX_DOCUMENT_BYTES:
        raise ValueError('dashboard state exceeds the 16 MiB local preview limit')
    temporary = '.' + uuid.uuid4().hex + '.tmp'
    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                 0o600, dir_fd=directory)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, 'state.json', src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
    finally:
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass
