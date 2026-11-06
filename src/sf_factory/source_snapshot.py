"""Materialize bounded Git blobs from an approved Run without copying host state.

No archive extraction, Git hooks/filters, commands from the repository, or model
calls. Snapshot hashes detect later modification; host storage remains trusted.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import selectors
import shutil
import stat
import subprocess
import tempfile
import time
import uuid
from contextlib import closing
from pathlib import Path, PurePosixPath

from sf_factory.factory import Factory, _now
from sf_factory.harness_discovery import _sensitive

MAX_FILES = 1000
MAX_FILE_BYTES = 1048576
MAX_TOTAL_BYTES = 16777216


def _git(root: Path, arguments: list[str], budget: int, deadline: float) -> bytes:
    command = ['git', '--no-optional-locks', '-c', 'core.hooksPath=/dev/null',
               '-c', 'core.fsmonitor=false', '-C', str(root), *arguments]
    environment = dict(os.environ, GIT_NO_LAZY_FETCH='1', GIT_NO_REPLACE_OBJECTS='1',
                       GIT_ALLOW_PROTOCOL='', GIT_TERMINAL_PROMPT='0')
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, env=environment)
    output = bytearray()
    try:
        assert process.stdout is not None
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ValueError('snapshot time budget exceeded')
                if not selector.select(min(remaining, 0.1)):
                    continue
                chunk = os.read(process.stdout.fileno(), min(8192, budget - len(output) + 1))
                if not chunk:
                    break
                output.extend(chunk)
                if len(output) > budget:
                    raise ValueError('snapshot read budget exceeded')
        if process.wait(timeout=max(0.01, deadline - time.monotonic())) != 0:
            raise ValueError('could not read approved Git objects')
        return bytes(output)
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        if process.stdout:
            process.stdout.close()


def _path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (not path.parts or len(path.parts) > 16 or len(value) > 1024
            or path.is_absolute() or path.as_posix() != value
            or '..' in path.parts or '\\' in value or '\x00' in value):
        raise ValueError('unsupported snapshot path')
    if any(p.lower() in {'.git', '.sf-factory'} or _sensitive(p) for p in path.parts):
        raise ValueError('sensitive or control-state paths cannot enter a source snapshot')
    return path


def _fingerprint(manifest: dict) -> str:
    return hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=True).encode()).hexdigest()


class SourceSnapshotService:
    """Build one snapshot per prepared local Run, in trusted Factory storage."""

    def __init__(self, factory: Factory):
        self.factory = factory
        self.storage = factory.root / 'source-snapshots'
        if self.storage.is_symlink():
            raise ValueError('snapshot storage cannot be a symlink')
        self.storage.mkdir(mode=0o700, exist_ok=True)
        with closing(factory._connect()) as db, db:
            db.execute('''CREATE TABLE IF NOT EXISTS run_source_snapshots (
                run_id TEXT PRIMARY KEY REFERENCES runs(id), snapshot_id TEXT NOT NULL UNIQUE,
                fingerprint TEXT NOT NULL, manifest TEXT NOT NULL
            )''')

    def create(self, run_id: str, *, root: Path) -> dict:
        run = self.factory.show_run(run_id)
        if run['status'] != 'prepared' or 'harness_manifest' not in run:
            raise ValueError('prepared Harness Run required')
        approved = run['harness_manifest']
        request = approved['request']
        if not root.is_absolute() or root != root.resolve(strict=True):
            raise ValueError('canonical repository root required')
        with closing(self.factory._connect()) as db:
            repository = db.execute(
                'SELECT project_id,provider_id,external_id FROM repositories WHERE id=?',
                (request['repository_id'],),
            ).fetchone()
            if (repository is None or repository['project_id'] != request['project_id']
                    or repository['provider_id'] != 'local-git'
                    or repository['external_id'] != str(root)):
                raise ValueError('registered repository mismatch')
        deadline = time.monotonic() + 30
        location = _git(root, ['rev-parse', '--show-toplevel'], 4096, deadline).decode().strip()
        if Path(location) != root:
            raise ValueError('repository root mismatch')
        revision = request['revision']
        tree = _git(root, ['ls-tree', '-r', '-z', '--full-tree', revision], 1048576, deadline)
        entries = tree.rstrip(b'\0').split(b'\0') if tree else []
        if not entries or len(entries) > MAX_FILES:
            raise ValueError('snapshot file count exceeded or empty source')
        files: list[dict] = []
        seen: set[str] = set()
        total = 0
        snapshot_id = uuid.uuid4().hex
        final = self.storage / snapshot_id
        installed = False
        try:
            with tempfile.TemporaryDirectory(prefix='staging-', dir=self.storage) as temporary:
                staging = Path(temporary)
                payload = staging / 'payload'
                payload.mkdir(mode=0o700)
                for entry in entries:
                    header, encoded_path = entry.split(b'\t', 1)
                    mode, kind, object_id = header.decode('ascii').split(' ')
                    if (mode not in {'100644', '100755'} or kind != 'blob'
                            or not re.fullmatch(r'(?:[a-f0-9]{40}|[a-f0-9]{64})', object_id)):
                        raise ValueError('symlinks, submodules or unsupported Git objects')
                    relative = encoded_path.decode('utf-8')
                    path = _path(relative)
                    if relative in seen:
                        raise ValueError('duplicate Git path')
                    seen.add(relative)
                    body = _git(root, ['cat-file', 'blob', object_id],
                                min(MAX_FILE_BYTES, MAX_TOTAL_BYTES - total), deadline)
                    total += len(body)
                    destination = payload.joinpath(*path.parts)
                    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                    with destination.open('xb') as stream:
                        stream.write(body)
                    destination.chmod(0o600)
                    files.append({'path': relative, 'mode': mode, 'bytes': len(body),
                                  'sha256': hashlib.sha256(body).hexdigest()})
                hashes = {file['path']: file['sha256'] for file in files}
                composition = approved['composition']
                for source in composition['sources']:
                    if hashes.get(source['path']) != source['sha256']:
                        raise ValueError('approved Harness does not match committed source')
                profile = composition['profile']
                if profile:
                    for path, expected in profile['references']:
                        if hashes.get(path) != expected:
                            raise ValueError('approved reference absent or changed in source')
                manifest = {'schema_version': 1, 'run_id': run_id, 'revision': revision,
                            'bundle_hash': request['bundle_hash'],
                            'files': sorted(files, key=lambda file: file['path'])}
                fingerprint = _fingerprint(manifest)
                encoded_manifest = json.dumps(
                    manifest, sort_keys=True, ensure_ascii=True,
                ).encode('utf-8')
                if len(encoded_manifest) > 1048576:
                    raise ValueError('snapshot manifest budget exceeded')
                (staging / 'manifest.json').write_bytes(encoded_manifest)
                with closing(self.factory._connect()) as db, db:
                    db.execute('BEGIN IMMEDIATE')
                    current = db.execute('SELECT status FROM runs WHERE id=?', (run_id,)).fetchone()
                    if current is None or current['status'] != 'prepared':
                        raise ValueError('Run no longer prepared')
                    db.execute('INSERT INTO run_source_snapshots VALUES (?,?,?,?)',
                               (run_id, snapshot_id, fingerprint,
                                json.dumps(manifest, sort_keys=True)))
                    # Fresh UUID destination; an existing directory is never replaced.
                    staging.rename(final)
                    installed = True
                    db.execute('INSERT INTO audit(run_id,task_id,event,at) VALUES (?,?,?,?)',
                               (run_id, run['task_id'], 'run.source_snapshotted', _now()))
        except BaseException:
            if installed:
                shutil.rmtree(final)
            raise
        return {'snapshot_id': snapshot_id, 'fingerprint': fingerprint, 'manifest': manifest}

    def verify(self, run_id: str) -> dict:
        """Rehash stored payload before use; never execute or extract it on the host."""
        with closing(self.factory._connect()) as db:
            row = db.execute('SELECT * FROM run_source_snapshots WHERE run_id=?',
                             (run_id,)).fetchone()
        if row is None:
            raise ValueError('snapshot not found')
        if not re.fullmatch(r'[a-f0-9]{32}', row['snapshot_id']):
            raise ValueError('invalid snapshot identity')
        root = self.storage / row['snapshot_id']
        if root.is_symlink() or not root.is_dir():
            raise ValueError('invalid snapshot storage')
        manifest = json.loads(row['manifest'])
        if _fingerprint(manifest) != row['fingerprint']:
            raise ValueError('snapshot manifest changed')
        root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            stored_manifest = json.loads(_read_blob(root_fd, 'manifest.json', 1048576))
            if stored_manifest != manifest:
                raise ValueError('stored manifest changed')
            fd = os.open('payload', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
            try:
                if _file_paths(fd) != {file['path'] for file in manifest['files']}:
                    raise ValueError('snapshot paths changed')
                for file in manifest['files']:
                    _path(file['path'])
                    body = _read_blob(fd, file['path'], MAX_FILE_BYTES)
                    if (len(body) != file['bytes']
                            or hashlib.sha256(body).hexdigest() != file['sha256']):
                        raise ValueError('snapshot content changed')
            finally:
                os.close(fd)
        finally:
            os.close(root_fd)
        return {'snapshot_id': row['snapshot_id'], 'fingerprint': row['fingerprint'],
                'manifest': manifest}


def _read_blob(root_fd: int, relative: str, budget: int) -> bytes:
    directory = os.dup(root_fd)
    try:
        parts = _path(relative).parts
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        with os.fdopen(fd, 'rb') as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size > budget:
                raise ValueError('snapshot file type or size changed')
            body = stream.read(budget + 1)
            after = os.fstat(stream.fileno())
        current = os.stat(parts[-1], dir_fd=directory, follow_symlinks=False)
        identities = {(s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
                      for s in (before, after, current)}
        if len(identities) != 1 or len(body) > budget:
            raise ValueError('snapshot changed while reading')
        return body
    finally:
        os.close(directory)


def _file_paths(root_fd: int) -> set[str]:
    paths: set[str] = set()
    scanned = 0

    def walk(fd: int, parts: tuple[str, ...]) -> None:
        nonlocal scanned
        with os.scandir(fd) as entries:
            for entry in entries:
                scanned += 1
                if scanned > 20000:
                    raise ValueError('snapshot verification entry limit exceeded')
                relative = '/'.join((*parts, entry.name))
                _path(relative)
                metadata = os.stat(entry.name, dir_fd=fd, follow_symlinks=False)
                if stat.S_ISDIR(metadata.st_mode):
                    child = os.open(entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                    dir_fd=fd)
                    try:
                        walk(child, (*parts, entry.name))
                    finally:
                        os.close(child)
                elif stat.S_ISREG(metadata.st_mode):
                    paths.add(relative)
                else:
                    raise ValueError('snapshot symlink or special file detected')
    walk(root_fd, ())
    return paths
