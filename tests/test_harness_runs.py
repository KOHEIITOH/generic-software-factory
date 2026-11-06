"""Use real Git/SQLite to verify prepared metadata and atomic approval consumption."""
import sqlite3
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from sf_factory.factory import Factory
from sf_factory.harness_approval import HarnessApprovalRequest
from sf_factory.harness_composition import compose_harness
from sf_factory.harness_runs import HarnessRunService
from sf_factory.harness_validation import validate_harness
from sf_factory.local_project_registry import LocalProjectRegistry
from sf_factory.local_task_projects import LocalTaskProjects
from sf_factory.repository_contracts import Project, Repository, Visibility


def git(root, *args):
    return subprocess.run(['git', '-c', 'core.hooksPath=/dev/null', '-C', str(root), *args],
                          capture_output=True, text=True, check=True).stdout.strip()


def commit(root):
    git(root, 'add', '.')
    git(root, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
        'commit', '-qm', 'fixture')


@pytest.fixture
def prepared(tmp_path):
    root = tmp_path / 'repo'
    root.mkdir()
    git(root, 'init', '-q')
    (root / 'AGENTS.md').write_text('rules')
    commit(root)
    factory = Factory(tmp_path / 'data')
    task = factory.create_task('Implement a sample')
    service = HarnessRunService(factory)
    registry = LocalProjectRegistry(factory.db)
    registry.add_project(Project('project', 'Demo', 'local'))
    registry.add_repository(Repository('repo', 'project', 'local-git', str(root), Visibility.LOCAL))
    LocalTaskProjects(factory.db).assign(task, 'project')
    composition = compose_harness(validate_harness(root), target='.', selected=('AGENTS.md',))
    request = HarnessApprovalRequest('project', 'repo', task, git(root, 'rev-parse', 'HEAD'),
                                     composition.bundle_hash)
    approval = service.approvals.record(request, reviewer='verified-human', approved=True,
                                        expires_at=datetime.now(UTC) + timedelta(hours=1))
    return root, factory, service, request, approval


def prepare(values, **overrides):
    root, _, service, request, approval = values
    return service.prepare(**({'root': root, 'request': request, 'approval_id': approval,
                               'target': '.', 'selected': ('AGENTS.md',),
                               'controller': 'trusted-factory'} | overrides))


def test_prepared_run_pins_metadata_and_never_starts_runtime(prepared, monkeypatch):
    root, factory, service, request, approval = prepared

    def forbidden(*args, **kwargs):
        raise AssertionError('must not start any runtime')

    monkeypatch.setattr(factory.runtime_registry, 'create', forbidden)
    run = prepare(prepared)
    assert run['status'] == 'prepared'
    assert run['runtime'] == 'unassigned'
    assert run['workspace'] == ''
    assert run['exit_code'] is None
    assert run['harness_manifest']['request']['bundle_hash'] == request.bundle_hash
    assert Factory(factory.root).show_run(run['id']) == run
    assert list(factory.workspaces.iterdir()) == []
    assert [e['event'] for e in service.approvals.events(approval)] == ['approved', 'consumed']
    (root / 'AGENTS.md').write_text('later changes')
    assert factory.show_run(run['id']) == run


@pytest.mark.parametrize('change', ['dirty', 'untracked', 'new_revision'])
def test_worktree_or_revision_changes_reject_without_consuming(prepared, change):
    root, factory, service, _, approval = prepared
    if change == 'dirty':
        (root / 'AGENTS.md').write_text('changed')
    else:
        (root / 'new.md').write_text('untracked')
        if change == 'new_revision':
            commit(root)
    with pytest.raises((ValueError, PermissionError)):
        prepare(prepared)
    assert not factory.list_runs()
    assert [e['event'] for e in service.approvals.events(approval)] == ['approved']


def test_wrong_bundle_and_wrong_project_are_rejected(prepared):
    _, factory, service, request, approval = prepared
    for invalid in [replace(request, bundle_hash='f' * 64), replace(request, project_id='other')]:
        with pytest.raises((ValueError, PermissionError)):
            prepare(prepared, request=invalid)
    assert not factory.list_runs()
    assert len(service.approvals.events(approval)) == 1


def test_database_failure_rolls_back_run_and_approval(prepared):
    _, factory, service, _, approval = prepared
    with sqlite3.connect(factory.db) as db:
        db.execute("CREATE TRIGGER reject_manifest BEFORE INSERT ON run_harness_manifests "
                   "BEGIN SELECT RAISE(ABORT, 'simulated failure'); END")
    with pytest.raises(sqlite3.IntegrityError):
        prepare(prepared)
    assert not factory.list_runs()
    assert len(service.approvals.events(approval)) == 1
    with sqlite3.connect(factory.db) as db:
        db.execute('DROP TRIGGER reject_manifest')
    assert prepare(prepared)['status'] == 'prepared'


def test_concurrent_prepare_creates_one_run(prepared):
    _, factory, _, _, _ = prepared

    def attempt(_):
        try:
            return prepare(prepared)['status']
        except PermissionError:
            return 'denied'

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt, range(2))) == ['denied', 'prepared']
    assert len(factory.list_runs()) == 1


def test_revoked_approval_never_creates_prepared_run(prepared):
    _, factory, service, _, approval = prepared
    service.approvals.revoke(approval, reviewer='verified-human')
    with pytest.raises(PermissionError):
        prepare(prepared)
    assert not factory.list_runs()


def test_repository_registration_cannot_redirect_to_different_path(prepared, tmp_path):
    _, factory, service, _, approval = prepared
    with pytest.raises(ValueError):
        prepare(prepared, root=tmp_path)
    assert not factory.list_runs()
    assert len(service.approvals.events(approval)) == 1


def test_git_filters_are_rejected_before_status_can_execute_them(prepared, tmp_path):
    root, factory, service, _, approval = prepared
    canary = tmp_path / 'filter-executed'
    git(root, 'config', 'filter.untrusted.clean', 'touch ' + str(canary))
    git(root, 'config', 'filter.untrusted.required', 'true')
    (root / '.git/info/attributes').write_text('*.md filter=untrusted\n')
    (root / 'AGENTS.md').write_text('rules')
    with pytest.raises(ValueError, match='configured Git filters'):
        prepare(prepared)
    assert not canary.exists()
    assert not factory.list_runs()
    assert len(service.approvals.events(approval)) == 1
