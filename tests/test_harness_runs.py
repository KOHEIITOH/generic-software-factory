"""Use real Git/SQLite to verify prepared metadata and atomic approval consumption."""
import hashlib
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from sf_factory.factory import Factory
from sf_factory.harness_approval import HarnessApprovalRequest
from sf_factory.harness_composition import compose_harness
from sf_factory.harness_runs import HarnessRunService
from sf_factory.harness_validation import validate_harness
from sf_factory.local_project_registry import LocalProjectRegistry
from sf_factory.local_task_projects import LocalTaskProjects
from sf_factory.repository_contracts import Project, Repository, Visibility
from sf_factory.run_evidence import (
    CheckObservation,
    CheckRequirement,
    EvidenceSubject,
    RunEvidenceService,
)


def git(root, *args):
    return subprocess.run(['git', '-c', 'core.hooksPath=/dev/null', '-C', str(root), *args],
                          capture_output=True, text=True, check=True).stdout.strip()


def commit(root):
    git(root, 'add', '.')
    git(root, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
        'commit', '-qm', 'fixture')


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    # Fixture repositories must not inherit machine-specific filters or hooks.
    global_config = tmp_path / 'fixture-global-gitconfig'
    global_config.write_text('')
    monkeypatch.setenv('GIT_CONFIG_GLOBAL', str(global_config))
    monkeypatch.setenv('GIT_CONFIG_NOSYSTEM', '1')
    root = tmp_path / 'repo'
    root.mkdir()
    git(root, 'init', '-q')
    (root / 'AGENTS.md').write_text('rules')
    bundled = Path(__file__).resolve().parents[1] / 'fixtures/calculator'
    for name in ('calculator.py', 'test_calculator.py'):
        (root / name).write_bytes((bundled / name).read_bytes())
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


def test_inherited_global_filter_is_rejected(prepared, tmp_path, monkeypatch):
    _, factory, service, _, approval = prepared
    global_config = tmp_path / 'global-lfs-config'
    global_config.write_text('[filter "lfs"]\n  process = git-lfs filter-process\n')
    monkeypatch.setenv('GIT_CONFIG_GLOBAL', str(global_config))
    with pytest.raises(ValueError, match='configured Git filters'):
        prepare(prepared)
    assert not factory.list_runs()
    assert len(service.approvals.events(approval)) == 1


@pytest.fixture
def evidence_run(prepared):
    _, factory, _, request, _ = prepared
    run = prepare(prepared)
    service = RunEvidenceService(factory)
    subject = EvidenceSubject(request.revision, request.bundle_hash, 'd' * 64)
    checks = (CheckRequirement('unit', 'tests'), CheckRequirement('lint', 'lint'))
    service.register(run['id'], subject, checks, collector='trusted-checker')
    return service, run['id'], subject


def observe(values, check='unit', attempt=1, status='completed', exit_code=0, tests_run=2):
    service, run_id, subject = values
    service.record(run_id, subject, attempt=attempt, collector='trusted-checker',
                   observation=CheckObservation(check, status, exit_code, 'e' * 64,
                                                tests_run if check == 'unit' else None,
                                                run_id=run_id))


def test_checks_connect_to_prepared_run_but_do_not_authorize_delivery(evidence_run):
    service, run_id, subject = evidence_run
    assert service.assess(run_id, subject)['checks_passed'] is False
    observe(evidence_run)
    assert service.assess(run_id, subject)['checks_passed'] is False
    observe(evidence_run, check='lint')
    report = service.assess(run_id, subject)
    assert report['checks_passed'] is True
    assert report['review_status'] == 'missing'
    assert report['eligible_for_delivery'] is False
    assert RunEvidenceService(service.factory).assess(run_id, subject) == report
    assert service.factory.show_run(run_id)['status'] == 'prepared'


@pytest.mark.parametrize('status,code,count', [
    ('completed', 0, 0), ('completed', 0, None), ('failed', 1, 2),
    ('skipped', None, None), ('error', None, None),
])
def test_incomplete_or_failed_checks_never_pass(evidence_run, status, code, count):
    service, run_id, subject = evidence_run
    observe(evidence_run, status=status, exit_code=code, tests_run=count)
    observe(evidence_run, check='lint')
    assert not service.assess(run_id, subject)['checks_passed']


@pytest.mark.parametrize('field,value', [
    ('revision', 'f' * 40), ('bundle_hash', 'f' * 64), ('diff_sha256', 'f' * 64),
])
def test_wrong_subject_is_rejected_for_record_and_assessment(evidence_run, field, value):
    service, run_id, subject = evidence_run
    stale = replace(subject, **{field: value})
    with pytest.raises(PermissionError):
        service.record(run_id, stale, attempt=1, collector='trusted-checker',
                       observation=CheckObservation('unit', 'completed', 0, 'e' * 64, 2,
                                                    run_id=run_id))
    with pytest.raises(PermissionError):
        service.assess(run_id, stale)
    assert service.assess(run_id, subject)['attempt'] == 0


def test_new_attempt_cannot_reuse_old_success_or_accept_old_callbacks(evidence_run):
    service, run_id, subject = evidence_run
    observe(evidence_run)
    observe(evidence_run, check='lint')
    assert service.assess(run_id, subject)['checks_passed']
    observe(evidence_run, attempt=2)
    report = service.assess(run_id, subject)
    assert report['attempt'] == 2
    assert not report['checks_passed']
    with pytest.raises(ValueError):
        observe(evidence_run, check='lint', attempt=1)
    observe(evidence_run, check='lint', attempt=2)
    assert service.assess(run_id, subject)['checks_passed']
    with pytest.raises(ValueError):
        observe(evidence_run, attempt=4)


def test_check_records_and_plan_cannot_be_overwritten(evidence_run):
    service, run_id, subject = evidence_run
    observe(evidence_run, status='failed', exit_code=1)
    with pytest.raises(sqlite3.IntegrityError):
        observe(evidence_run)
    with pytest.raises(sqlite3.IntegrityError):
        service.register(run_id, subject, (CheckRequirement('unit', 'tests'),),
                         collector='trusted-checker')
    assert not service.assess(run_id, subject)['checks_passed']


def test_unplanned_check_and_wrong_collector_are_rejected(evidence_run):
    service, run_id, subject = evidence_run
    with pytest.raises(ValueError):
        service.record(run_id, subject, attempt=1, collector='trusted-checker',
                       observation=CheckObservation('unknown', 'completed', 0, 'e' * 64, 2,
                                                    run_id=run_id))
    with pytest.raises(PermissionError):
        service.record(run_id, subject, attempt=1, collector='agent-self-report',
                       observation=CheckObservation('unit', 'completed', 0, 'e' * 64, 2,
                                                    run_id=run_id))


def test_real_fixture_test_failure_is_preserved_as_failed_evidence(evidence_run, prepared):
    service, run_id, subject = evidence_run
    fixture = prepared[0]
    result = subprocess.run(
        [sys.executable, '-B', '-m', 'unittest', 'discover', '-s', str(fixture)],
        capture_output=True, timeout=10,
    )
    # This bundled fixture deliberately lacks an implementation.
    assert result.returncode == 1
    assert b'Ran 2 tests' in result.stderr
    fingerprint = hashlib.sha256(result.stdout + result.stderr).hexdigest()
    service.record(run_id, subject, attempt=1, collector='trusted-checker',
                   observation=CheckObservation(
                       'unit', 'failed', result.returncode, fingerprint, 2, run_id=run_id,
                   ))
    report = service.assess(run_id, subject)
    assert not report['checks_passed']
    assert next(c for c in report['checks'] if c['id'] == 'unit')['outcome'] == 'failed'



def test_terminal_run_does_not_accept_or_reuse_quality_evidence(evidence_run):
    service, run_id, subject = evidence_run
    observe(evidence_run)
    observe(evidence_run, check='lint')
    with sqlite3.connect(service.factory.db) as db:
        db.execute("UPDATE runs SET status='cancelled' WHERE id=?", (run_id,))
    with pytest.raises(ValueError, match='prepared state'):
        observe(evidence_run, attempt=2)
    with pytest.raises(ValueError, match='prepared state'):
        service.assess(run_id, subject)


def test_result_from_another_run_is_rejected(evidence_run):
    service, run_id, subject = evidence_run
    with pytest.raises(PermissionError):
        service.record(run_id, subject, attempt=1, collector='trusted-checker',
                       observation=CheckObservation('unit', 'completed', 0, 'e' * 64, 2,
                                                    run_id='f' * 32))
    assert service.assess(run_id, subject)['attempt'] == 0
