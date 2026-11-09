"""Immutable provider-verified source baselines; no Git checkout, fetch, hooks or filters."""
from __future__ import annotations

import os
import re
import stat
import subprocess
import tempfile
import time
from pathlib import Path

from sf_factory.automation_state import fingerprint
from sf_factory.collaboration_contracts import CollaborationSourceControl, RevisionSource
from sf_factory.file_document import read_document, write_document
from sf_factory.file_state import lock_directory
from sf_factory.git_environment import git_environment
from sf_factory.harness_runs import _revision
from sf_factory.source_snapshot import _sync_directory
from sf_factory.state_store import StateConflict, StatePermissionDenied


class ManagedHarnessChanged(StateConflict):
    """The current remote source needs another explicit configuration review."""


def workspace_directory(root: Path) -> Path:
    parent = root.parent
    # Use Git's verified root, not the mere existence of a .git directory.
    try:
        parent = Path(_command(parent, ['rev-parse', '--show-toplevel'])).parent
    except subprocess.CalledProcessError:
        pass
    return parent / '.sf-repositories' / fingerprint(str(root))[:32]


def _command(root: Path, args: list[str], *, body: bytes | None = None) -> str:
    env = {**git_environment(), 'GIT_AUTHOR_NAME': 'Software Factory',
           'GIT_AUTHOR_EMAIL': 'factory@localhost', 'GIT_COMMITTER_NAME': 'Software Factory',
           'GIT_COMMITTER_EMAIL': 'factory@localhost', 'GIT_AUTHOR_DATE': '2000-01-01T00:00:00Z',
           'GIT_COMMITTER_DATE': '2000-01-01T00:00:00Z'}
    result = subprocess.run(['git', '-c', 'core.hooksPath=/dev/null', '-c', 'core.fsmonitor=false',
        '-c', 'commit.gpgSign=false', '-C', str(root), *args], input=body,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env, check=True, timeout=10)
    if len(result.stdout) > 65536:
        raise ValueError('Git response exceeds setup budget')
    return result.stdout.decode().strip()


def materialize(root: Path, source: RevisionSource, origin: str) -> str:
    source.validate()
    _command(root, ['init', '-q', '--template=', '--initial-branch=main'])
    index = bytearray()
    deadline = time.monotonic() + 120
    for file in source.files:
        if time.monotonic() >= deadline:
            raise ValueError('materialization deadline exceeded')
        path = root / file.path
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o755 if file.mode == '100755' else 0o644)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(file.content)
            stream.flush()
            os.fsync(stream.fileno())
        oid = _command(root, ['hash-object', '-w', '--stdin'], body=file.content)
        if not re.fullmatch('[a-f0-9]{40}', oid):
            raise ValueError('exact Git blob identity required')
        index.extend((file.mode + ' ' + oid + '\t' + file.path + '\0').encode())
    _command(root, ['update-index', '-z', '--index-info'], body=bytes(index))
    tree = _command(root, ['write-tree'])
    revision = _command(root, ['commit-tree', tree], body=b'Factory source baseline\n')
    _command(root, ['update-ref', 'refs/heads/main', revision])
    _command(root, ['config', 'remote.origin.url', origin])
    for directory, _, files in os.walk(root, topdown=False):
        for name in files:
            if time.monotonic() >= deadline:
                raise ValueError('materialization sync deadline exceeded')
            fd = os.open(Path(directory) / name, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                if not stat.S_ISREG(os.fstat(fd).st_mode):
                    raise ValueError('unexpected managed file type')
                os.fsync(fd)
            finally:
                os.close(fd)
        _sync_directory(Path(directory))
    if _revision(root) != revision:
        raise StateConflict('managed baseline verification failed')
    return revision


class ManagedRepositories:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.directory = self.root / 'managed-repositories-v1'
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.workspaces = workspace_directory(self.root)
        self.workspaces.parent.mkdir(mode=0o700, exist_ok=True)
        if any(p.is_symlink() for p in (self.workspaces.parent, *self.workspaces.parent.parents)):
            raise ValueError('canonical managed workspace parent required')
        if (self.workspaces.parent.stat().st_uid != os.getuid() or
                self.workspaces.parent.stat().st_mode & 0o022):
            raise ValueError('managed workspace parent must be operator-owned and protected')
        self.workspaces.mkdir(mode=0o700, exist_ok=True)
        if (self.workspaces.is_symlink() or self.workspaces.stat().st_uid != os.getuid()
                or self.workspaces.stat().st_mode & 0o022):
            raise ValueError('managed workspace must be operator-owned and protected')

    def _read(self, key: str, *, verify: bool = True) -> dict:
        if not re.fullmatch('[a-f0-9]{32}', key):
            raise ValueError('exact checkout identity required')
        with lock_directory(self.directory / key) as fd:
            value = read_document(fd)
        required = {'schema_version', 'repository', 'root', 'local_revision',
                    'remote_revision', 'source_fingerprint', 'fingerprint'}
        if (set(value) != required or type(value['schema_version']) is not int or
                not all(isinstance(value[k], str) for k in required - {'schema_version'})):
            raise StateConflict('invalid managed source document')
        immutable = {k: v for k, v in value.items() if k != 'fingerprint'}
        if (value['fingerprint'] != fingerprint(immutable) or value['schema_version'] != 1
                or key != fingerprint({'repository': value['repository'],
                                       'revision': value['remote_revision']})[:32]
                or value['root'] != str(self.workspaces / key)
                or not re.fullmatch('[a-f0-9]{40}', value['local_revision'])
                or not re.fullmatch('[a-f0-9]{40}', value['remote_revision'])):
            raise StateConflict('managed source metadata changed; do not reset')
        if verify:
            try:
                matches = _revision(Path(value['root'])) == value['local_revision']
            except (ValueError, OSError) as exc:
                raise StateConflict('managed baseline unavailable or modified') from exc
            if not matches:
                raise StateConflict('managed baseline was modified; do not overwrite')
        return value

    def find(self, root: Path) -> dict | None:
        # Immutable metadata is published atomically: unrelated acquisition needs no read lock.
        if root.parent != self.workspaces or not re.fullmatch('[a-f0-9]{32}', root.name):
            return None
        if not (self.directory / root.name).is_dir():
            return None
        return self._read(root.name)

    def acquire(self, repository: str, scm: CollaborationSourceControl, origin) -> dict:
        deadline, calls = time.monotonic() + 120, 0
        previous = getattr(scm, 'request_guard', None)
        def guard(method, path):
            nonlocal calls
            calls += 1
            if calls > 1100 or time.monotonic() >= deadline:
                raise StateConflict('repository acquisition budget exhausted')
            if previous is not None:
                previous(method, path)
        if hasattr(scm, 'request_guard'):
            setattr(scm, 'request_guard', guard)
        try:
            with lock_directory(self.directory, lock_timeout=0.1):
                info = scm.describe_repository(repository)
                if not info.capabilities.write or not info.capabilities.pull_request:
                    raise ValueError('Repository write and PR capability required')
                revision = scm.branch_revision(info.external_id, info.default_branch)
                key = fingerprint({'repository': info.external_id, 'revision': revision})[:32]
                prior = None
                if (self.directory / key).exists():
                    prior = self._read(key, verify=False)
                    if Path(prior['root']).exists():
                        return self._read(key)
                if len([p for p in self.directory.iterdir()
                        if re.fullmatch('[a-f0-9]{32}', p.name)]) >= 64 and prior is None:
                    raise StateConflict('managed repository history limit reached')
                source = scm.read_revision(info.external_id, revision)
                source.validate()
                if source.repository != info.external_id or source.revision != revision:
                    raise StateConflict('requested remote source differs')
                target = self.workspaces / key
                if target.exists() or target.is_symlink():
                    raise StateConflict('unpublished workspace exists; retain it for recovery')
                with tempfile.TemporaryDirectory(prefix='staging-', dir=self.workspaces) as stage:
                    local = materialize(Path(stage), source, origin(info.external_id))
                    value = {'schema_version': 1, 'repository': info.external_id,
                        'root': str(target), 'remote_revision': revision, 'local_revision': local,
                        'source_fingerprint': source.fingerprint}
                    value['fingerprint'] = fingerprint(value)
                    if prior is not None and prior != value:
                        raise StateConflict('recovered source differs from publication intent')
                    if prior is None:
                        with tempfile.TemporaryDirectory(prefix='intent-',
                                                         dir=self.directory) as temporary:
                            with lock_directory(Path(temporary)) as fd:
                                write_document(fd, value)
                            os.rename(temporary, self.directory / key)
                        _sync_directory(self.directory)
                    # Durable immutable publication intent precedes the workspace rename.
                    os.rename(stage, target)
                _sync_directory(self.workspaces)
                return value
        finally:
            if hasattr(scm, 'request_guard'):
                setattr(scm, 'request_guard', previous)


def managed_baseline(data_root: Path, root: Path) -> dict | None:
    if (not (data_root / 'managed-repositories-v1').is_dir()
            or not re.fullmatch('[a-f0-9]{32}', root.name)):
        return None
    return ManagedRepositories(data_root).find(root)


def execution_source(data_root: Path, root: Path, repository: str, scm) -> RevisionSource | None:
    value = managed_baseline(data_root, root)
    if value is None:
        return None
    info = scm.describe_repository(repository)
    if info.external_id != value['repository']:
        raise StateConflict('managed Repository scope differs')
    revision = scm.branch_revision(info.external_id, info.default_branch)
    source = scm.read_revision(info.external_id, revision)
    source.validate()
    if source.repository != info.external_id or source.revision != revision:
        raise StateConflict('managed execution source differs')
    from sf_factory.remote_harness import verify_remote_harness
    try:
        verify_remote_harness(root, source)
    except (ValueError, StatePermissionDenied) as exc:
        raise ManagedHarnessChanged('managed Harness review required') from exc
    return source
