"""File adapter for the existing local dashboard and read-only Runtime Runs.

No SQL compatibility layer. Harness approval/prepare uses atomic File state;
quality evidence shares the same durable state without exposing SQL.
"""
from __future__ import annotations

import copy
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path

from sf_factory.agent_registry import AgentRuntimeRegistry, default_runtime_registry
from sf_factory.evidence_state import EvidenceState
from sf_factory.factory import Factory, _now
from sf_factory.file_document import read_document, write_document
from sf_factory.file_state import FileStateStore
from sf_factory.harness_state import HarnessState
from sf_factory.repository_contracts import (
    Project,
    ProjectRegistry,
    Repository,
    RepositoryBindingAdapter,
    Visibility,
)
from sf_factory.source_state import SourceState
from sf_factory.state_store import (
    StateConflict,
    StateCorrupt,
    StateNotFound,
    StatePermissionDenied,
    StateUnavailable,
)


class FileDashboardFactory(Factory):
    def __init__(self, root: Path, *, runtime_registry: AgentRuntimeRegistry | None = None,
                 repository_binding: RepositoryBindingAdapter | None = None):
        self.runtime_registry = runtime_registry or default_runtime_registry()
        self._configure_repository_binding(repository_binding)
        self.files = FileStateStore(root)
        self.task_store = self.files
        self.root = self.files.root
        self.workspaces = self.root / 'workspaces'
        self.workspaces.mkdir(mode=0o700, exist_ok=True)
        # The directory is an initialization marker: a missing/corrupt document
        # inside an existing directory must never be treated as empty state.
        with self.files._locked():
            document_root = self.root / 'dashboard-v1'
            try:
                document_root.mkdir(mode=0o700)
                created = True
            except FileExistsError:
                created = False
            directory = os.open(document_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                if created:
                    write_document(directory, {
                        'schema_version': 4, 'version': 1,
                        'evidence': self._empty_evidence(),
                        'snapshots': {},
                        'harness': self._empty_harness(),
                        'bindings': {}, 'runs': {}, 'events': [],
                        'projects': {}, 'repositories': {},
                    })
                    parent = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                    try:
                        os.fsync(parent)
                    finally:
                        os.close(parent)
                record = read_document(directory)
                self._validate(record)
                if record['schema_version'] < 4:
                    if record['schema_version'] == 1:
                        record['harness'] = self._empty_harness()
                    if record['schema_version'] < 3:
                        record['snapshots'] = {}
                    record.update(schema_version=4, evidence=self._empty_evidence())
                    record['version'] += 1
                    self._validate(record)
                    write_document(directory, record)
            finally:
                os.close(directory)

    @property
    def db(self) -> Path:
        raise StateUnavailable(
            'This operation requires the SQLite workflow adapter; '
            'Direct SQL access is unavailable in File mode'
        )

    def _connect(self):
        # Never inherit a path that opens or creates a hidden SQLite database.
        raise StateUnavailable('SQL workflow operations are unavailable in File dashboard mode')

    @staticmethod
    def _validate(record: dict) -> None:
        try:
            if (set(record) != ({'schema_version', 'version', 'bindings', 'runs', 'events',
                                 'projects', 'repositories'} |
                                ({'harness'} if record.get('schema_version') in {2, 3, 4}
                                 else set()) |
                                ({'snapshots'} if record.get('schema_version') in {3, 4}
                                 else set()) |
                                ({'evidence'} if record.get('schema_version') == 4 else set()))
                    or type(record['schema_version']) is not int
                    or record['schema_version'] not in {1, 2, 3, 4}
                    or type(record['version']) is not int or record['version'] < 1):
                raise ValueError('unsupported dashboard schema or revision')
            for name in ('bindings', 'runs', 'projects', 'repositories'):
                if not isinstance(record[name], dict):
                    raise ValueError('invalid collection')
            for key, project in record['projects'].items():
                if key != Project(**project).id:
                    raise ValueError('project identity mismatch')
            identities = set()
            for key, value in record['repositories'].items():
                repo = Repository(**{**value, 'visibility': Visibility(value['visibility'])})
                identity = (repo.project_id, repo.provider_id, repo.external_id)
                if (key != repo.id or repo.project_id not in record['projects']
                        or identity in identities):
                    raise ValueError('invalid repository relationship')
                identities.add(identity)
            for key, binding in record['bindings'].items():
                if (not re.fullmatch(r'[a-f0-9]{32}', key)
                        or set(binding) != {'repository', 'local_path', 'linked_at'}
                        or not all(isinstance(v, str) and v for v in binding.values())):
                    raise ValueError('invalid repository binding')
            for key, run in record['runs'].items():
                if (key != run['id'] or not re.fullmatch(r'[a-f0-9]{32}', key)
                        or not re.fullmatch(r'[a-f0-9]{32}', run['task_id'])
                        or set(run) != {'id', 'task_id', 'runtime', 'status', 'workspace',
                                       'started_at', 'ended_at', 'output', 'error_kind',
                                       'error_message', 'exit_code'}
                        or run['status'] not in {
                            'running', 'prepared', 'succeeded', 'failed', 'timed_out'}
                        or not all(isinstance(run[k], str) and run[k]
                                   for k in ('runtime', 'started_at'))
                        or not isinstance(run['workspace'], str)
                        or (run['status'] != 'prepared' and not run['workspace'])):
                    raise ValueError('invalid Run')
                for field in ('ended_at', 'output', 'error_kind', 'error_message'):
                    if run[field] is not None and not isinstance(run[field], str):
                        raise ValueError('invalid Run result')
                if run['exit_code'] is not None and type(run['exit_code']) is not int:
                    raise ValueError('invalid Run exit code')
                if (run['status'] in {'running', 'prepared'}) != (run['ended_at'] is None):
                    raise ValueError('invalid Run lifecycle')
            if not isinstance(record['events'], list):
                raise ValueError('invalid audit events')
            for event in record['events']:
                if (not isinstance(event, dict)
                        or set(event) != {'task_id', 'run_id', 'event', 'at'}
                        or not all(isinstance(event[k], str) and event[k]
                                   for k in ('task_id', 'event', 'at'))
                        or (event['run_id'] is not None
                            and event['run_id'] not in record['runs'])):
                    raise ValueError('invalid audit event')
            if record['schema_version'] >= 2:
                from sf_factory.file_harness_state import validate_harness_state

                validate_harness_state(record)
            if record['schema_version'] >= 3:
                from sf_factory.source_state import validate_source_state

                validate_source_state(record)
            if record['schema_version'] == 4:
                from sf_factory.file_evidence_state import validate_evidence_state

                validate_evidence_state(record)
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError,
                StatePermissionDenied) as exc:
            raise StateCorrupt('invalid or unsupported dashboard state') from exc

    @contextmanager
    def _document(self, *, edit: bool = False) -> Iterator[dict]:
        with self.files._locked():
            directory = os.open(self.root / 'dashboard-v1',
                                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                record = read_document(directory)
                self._validate(record)
                yield record
                if edit:
                    record['version'] += 1
                    self._validate(record)
                    write_document(directory, record)
            finally:
                os.close(directory)

    @staticmethod
    def _limit(limit: int) -> None:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('limit must be between 1 and 100')

    def list_tasks(self, limit: int = 50, *, external_only: bool = False) -> list[dict]:
        self._limit(limit)
        with self._document() as state:
            rows = []
            for path in self.files.directory.iterdir():
                if re.fullmatch(r'[a-f0-9]{32}\.json', path.name):
                    # The enclosing lock protects task and dashboard metadata together.
                    directory = os.open(self.files.directory,
                                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                    try:
                        record = self.files._read(directory, path.stem)
                    finally:
                        os.close(directory)
                    if external_only and record['source'] is None:
                        continue
                    source = record['source'] or {}
                    binding = state['bindings'].get(path.stem, {})
                    rows.append({**record['task'], **{k: source.get(k) for k in (
                        'provider', 'instance', 'external_id', 'external_url')},
                        'bound_repository': binding.get('repository'),
                        'bound_local_path': binding.get('local_path')})
        return sorted(rows, key=lambda row: (row['created_at'], row['id']), reverse=True)[:limit]

    def _issue_run_history(self, task_ids: tuple[str, ...]) -> dict:
        if not task_ids:
            return {}
        history: dict = {}
        with self._document() as state:
            for run in sorted(state['runs'].values(),
                              key=lambda item: (item['started_at'], item['id']), reverse=True):
                if run['task_id'] not in task_ids:
                    continue
                group = history.setdefault(run['task_id'], {'runs': [], 'total': 0})
                group['total'] += 1
                if len(group['runs']) < 10:
                    group['runs'].append({k: run[k] for k in (
                        'id', 'task_id', 'runtime', 'status', 'started_at', 'ended_at')})
        return history

    def show_task(self, task_id: str) -> dict:
        task = self.task_store.get_task(task_id)
        with self._document() as state:
            runs = [{k: run[k] for k in ('id', 'runtime', 'status', 'started_at')}
                    for run in state['runs'].values() if run['task_id'] == task_id]
        return {'task': asdict(task), 'runs': sorted(runs, key=lambda run: run['started_at'])}

    def list_runs(self, limit: int = 50) -> list[dict]:
        self._limit(limit)
        with self._document() as state:
            runs = [{k: run[k] for k in ('id', 'task_id', 'runtime', 'status',
                                        'started_at', 'ended_at')}
                    for run in state['runs'].values()]
        return sorted(runs, key=lambda run: (run['started_at'], run['id']), reverse=True)[:limit]

    def show_run(self, run_id: str) -> dict:
        with self._document() as state:
            if run_id not in state['runs']:
                raise StateNotFound('run not found')
            run = copy.deepcopy(state['runs'][run_id])
            entry = state.get('harness', {}).get('manifests', {}).get(run_id)
            if entry is not None:
                import json

                run['harness_manifest'] = json.loads(entry['manifest'])
            return run

    def task_repository(self, task_id: str) -> dict:
        with self.files._locked() as directory:
            source = self.files._read(directory, task_id)['source'] or {}
        with self._document() as state:
            binding = state['bindings'].get(task_id, {})
            return {'id': task_id, 'provider': source.get('provider'),
                    'instance': source.get('instance'), 'repository': binding.get('repository'),
                    'local_path': binding.get('local_path')}

    def bind_task_repository(self, task_id: str, repository: str, local_path: Path) -> dict:
        root = self._verified_binding(task_id, repository, local_path)
        with self._document(edit=True) as state:
            state['bindings'][task_id] = {
                'repository': repository, 'local_path': str(root), 'linked_at': _now(),
            }
            state['events'].append({'task_id': task_id, 'run_id': None,
                                    'event': 'task.repository_bound', 'at': _now()})
        return {'task_id': task_id, 'repository': repository, 'local_path': str(root)}

    def _start_run(self, run_id: str, task_id: str, runtime: str, workspace: Path) -> None:
        with self._document(edit=True) as state:
            if any(run['status'] == 'running' for run in state['runs'].values()):
                raise StateConflict('File mode allows one active Run; inspect unfinished Runs')
            if run_id in state['runs']:
                raise StateConflict('Run already exists')
            at = _now()
            state['runs'][run_id] = {
                'id': run_id, 'task_id': task_id, 'runtime': runtime, 'status': 'running',
                'workspace': str(workspace), 'started_at': at, 'ended_at': None, 'output': None,
                'error_kind': None, 'error_message': None, 'exit_code': None,
            }
            state['events'].append({'task_id': task_id, 'run_id': run_id,
                                    'event': 'run.started', 'at': at})

    def _finish_run(self, run_id, task_id, status, output, error_kind, error_message, exit_code):
        with self._document(edit=True) as state:
            run = state['runs'].get(run_id)
            if run is None or run['task_id'] != task_id or run['status'] != 'running':
                raise StateConflict('Run is not active')
            at = _now()
            run.update(status=status, output=output, error_kind=error_kind,
                       error_message=error_message, exit_code=exit_code, ended_at=at)
            state['events'].append({'task_id': task_id, 'run_id': run_id,
                                    'event': 'run.' + status, 'at': at})

    @staticmethod
    def _empty_harness() -> dict:
        from sf_factory.file_harness_state import empty_harness

        return empty_harness()

    @staticmethod
    def _empty_evidence() -> dict:
        from sf_factory.file_evidence_state import empty_evidence

        return empty_evidence()

    def evidence_state(self) -> EvidenceState:
        from sf_factory.file_evidence_state import FileEvidenceState

        return FileEvidenceState(self)

    def source_state(self) -> SourceState:
        from sf_factory.source_state import FileSourceState

        return FileSourceState(self)

    def harness_state(self) -> HarnessState:
        from sf_factory.file_harness_state import FileHarnessState

        return FileHarnessState(self)

    def project_registry(self) -> ProjectRegistry:
        return FileProjectRegistry(self)


class FileProjectRegistry:
    def __init__(self, factory: FileDashboardFactory):
        self.factory = factory

    def add_project(self, project: Project) -> None:
        with self.factory._document(edit=True) as state:
            if project.id in state['projects']:
                raise StateConflict('Project already registered')
            state['projects'][project.id] = asdict(project)

    def add_repository(self, repository: Repository) -> None:
        with self.factory._document(edit=True) as state:
            if repository.project_id not in state['projects']:
                raise StateConflict('Project not found')
            identity = (repository.project_id, repository.provider_id, repository.external_id)
            if (repository.id in state['repositories'] or any(
                (r['project_id'], r['provider_id'], r['external_id']) == identity
                for r in state['repositories'].values()
            )):
                raise StateConflict('Repository already registered')
            state['repositories'][repository.id] = asdict(repository)

    def list_projects(self, owner_id: str) -> tuple[Project, ...]:
        with self.factory._document() as state:
            return tuple(Project(**p) for _, p in sorted(state['projects'].items())
                         if p['owner_id'] == owner_id)

    def list_repositories(self, project_id: str) -> tuple[Repository, ...]:
        with self.factory._document() as state:
            return tuple(Repository(**{**r, 'visibility': Visibility(r['visibility'])})
                         for _, r in sorted(state['repositories'].items())
                         if r['project_id'] == project_id)
