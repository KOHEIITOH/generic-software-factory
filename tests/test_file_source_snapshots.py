"""File snapshot metadata and uncertain publication never lose referenced payload."""
import json
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context

import pytest
import test_file_harness as harness_fixtures

from sf_factory.factory_selection import open_factory
from sf_factory.source_snapshot import SourceSnapshotService
from sf_factory.state_store import StateConflict, StateCorrupt, StateUnavailable

file_prepared = harness_fixtures.file_prepared
prepare = harness_fixtures.prepare

@pytest.fixture
def snapshot(file_prepared):
    root, factory, _, _, _ = file_prepared
    run = prepare(file_prepared)
    return SourceSnapshotService(factory), run['id'], root


def test_file_snapshot_uses_approved_git_blobs_and_survives_reopen(snapshot):
    service, run_id, root = snapshot
    (root / 'AGENTS.md').write_text('unapproved host change')
    (root / 'host.env').write_text('host-only canary')
    record = service.create(run_id, root=root)
    assert service.verify(run_id) == record
    payload = service.storage / record['snapshot_id'] / 'payload'
    assert (payload / 'AGENTS.md').read_text() == 'fixture rules'
    assert not (payload / 'host.env').exists()
    assert not (payload / '.git').exists()
    reopened = SourceSnapshotService(open_factory(service.factory.root))
    assert reopened.verify(run_id) == record
    with pytest.raises(StateConflict):
        reopened.create(run_id, root=root)
    assert list(service.storage.iterdir()) == [service.storage / record['snapshot_id']]


@pytest.mark.parametrize('change', ['content', 'extra', 'symlink', 'manifest'])
def test_file_snapshot_tamper_is_refused(snapshot, change):
    service, run_id, root = snapshot
    record = service.create(run_id, root=root)
    path = service.storage / record['snapshot_id']
    if change == 'content':
        (path / 'payload/AGENTS.md').write_text('changed')
    elif change == 'extra':
        (path / 'payload/injected.py').write_text('extra')
    elif change == 'symlink':
        (path / 'payload/AGENTS.md').unlink()
        (path / 'payload/AGENTS.md').symlink_to('/etc/passwd')
    else:
        (path / 'manifest.json').write_text('{}')
    with pytest.raises((ValueError, OSError)):
        service.verify(run_id)


def test_metadata_write_failure_removes_only_unregistered_payload(snapshot, monkeypatch):
    service, run_id, root = snapshot
    def fail(*args, **kwargs):
        raise OSError('fixture metadata write failure')
    with monkeypatch.context() as patch:
        patch.setattr('sf_factory.file_document.os.replace', fail)
        with pytest.raises(StateUnavailable):
            service.create(run_id, root=root)
    assert list(service.storage.iterdir()) == []
    with pytest.raises(ValueError, match='snapshot not found'):
        service.verify(run_id)
    assert service.create(run_id, root=root) == service.verify(run_id)


def test_uncertain_metadata_write_retains_referenced_payload(snapshot, monkeypatch):
    import sf_factory.file_dashboard as module

    service, run_id, root = snapshot
    original = module.write_document
    def publish_then_fail(*args, **kwargs):
        original(*args, **kwargs)
        raise OSError('fixture post-publication error')
    with monkeypatch.context() as patch:
        patch.setattr(module, 'write_document', publish_then_fail)
        with pytest.raises(StateUnavailable):
            service.create(run_id, root=root)
    verified = service.verify(run_id)
    assert len(list(service.storage.iterdir())) == 1
    assert (service.storage / verified['snapshot_id'] / 'payload/AGENTS.md').is_file()
    with pytest.raises(StateConflict):
        service.create(run_id, root=root)
    assert service.verify(run_id) == verified


def test_unavailable_reconciliation_keeps_possibly_referenced_payload(snapshot, monkeypatch):
    service, run_id, root = snapshot
    original = service.state.register
    def register_then_fail(*args, **kwargs):
        original(*args, **kwargs)
        raise StateUnavailable('fixture unknown commit outcome')
    def cannot_read(*args, **kwargs):
        raise StateUnavailable('fixture read outage')
    with monkeypatch.context() as patch:
        patch.setattr(service.state, 'register', register_then_fail)
        patch.setattr(service.state, 'get', cannot_read)
        with pytest.raises(StateUnavailable):
            service.create(run_id, root=root)
    assert service.verify(run_id)['manifest']['run_id'] == run_id


def create_in_process(data, run_id, root):
    service = SourceSnapshotService(open_factory(data))
    try:
        return service.create(run_id, root=root)['snapshot_id']
    except StateConflict:
        return 'conflict'


def test_two_processes_register_one_snapshot_and_keep_winner_payload(snapshot):
    service, run_id, root = snapshot
    with ProcessPoolExecutor(max_workers=2, mp_context=get_context('spawn')) as pool:
        jobs = [pool.submit(create_in_process, service.factory.root, run_id, root)
                for _ in range(2)]
        results = [job.result(timeout=30) for job in jobs]
    assert results.count('conflict') == 1
    verified = service.verify(run_id)
    assert verified['snapshot_id'] in results
    assert len(list(service.storage.iterdir())) == 1


def test_manifest_subject_corruption_is_rejected_without_reset(snapshot):
    service, run_id, root = snapshot
    service.create(run_id, root=root)
    path = service.factory.root / 'dashboard-v1/state.json'
    state = json.loads(path.read_text())
    state['snapshots'][run_id]['fingerprint'] = 'f' * 64
    path.write_text(json.dumps(state))
    before = path.read_bytes()
    with pytest.raises(StateCorrupt):
        open_factory(service.factory.root)
    assert path.read_bytes() == before


def test_schema_two_upgrade_retains_consumed_approvals_and_prepared_runs(snapshot):
    service, run_id, _ = snapshot
    before_run = service.factory.show_run(run_id)
    path = service.factory.root / 'dashboard-v1/state.json'
    state = json.loads(path.read_text())
    before_harness = state['harness']
    state.pop('snapshots')
    state.pop('evidence')
    state['schema_version'] = 2
    path.write_text(json.dumps(state))
    reopened = open_factory(service.factory.root)
    assert reopened.show_run(run_id) == before_run
    upgraded = json.loads(path.read_text())
    assert upgraded['harness'] == before_harness
    assert upgraded['snapshots'] == {}


def test_payload_sync_failure_never_registers_snapshot(snapshot, monkeypatch):
    service, run_id, root = snapshot
    def fail(*args):
        raise OSError('fixture payload sync failure')
    with monkeypatch.context() as patch:
        patch.setattr('sf_factory.source_snapshot._sync_tree', fail)
        with pytest.raises(OSError):
            service.create(run_id, root=root)
    assert service.state.get(run_id) is None
    assert list(service.storage.iterdir()) == []


def test_snapshot_identity_collision_never_replaces_existing_directory(snapshot, monkeypatch):
    import uuid

    service, run_id, root = snapshot
    record = service.create(run_id, root=root)
    with monkeypatch.context() as patch:
        patch.setattr('sf_factory.source_snapshot.uuid.uuid4',
                      lambda: uuid.UUID(hex=record['snapshot_id']))
        with pytest.raises(FileExistsError):
            service.create(run_id, root=root)
    assert service.verify(run_id) == record


def test_load_returns_only_verified_immutable_payload_bytes(snapshot):
    service, run_id, root = snapshot
    descriptor = service.create(run_id, root=root)
    record, files = service.load(run_id)
    assert record == descriptor
    assert files == {'AGENTS.md': b'fixture rules'}
    files['AGENTS.md'] = b'caller changes its copy'
    assert service.load(run_id)[1] == {'AGENTS.md': b'fixture rules'}
