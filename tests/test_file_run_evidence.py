"""File evidence obeys the same subject, producer, attempt and review rules."""
import json
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, replace
from multiprocessing import get_context

import pytest
import test_file_harness as harness_fixtures

from sf_factory.factory_selection import open_factory
from sf_factory.run_evidence import (
    CheckObservation,
    CheckRequirement,
    EvidenceSubject,
    RunEvidenceService,
)
from sf_factory.state_store import StateConflict, StateCorrupt, StateUnavailable

file_prepared = harness_fixtures.file_prepared


@pytest.fixture
def evidence(file_prepared):
    _, factory, _, request, _ = file_prepared
    run = harness_fixtures.prepare(file_prepared)
    subject = EvidenceSubject(request.revision, request.bundle_hash, 'd' * 64)
    service = RunEvidenceService(factory)
    service.register(run['id'], subject, (CheckRequirement('unit', 'tests'),
                                         CheckRequirement('lint', 'lint')), collector='collector')
    return service, run['id'], subject


def observe(values, *, check='unit', attempt=1, status='completed', code=0, count=2):
    service, run_id, subject = values
    service.record(run_id, subject, attempt=attempt, collector='collector',
        observation=CheckObservation(check, status, code, 'e' * 64,
                                     count if check == 'unit' else None, run_id=run_id))


def review(values, **changes):
    service, run_id, subject = values
    response = {'schema_version': 1, 'run_id': run_id, **asdict(subject), 'status': 'completed',
                'complete': True, 'truncated': False, 'reviewed_paths': ['feature.py'],
                'findings': [], **changes}
    service.record_review(run_id, subject, attempt=1, reviewer='reviewer',
                          response=json.dumps(response))


def test_complete_evidence_persists_but_never_grants_delivery(evidence):
    service, run_id, subject = evidence
    observe(evidence)
    observe(evidence, check='lint')
    assert service.assess(run_id, subject)['checks_passed']
    assert not service.assess(run_id, subject)['evidence_complete']
    service.register_review(run_id, reviewer='reviewer', implementer='implementer',
                            changed_paths=('feature.py',))
    review(evidence)
    report = service.assess(run_id, subject)
    assert report['evidence_complete']
    assert report['eligible_for_delivery'] is False
    reopened = RunEvidenceService(open_factory(service.factory.root))
    assert reopened.assess(run_id, subject) == report
    assert not list(service.factory.root.rglob('*.sqlite3'))


@pytest.mark.parametrize('status,code,count', [
    ('completed', 0, 0), ('completed', 0, None), ('failed', 1, 2),
    ('error', None, None), ('skipped', None, None),
])
def test_zero_unknown_failed_or_unexecuted_tests_do_not_pass(evidence, status, code, count):
    service, run_id, subject = evidence
    observe(evidence, status=status, code=code, count=count)
    observe(evidence, check='lint')
    assert not service.assess(run_id, subject)['checks_passed']


@pytest.mark.parametrize('field,value', [('revision', 'f' * 40), ('bundle_hash', 'f' * 64),
                                         ('diff_sha256', 'f' * 64)])
def test_wrong_subject_never_records_or_assesses(evidence, field, value):
    service, run_id, subject = evidence
    other = replace(subject, **{field: value})
    with pytest.raises(PermissionError):
        observe((service, run_id, other))
    with pytest.raises(PermissionError):
        service.assess(run_id, other)
    assert service.assess(run_id, subject)['attempt'] == 0


def test_wrong_producer_or_run_cannot_record_check(evidence):
    service, run_id, subject = evidence
    for collector, source in [('other', run_id), ('collector', 'f' * 32)]:
        with pytest.raises(PermissionError):
            service.record(run_id, subject, attempt=1, collector=collector,
                observation=CheckObservation('unit', 'completed', 0, 'e' * 64, 2, run_id=source))
    assert service.assess(run_id, subject)['attempt'] == 0


def test_new_attempt_does_not_reuse_old_checks_or_review(evidence):
    service, run_id, subject = evidence
    observe(evidence)
    observe(evidence, check='lint')
    service.register_review(run_id, reviewer='reviewer', implementer='implementer',
                            changed_paths=('feature.py',))
    review(evidence)
    assert service.assess(run_id, subject)['evidence_complete']
    observe(evidence, attempt=2)
    report = service.assess(run_id, subject)
    assert report['attempt'] == 2
    assert not report['checks_passed']
    assert report['review_status'] == 'missing'
    with pytest.raises(ValueError):
        observe(evidence, attempt=1, check='lint')
    with pytest.raises(ValueError):
        observe(evidence, attempt=4)
    with pytest.raises(ValueError):
        review(evidence)


def test_plan_checks_and_review_are_immutable(evidence):
    service, run_id, subject = evidence
    observe(evidence, status='failed', code=1)
    with pytest.raises(StateConflict):
        observe(evidence)
    with pytest.raises(StateConflict):
        service.register(run_id, subject, (CheckRequirement('unit', 'tests'),),
                         collector='collector')
    service.register_review(run_id, reviewer='reviewer', implementer='implementer',
                            changed_paths=('feature.py',))
    review(evidence)
    with pytest.raises(StateConflict):
        review(evidence)


@pytest.mark.parametrize('changes', [
    {'status': 'failed'}, {'complete': False}, {'truncated': True}, {'reviewed_paths': []},
    {'findings': [{'severity': 'must-fix', 'path': 'feature.py', 'line': 1,
                   'summary': 'Missing check', 'evidence': 'fixture evidence'}]},
])
def test_failed_partial_or_must_fix_reviews_do_not_complete(evidence, changes):
    service, run_id, subject = evidence
    observe(evidence)
    observe(evidence, check='lint')
    service.register_review(run_id, reviewer='reviewer', implementer='implementer',
                            changed_paths=('feature.py',))
    review(evidence, **changes)
    assert not service.assess(run_id, subject)['evidence_complete']


def test_self_review_and_wrong_review_subject_are_refused(evidence):
    service, run_id, _ = evidence
    with pytest.raises(ValueError):
        service.register_review(run_id, reviewer='same', implementer='same',
                                changed_paths=('feature.py',))
    service.register_review(run_id, reviewer='reviewer', implementer='implementer',
                            changed_paths=('feature.py',))
    observe(evidence)
    with pytest.raises(ValueError):
        review(evidence, run_id='f' * 32)


def record_in_process(data, run_id, subject):
    service = RunEvidenceService(open_factory(data))
    try:
        observe((service, run_id, EvidenceSubject(**subject)))
        return 'recorded'
    except StateConflict:
        return 'conflict'


def test_concurrent_observers_never_overwrite_each_other(evidence):
    service, run_id, subject = evidence
    with ProcessPoolExecutor(max_workers=2, mp_context=get_context('spawn')) as pool:
        jobs = [pool.submit(record_in_process, service.factory.root, run_id, asdict(subject))
                for _ in range(2)]
        assert sorted(job.result(timeout=30) for job in jobs) == ['conflict', 'recorded']
    assert service.assess(run_id, subject)['attempt'] == 1


def test_failed_write_does_not_append_observation_or_audit(evidence, monkeypatch):
    service, run_id, subject = evidence
    path = service.factory.root / 'dashboard-v2/state.json'
    before = path.read_bytes()
    def fail(*args, **kwargs):
        raise OSError('fixture replace failure')
    with monkeypatch.context() as patch:
        patch.setattr('sf_factory.file_document.os.replace', fail)
        with pytest.raises(StateUnavailable):
            observe(evidence)
    assert path.read_bytes() == before
    assert service.assess(run_id, subject)['attempt'] == 0
    observe(evidence)


def test_corrupt_observation_is_not_silently_accepted(evidence):
    service, run_id, _ = evidence
    observe(evidence)
    path = service.factory.root / 'dashboard-v2/state.json'
    state = json.loads(path.read_text())
    state['evidence']['checks'][run_id][0]['attempt'] = True
    path.write_text(json.dumps(state))
    before = path.read_bytes()
    with pytest.raises(StateCorrupt):
        open_factory(service.factory.root)
    assert path.read_bytes() == before


def test_uncertain_write_keeps_observation_and_audit_together(evidence, monkeypatch):
    import sf_factory.file_dashboard as module

    service, run_id, subject = evidence
    original = module.write_document
    def publish_then_fail(*args, **kwargs):
        original(*args, **kwargs)
        raise OSError('fixture uncertain commit')
    with monkeypatch.context() as patch:
        patch.setattr(module, 'write_document', publish_then_fail)
        with pytest.raises(StateUnavailable):
            observe(evidence)
    assert service.assess(run_id, subject)['attempt'] == 1
    with pytest.raises(StateConflict):
        observe(evidence)
    data = json.loads((service.factory.root / 'dashboard-v2/state.json').read_text())
    events = [e for e in data['events'] if e['event'] == 'run.check_observed']
    assert len(events) == 1


def test_terminal_run_refuses_new_and_previously_successful_evidence(evidence):
    from sf_factory.factory import _now

    service, run_id, subject = evidence
    observe(evidence)
    observe(evidence, check='lint')
    with service.factory._document(edit=True) as state:
        run = state['runs'][run_id]
        run.update(status='failed', ended_at=_now(), workspace=str(service.factory.workspaces))
    with pytest.raises(ValueError, match='prepared state'):
        observe(evidence, attempt=2)
    with pytest.raises(ValueError, match='prepared state'):
        service.assess(run_id, subject)


def test_schema_three_upgrade_keeps_source_and_harness_state(file_prepared):
    from sf_factory.source_snapshot import SourceSnapshotService

    root, factory, _, _, _ = file_prepared
    run = harness_fixtures.prepare(file_prepared)
    SourceSnapshotService(factory).create(run['id'], root=root)
    path = factory.root / 'dashboard-v2/state.json'
    state = json.loads(path.read_text())
    state.pop('evidence')
    state['schema_version'] = 3
    path.write_text(json.dumps(state))
    before = path.read_bytes()
    with pytest.raises(StateCorrupt):
        open_factory(factory.root)
    assert path.read_bytes() == before
