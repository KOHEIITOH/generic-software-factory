"""Exact-scope File approvals and prepared Runs commit as one real document."""
import json
import os
import sqlite3
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from multiprocessing import get_context

import pytest
from test_harness_runs import commit, git

from sf_factory.factory_selection import open_factory
from sf_factory.harness_approval import HarnessApprovalRequest
from sf_factory.harness_composition import compose_harness
from sf_factory.harness_runs import HarnessRunService
from sf_factory.harness_validation import validate_harness
from sf_factory.repository_contracts import Project, Repository, Visibility
from sf_factory.state_store import StateConflict, StateCorrupt, StateUnavailable


@pytest.fixture
def file_prepared(tmp_path, monkeypatch):
    def forbid(*args, **kwargs):
        pytest.fail('File Harness must not open SQLite')
    monkeypatch.setattr(sqlite3, 'connect', forbid)
    config = tmp_path / 'gitconfig'
    config.write_text('')
    monkeypatch.setenv('GIT_CONFIG_GLOBAL', str(config))
    monkeypatch.setenv('GIT_CONFIG_NOSYSTEM', '1')
    root = tmp_path / 'repo'
    root.mkdir()
    git(root, 'init', '-q')
    (root / 'AGENTS.md').write_text('fixture rules')
    commit(root)
    factory = open_factory(tmp_path / 'data')
    task = factory.create_task('Fixture task')
    registry = factory.project_registry()
    registry.add_project(Project('project', 'Example', 'local'))
    registry.add_repository(Repository('repo', 'project', 'local-git', str(root), Visibility.LOCAL))
    state = factory.harness_state()
    state.task_projects.assign(task, 'project')
    bundle = compose_harness(validate_harness(root), target='.', selected=('AGENTS.md',))
    request = HarnessApprovalRequest('project', 'repo', task, git(root, 'rev-parse', 'HEAD'),
                                     bundle.bundle_hash)
    service = HarnessRunService(factory)
    approval = service.approvals.record(request, reviewer='human', approved=True,
                                        expires_at=datetime.now(UTC) + timedelta(hours=1))
    return root, factory, service, request, approval


def prepare(values, **overrides):
    root, _, service, request, approval = values
    return service.prepare(**{
        **dict(root=root, request=request, approval_id=approval, target='.',
               selected=('AGENTS.md',), controller='controller'), **overrides,
    })


def test_file_prepare_persists_manifest_and_single_use_decision(file_prepared):
    _, factory, service, request, approval = file_prepared
    run = prepare(file_prepared)
    assert run['status'] == 'prepared'
    assert run['harness_manifest']['request'] == asdict(request)
    assert open_factory(factory.root).show_run(run['id']) == run
    assert [e['event'] for e in service.approvals.events(approval)] == ['approved', 'consumed']
    with pytest.raises(PermissionError):
        prepare(file_prepared)
    assert len(factory.list_runs()) == 1
    assert not list(factory.root.rglob('*.sqlite3'))


@pytest.mark.parametrize('change', [
    'revision', 'bundle', 'project', 'repository', 'dirty', 'revoked',
])
def test_bad_scope_or_stale_approval_does_not_create_run(file_prepared, change):
    root, factory, service, request, approval = file_prepared
    if change == 'revision':
        request = replace(request, revision='f' * 40)
    elif change == 'bundle':
        request = replace(request, bundle_hash='f' * 64)
    elif change == 'project':
        request = replace(request, project_id='other')
    elif change == 'repository':
        request = replace(request, repository_id='other')
    elif change == 'dirty':
        (root / 'AGENTS.md').write_text('changed')
    else:
        service.approvals.revoke(approval, reviewer='human')
    with pytest.raises((ValueError, PermissionError)):
        prepare(file_prepared, request=request)
    assert factory.list_runs() == []
    assert 'consumed' not in [e['event'] for e in service.approvals.events(approval)]


def test_failed_replace_leaves_approval_reusable_and_no_run(file_prepared, monkeypatch):
    _, factory, service, _, approval = file_prepared
    before = (factory.root / 'dashboard-v1/state.json').read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr('sf_factory.file_document.os.replace',
                      lambda *args, **kwargs: (_ for _ in ()).throw(OSError('fixture')))
        with pytest.raises(StateUnavailable):
            prepare(file_prepared)
    assert (factory.root / 'dashboard-v1/state.json').read_bytes() == before
    assert len(service.approvals.events(approval)) == 1
    assert prepare(file_prepared)['status'] == 'prepared'


def claim_in_process(root, data, request, approval):
    service = HarnessRunService(open_factory(data))
    try:
        return service.prepare(root=root, request=HarnessApprovalRequest(**request),
                               approval_id=approval, target='.', selected=('AGENTS.md',),
                               controller='controller')['status']
    except PermissionError:
        return 'denied'


def test_two_processes_can_create_only_one_prepared_run(file_prepared):
    root, factory, _, request, approval = file_prepared
    with ProcessPoolExecutor(max_workers=2, mp_context=get_context('spawn')) as pool:
        jobs = [pool.submit(claim_in_process, root, factory.root, asdict(request), approval)
                for _ in range(2)]
        assert sorted(job.result(timeout=30) for job in jobs) == ['denied', 'prepared']
    assert len(factory.list_runs()) == 1


def die_during_prepare(root, data, request, approval, after):
    import sf_factory.file_document as module

    service = HarnessRunService(open_factory(data))
    original = module.os.replace
    def replace_then_die(*args, **kwargs):
        if after:
            original(*args, **kwargs)
        os._exit(23)
    module.os.replace = replace_then_die
    service.prepare(root=root, request=HarnessApprovalRequest(**request), approval_id=approval,
                    target='.', selected=('AGENTS.md',), controller='controller')


@pytest.mark.parametrize('after', [False, True])
def test_process_death_never_splits_approval_consumption_and_run(file_prepared, after):
    root, factory, _, request, approval = file_prepared
    worker = get_context('spawn').Process(target=die_during_prepare,
        args=(root, factory.root, asdict(request), approval, after))
    worker.start()
    worker.join(timeout=20)
    if worker.is_alive():
        worker.kill()
        worker.join()
        pytest.fail('fixture worker did not finish')
    assert worker.exitcode == 23
    reopened = open_factory(factory.root)
    events = reopened.harness_state().approvals.events(approval)
    assert len(reopened.list_runs()) == int(after)
    assert ('consumed' in [e['event'] for e in events]) is after
    if after:
        with pytest.raises(PermissionError):
            prepare(file_prepared)
    else:
        assert prepare(file_prepared)['status'] == 'prepared'


def test_uncertain_directory_sync_keeps_decision_and_run_together(file_prepared, monkeypatch):
    import stat

    _, factory, service, _, approval = file_prepared
    original = os.fsync
    def fail_directory(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError('fixture directory sync failure')
        return original(fd)
    with monkeypatch.context() as patch:
        patch.setattr('sf_factory.file_document.os.fsync', fail_directory)
        with pytest.raises(StateUnavailable):
            prepare(file_prepared)
    assert len(open_factory(factory.root).list_runs()) == 1
    assert service.approvals.events(approval)[-1]['event'] == 'consumed'
    with pytest.raises(PermissionError):
        prepare(file_prepared)


def test_legacy_dashboard_upgrades_without_replacing_tasks_or_projects(tmp_path):
    factory = open_factory(tmp_path)
    task = factory.create_task('Keep')
    factory.project_registry().add_project(Project('p', 'Keep project', 'local'))
    path = tmp_path / 'dashboard-v1/state.json'
    record = json.loads(path.read_text())
    record.pop('harness')
    record.pop('snapshots')
    record['schema_version'] = 1
    path.write_text(json.dumps(record))
    reopened = open_factory(tmp_path)
    assert reopened.show_task(task)['task']['prompt'] == 'Keep'
    assert reopened.project_registry().list_projects('local')[0].id == 'p'
    assert json.loads(path.read_text())['schema_version'] == 3


@pytest.mark.parametrize('flag,value', [('approved', 1), ('consumed', True), ('revoked', True)])
def test_corrupt_decision_flags_or_audit_are_rejected(file_prepared, flag, value):
    _, factory, _, _, approval = file_prepared
    path = factory.root / 'dashboard-v1/state.json'
    record = json.loads(path.read_text())
    record['harness']['approvals'][approval][flag] = value
    path.write_text(json.dumps(record))
    before = path.read_bytes()
    with pytest.raises(StateCorrupt):
        open_factory(factory.root)
    assert path.read_bytes() == before


def test_task_project_assignment_is_once_only(file_prepared):
    _, factory, _, request, _ = file_prepared
    mapping = factory.harness_state().task_projects
    assert mapping.project_for_task(request.task_id) == 'project'
    assert mapping.tasks_for_project('project') == (request.task_id,)
    with pytest.raises(StateConflict):
        mapping.assign(request.task_id, 'project')
