"""Real File backend: no SQLite connects, persistent Web/CLI-compatible state."""
import json
import sqlite3
import uuid
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context

import pytest
from fastapi.testclient import TestClient

from sf_factory.factory import Factory
from sf_factory.factory_selection import open_factory
from sf_factory.file_dashboard import FileDashboardFactory
from sf_factory.repository_contracts import Project, Repository, Visibility
from sf_factory.run_evidence import RunEvidenceService
from sf_factory.runtime import RuntimeResult
from sf_factory.state_store import StateConflict, StateCorrupt, StateUnavailable
from sf_factory.web_api import create_app


def no_sqlite(*args, **kwargs):
    raise AssertionError('File dashboard must not open SQLite')


def add_project(root, number):
    factory = open_factory(root)
    factory.project_registry().add_project(Project(str(number), str(number), 'local'))


def test_web_file_roundtrip_without_sqlite_and_without_extra_commands(tmp_path, monkeypatch):
    monkeypatch.setattr(sqlite3, 'connect', no_sqlite)
    headers = {'Origin': 'http://testserver'}
    with TestClient(create_app(data_dir=tmp_path)) as client:
        task = client.post('/api/tasks', json={'prompt': 'keep me'}, headers=headers)
        assert task.status_code == 201
        project = client.post('/api/projects', json={'name': 'Example'}, headers=headers)
        assert project.status_code == 201
        project_id = project.json()['id']
        url = f'/api/projects/{project_id}/repositories'
        repo = {'provider_id': 'local-git', 'external_id': '/example', 'visibility': 'local'}
        assert client.post(url, json=repo, headers=headers).status_code == 201
        assert client.post(url, json=repo, headers=headers).status_code == 409
        assert client.post('/api/tasks', json={'prompt': 'cross-origin'}).status_code == 403
        assert client.get('/api/runs').json() == {'runs': []}
        preflight = client.get(f'/api/tasks/{task.json()["task_id"]}/implementation-preflight')
        assert preflight.json()['execution_started'] is False
    with TestClient(create_app(data_dir=tmp_path)) as client:
        assert client.get('/api/tasks').json()['tasks'][0]['prompt'] == 'keep me'
        assert client.get('/api/projects').json()['projects'][0]['name'] == 'Example'
        assert client.get(url).json()['repositories'][0]['external_id'] == '/example'
    assert not list(tmp_path.rglob('*.sqlite3'))
    assert (tmp_path / 'dashboard-v1/state.json').stat().st_mode & 0o777 == 0o600


def test_existing_sqlite_retains_data_and_backend(tmp_path):
    existing = Factory(tmp_path)
    task_id = existing.create_task('old data')
    existing.project_registry().add_project(Project('p', 'Old project', 'local'))
    with TestClient(create_app(data_dir=tmp_path)) as client:
        assert client.get('/api/tasks').json()['tasks'][0]['id'] == task_id
        assert client.get('/api/projects').json()['projects'][0]['id'] == 'p'
    assert not (tmp_path / 'tasks-v1').exists()
    assert not (tmp_path / 'dashboard-v1').exists()
    with pytest.raises(StateConflict):
        open_factory(tmp_path, backend='file')


def test_file_run_results_and_audit_survive_reopen(tmp_path, monkeypatch):
    monkeypatch.setattr(sqlite3, 'connect', no_sqlite)
    factory = open_factory(tmp_path)
    task_id = factory.create_task('Read only')
    def execute(self, *, prompt, workspace, timeout_seconds):
        assert prompt == 'Read only'
        assert workspace.is_dir()
        return RuntimeResult('codex', 'timed_out', 'partial', None, error_kind='timeout')
    monkeypatch.setattr('sf_factory.codex_cli.CodexCliRuntime.execute', execute)
    run = factory.run_task(task_id, 'codex')
    reopened = open_factory(tmp_path)
    assert reopened.show_run(run['id'])['status'] == 'timed_out'
    assert reopened.show_run(run['id'])['output'] == 'partial'
    assert reopened.show_task(task_id)['runs'][0]['id'] == run['id']
    assert reopened.list_runs()[0]['id'] == run['id']
    state = json.loads((tmp_path / 'dashboard-v1/state.json').read_text())
    assert [event['event'] for event in state['events']] == ['run.started', 'run.timed_out']


def test_file_run_exception_persists_failure(tmp_path, monkeypatch):
    def execute(*args, **kwargs):
        raise RuntimeError('fixture failure')
    monkeypatch.setattr('sf_factory.codex_cli.CodexCliRuntime.execute', execute)
    factory = open_factory(tmp_path)
    result = factory.run_task(factory.create_task('Explain'), 'codex')
    assert result['status'] == 'failed'
    assert result['error_message'] == 'fixture failure'


def test_inflight_run_is_preserved_and_blocks_duplicate_execution(tmp_path, monkeypatch):
    factory = FileDashboardFactory(tmp_path)
    task_id = factory.create_task('Explain')
    run_id = uuid.uuid4().hex
    factory._start_run(run_id, task_id, 'codex', tmp_path / 'workspaces' / run_id)
    def execute(*args, **kwargs):
        pytest.fail('unfinished Run must not be executed again')
    monkeypatch.setattr('sf_factory.codex_cli.CodexCliRuntime.execute', execute)
    with pytest.raises(StateConflict):
        open_factory(tmp_path).run_task(task_id, 'codex')
    assert open_factory(tmp_path).show_run(run_id)['status'] == 'running'


def test_file_backend_has_no_hidden_fallback_for_sql_workflows(tmp_path, monkeypatch):
    monkeypatch.setattr(sqlite3, 'connect', no_sqlite)
    factory = open_factory(tmp_path)
    with pytest.raises(StateUnavailable, match='SQL workflow operations'):
        RunEvidenceService(factory)
    with pytest.raises(StateConflict):
        open_factory(tmp_path, backend='sqlite')
    with pytest.raises(ValueError):
        open_factory(tmp_path, backend='unsupported')


@pytest.mark.parametrize('payload', [b'{', b'{"schema_version":42}', None])
def test_corrupt_or_missing_dashboard_state_is_not_reset(tmp_path, payload):
    open_factory(tmp_path)
    path = tmp_path / 'dashboard-v1/state.json'
    if payload is None:
        path.unlink()
    else:
        path.write_bytes(payload)
    with pytest.raises(StateCorrupt):
        open_factory(tmp_path)
    with TestClient(create_app(data_dir=tmp_path)) as client:
        assert client.get('/api/projects').status_code == 503
    assert (path.read_bytes() if path.exists() else None) == payload


def test_concurrent_process_updates_do_not_lose_projects(tmp_path):
    open_factory(tmp_path)
    with ProcessPoolExecutor(max_workers=3, mp_context=get_context('spawn')) as pool:
        jobs = [pool.submit(add_project, tmp_path, i) for i in range(9)]
        for job in jobs:
            job.result(timeout=30)
    assert len(open_factory(tmp_path).project_registry().list_projects('local')) == 9


def test_failed_replace_preserves_snapshot_and_allows_retry(tmp_path, monkeypatch):
    factory = open_factory(tmp_path)
    before = (tmp_path / 'dashboard-v1/state.json').read_bytes()
    import sf_factory.file_document as module
    original = module.os.replace
    def fail(*args, **kwargs):
        raise OSError('fixture failure')
    monkeypatch.setattr(module.os, 'replace', fail)
    with pytest.raises(StateUnavailable):
        factory.project_registry().add_project(Project('p', 'Example', 'local'))
    assert (tmp_path / 'dashboard-v1/state.json').read_bytes() == before
    monkeypatch.setattr(module.os, 'replace', original)
    factory.project_registry().add_project(Project('p', 'Example', 'local'))
    assert len(factory.project_registry().list_projects('local')) == 1


def test_snapshot_symlink_is_refused(tmp_path):
    root = tmp_path / 'data'
    open_factory(root)
    outside = tmp_path / 'outside'
    outside.write_text('keep')
    path = root / 'dashboard-v1/state.json'
    path.unlink()
    path.symlink_to(outside)
    with pytest.raises(StateUnavailable):
        open_factory(root)
    assert outside.read_text() == 'keep'


def test_repository_constraint_rolls_back(tmp_path):
    registry = open_factory(tmp_path).project_registry()
    repo = Repository('r', 'p', 'local-git', '/example', Visibility.LOCAL)
    with pytest.raises(StateConflict):
        registry.add_repository(repo)
    registry.add_project(Project('p', 'P', 'local'))
    registry.add_repository(repo)
    with pytest.raises(StateConflict):
        registry.add_repository(Repository('r2', 'p', 'local-git', '/example', Visibility.LOCAL))
    assert len(registry.list_repositories('p')) == 1


def test_preview_tasks_are_visible_in_web(tmp_path, monkeypatch):
    from sf_factory.file_state import FileStateStore

    monkeypatch.setattr(sqlite3, 'connect', no_sqlite)
    task_id = FileStateStore(tmp_path).create_task('Created by preview CLI')
    with TestClient(create_app(data_dir=tmp_path)) as client:
        assert client.get('/api/tasks').json()['tasks'][0]['id'] == task_id


def test_shared_cli_web_data_directory(tmp_path, monkeypatch, capsys):
    import sys

    from sf_factory.cli import main

    monkeypatch.setattr(sqlite3, 'connect', no_sqlite)
    monkeypatch.setenv('SF_DATA_DIR', str(tmp_path))
    monkeypatch.setattr(sys, 'argv', ['sf', 'task', 'create', 'Shared Task'])
    assert main() == 0
    task_id = capsys.readouterr().out.strip()
    with TestClient(create_app()) as client:
        assert client.get('/api/tasks').json()['tasks'][0]['id'] == task_id


def test_bound_issue_metadata_survives_reopen_and_preflight(tmp_path, monkeypatch):
    monkeypatch.setattr(sqlite3, 'connect', no_sqlite)
    monkeypatch.setattr('sf_factory.github_repo_identity.verify_github_origin',
                        lambda path, repository: path)
    factory = open_factory(tmp_path)
    task_id = factory.import_external_task(
        provider='github', instance='example/repo', external_id='42', prompt='Implement',
    )
    headers = {'Origin': 'http://testserver'}
    with TestClient(create_app(data_dir=tmp_path)) as client:
        result = client.post(f'/api/tasks/{task_id}/repository', headers=headers, json={
            'repository': 'example/repo', 'local_path': str(tmp_path),
        })
        assert result.status_code == 200
    with TestClient(create_app(data_dir=tmp_path)) as client:
        row = client.get('/api/tasks').json()['tasks'][0]
        assert row['bound_repository'] == 'example/repo'
        result = client.get(f'/api/tasks/{task_id}/implementation-preflight').json()
        assert result['repository'] == 'example/repo'
        assert result['execution_started'] is False
        assert 'GitHub Issue source required' not in result['blockers']
        assert 'Verified local repository binding required' not in result['blockers']


def test_bad_binding_does_not_change_file_state(tmp_path, monkeypatch):
    monkeypatch.setattr('sf_factory.github_repo_identity.verify_github_origin',
                        lambda path, repository: path)
    factory = open_factory(tmp_path)
    task_id = factory.import_external_task(
        provider='github', instance='example/repo', external_id='42', prompt='Implement',
    )
    before = (tmp_path / 'dashboard-v1/state.json').read_bytes()
    with pytest.raises(ValueError, match='does not match'):
        factory.bind_task_repository(task_id, 'other/repo', tmp_path)
    assert (tmp_path / 'dashboard-v1/state.json').read_bytes() == before


def test_file_document_limit_does_not_replace_existing_state(tmp_path, monkeypatch):
    import sf_factory.file_document as module

    factory = open_factory(tmp_path)
    path = tmp_path / 'dashboard-v1/state.json'
    before = path.read_bytes()
    monkeypatch.setattr(module, 'MAX_DOCUMENT_BYTES', len(before) + 10)
    with pytest.raises(ValueError, match='limit'):
        factory.project_registry().add_project(Project('p', 'x' * 100, 'local'))
    assert path.read_bytes() == before


def crash_project_update(root):
    import os

    import sf_factory.file_document as module

    factory = open_factory(root)
    module.os.replace = lambda *args, **kwargs: os._exit(23)
    factory.project_registry().add_project(Project('uncommitted', 'Interrupted', 'local'))


def select_backend(root, backend):
    try:
        return type(open_factory(root, backend=backend)).__name__
    except StateConflict:
        return 'conflict'


def test_process_death_releases_lock_and_preserves_previous_document(tmp_path):
    factory = open_factory(tmp_path)
    factory.project_registry().add_project(Project('old', 'Keep', 'local'))
    before = (tmp_path / 'dashboard-v1/state.json').read_bytes()
    worker = get_context('spawn').Process(target=crash_project_update, args=(tmp_path,))
    worker.start()
    worker.join(timeout=15)
    if worker.is_alive():
        worker.kill()
        worker.join()
        pytest.fail('fixture process did not finish')
    assert worker.exitcode == 23
    assert (tmp_path / 'dashboard-v1/state.json').read_bytes() == before
    reopened = open_factory(tmp_path)
    assert [p.id for p in reopened.project_registry().list_projects('local')] == ['old']
    reopened.project_registry().add_project(Project('new', 'After crash', 'local'))


def test_simultaneous_backend_selection_does_not_mix_data(tmp_path):
    with ProcessPoolExecutor(max_workers=2, mp_context=get_context('spawn')) as pool:
        jobs = [pool.submit(select_backend, tmp_path, b) for b in ('file', 'sqlite')]
        results = [job.result(timeout=30) for job in jobs]
    assert results.count('conflict') == 1
    assert (tmp_path / 'factory.sqlite3').exists() != (tmp_path / 'tasks-v1').exists()
