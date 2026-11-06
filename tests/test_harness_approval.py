"""Exact-scope decisions remain single-use across processes and object lifetimes."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from sf_factory.harness_approval import (
    HarnessApprovalRequest,
    HarnessApprovalStore,
    harness_bundle_hash,
)
from sf_factory.harness_validation import validate_harness

NOW = datetime(2026, 11, 6, tzinfo=UTC)
REQUEST = HarnessApprovalRequest('project', 'repo', 'task', 'a' * 40, 'b' * 64)


def approve(store, request=REQUEST, **kwargs):
    return store.record(request, reviewer='verified-human', approved=True,
                        expires_at=NOW + timedelta(hours=1), **kwargs)


def test_decision_persists_and_is_consumed_once(tmp_path):
    path = tmp_path / 'approvals.db'
    store = HarnessApprovalStore(path, clock=lambda: NOW)
    approval = approve(store)
    restored = HarnessApprovalStore(path, clock=lambda: NOW)
    restored.consume(approval, REQUEST, controller='factory')
    with pytest.raises(PermissionError):
        store.consume(approval, REQUEST, controller='factory')
    assert [e['event'] for e in store.events(approval)] == ['approved', 'consumed']


@pytest.mark.parametrize('field,value', [
    ('project_id', 'other'), ('repository_id', 'other'), ('task_id', 'other'),
    ('revision', 'c' * 40), ('bundle_hash', 'd' * 64),
])
def test_any_scope_change_rejects_without_consuming(tmp_path, field, value):
    store = HarnessApprovalStore(tmp_path / 'db', clock=lambda: NOW)
    approval = approve(store)
    with pytest.raises(PermissionError):
        store.consume(approval, replace(REQUEST, **{field: value}), controller='factory')
    store.consume(approval, REQUEST, controller='factory')


def test_rejected_revoked_and_expired_decisions_do_not_authorize(tmp_path):
    now = [NOW]
    store = HarnessApprovalStore(tmp_path / 'db', clock=lambda: now[0])
    rejected = store.record(REQUEST, reviewer='human', approved=False,
                            expires_at=NOW + timedelta(hours=1))
    revoked = approve(store)
    store.revoke(revoked, reviewer='human')
    expiring = approve(store)
    now[0] += timedelta(hours=1)
    for receipt in [rejected, revoked, expiring, 'missing']:
        with pytest.raises(PermissionError):
            store.consume(receipt, REQUEST, controller='factory')
    assert [e['event'] for e in store.events(revoked)] == ['approved', 'revoked']


def test_clock_before_creation_is_rejected(tmp_path):
    now = [NOW]
    store = HarnessApprovalStore(tmp_path / 'db', clock=lambda: now[0])
    approval = approve(store)
    now[0] -= timedelta(minutes=1)
    with pytest.raises(PermissionError):
        store.consume(approval, REQUEST, controller='factory')


def test_concurrent_consumers_only_one_can_claim(tmp_path):
    store = HarnessApprovalStore(tmp_path / 'db', clock=lambda: NOW)
    approval = approve(store)

    def claim(_):
        try:
            store.consume(approval, REQUEST, controller='factory')
            return True
        except PermissionError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(claim, range(2))) == [False, True]


@pytest.mark.parametrize('expires', [NOW, NOW + timedelta(days=2), NOW.replace(tzinfo=None)])
def test_expiry_must_be_bounded_and_aware(tmp_path, expires):
    store = HarnessApprovalStore(tmp_path / 'db', clock=lambda: NOW)
    with pytest.raises(ValueError):
        store.record(REQUEST, reviewer='human', approved=True, expires_at=expires)


@pytest.mark.parametrize('change', [
    {'task_id': ''}, {'revision': 'main'}, {'bundle_hash': 'x'}, {'operation': 'merge'},
])
def test_invalid_scope_cannot_be_constructed(change):
    with pytest.raises(ValueError):
        replace(REQUEST, **change)


def test_bundle_fingerprint_tracks_files_and_rejects_unresolved_inventory(tmp_path):
    (tmp_path / '.git').mkdir()
    instructions = tmp_path / 'AGENTS.md'
    instructions.write_text('first')
    first = validate_harness(tmp_path)
    assert first.valid
    assert harness_bundle_hash(first) == harness_bundle_hash(validate_harness(tmp_path))
    instructions.write_text('changed')
    assert harness_bundle_hash(first) != harness_bundle_hash(validate_harness(tmp_path))
    (tmp_path / 'harness').mkdir()
    (tmp_path / 'harness/policy.md').write_text('another rule')
    with pytest.raises(ValueError):
        harness_bundle_hash(validate_harness(tmp_path))


def test_empty_inventory_cannot_be_approved_as_bundle(tmp_path):
    (tmp_path / '.git').mkdir()
    with pytest.raises(ValueError):
        harness_bundle_hash(validate_harness(tmp_path))


def test_bundle_tracks_referenced_content_even_if_profile_is_unchanged(tmp_path):
    (tmp_path / '.git').mkdir()
    (tmp_path / 'config').mkdir()
    (tmp_path / 'config/project.yaml').write_text('''
apiVersion: generic-software-factory/v1alpha1
kind: ProjectProfile
metadata: {name: demo}
spec:
  repositoryRoot: .
  language: python
  commands: {test: pytest}
  definitionOfDone: [Tests pass]
  conventions: [rules.md]
''')
    rules = tmp_path / 'rules.md'
    rules.write_text('initial')
    before = validate_harness(tmp_path)
    rules.write_text('changed')
    after = validate_harness(tmp_path)
    assert before.valid and after.valid
    assert before.profiles[0].sha256 == after.profiles[0].sha256
    assert harness_bundle_hash(before) != harness_bundle_hash(after)
