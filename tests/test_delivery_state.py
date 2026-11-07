"""Durable intent survives restarts, races and uncertain writes without replay."""
import json
import multiprocessing
from dataclasses import replace

import pytest
from test_delivery_plan import fixture

from sf_factory.delivery_plan import build_delivery_plan
from sf_factory.file_delivery_state import FileDeliveryState
from sf_factory.source_control import PreparedCommit, PullRequestReference
from sf_factory.state_store import StateConflict, StateUnavailable

COMMIT = PreparedCommit('e' * 40, 'f' * 40, 'b' * 40)
PR = PullRequestReference('7', 'https://fixture.invalid/pr/7')


def plan():
    return build_delivery_plan(**fixture())


def advance_to_pr_pending(state, item):
    for expected, stage, kwargs in [
        ('claimed', 'commit_ready', {'commit': COMMIT}),
        ('commit_ready', 'branch_pending', {}), ('branch_pending', 'branch_ready', {}),
        ('branch_ready', 'pr_pending', {})]:
        state.advance(item.run_id, item.fingerprint, expected=expected, stage=stage, **kwargs)


def test_restart_retains_exact_receipts_and_never_reclaims(tmp_path):
    item = plan()
    state = FileDeliveryState(tmp_path)
    state.claim(item)
    advance_to_pr_pending(state, item)
    reopened = FileDeliveryState(tmp_path)
    assert reopened.get(item.run_id).commit == COMMIT
    assert reopened.get(item.run_id).stage == 'pr_pending'
    with pytest.raises(StateConflict):
        reopened.claim(item)
    result = reopened.advance(item.run_id, item.fingerprint, expected='pr_pending',
                              stage='delivered', pull_request=PR)
    assert result.pull_request == PR
    assert FileDeliveryState(tmp_path).get(item.run_id) == result
    with pytest.raises(StateConflict):
        reopened.claim(item)


def test_repository_serialization_and_completed_release(tmp_path):
    item = plan()
    state = FileDeliveryState(tmp_path)
    state.claim(item)
    next_run = replace(item, run_id='9' * 32)
    with pytest.raises(StateConflict):
        state.claim(next_run)
    state.claim(replace(next_run, repository='other/repository'))
    advance_to_pr_pending(state, item)
    state.advance(item.run_id, item.fingerprint, expected='pr_pending',
                  stage='delivered', pull_request=PR)
    state.claim(replace(item, run_id='8' * 32))


@pytest.mark.parametrize('kwargs', [
    {'expected': 'claimed', 'stage': 'branch_ready'},
    {'expected': 'claimed', 'stage': 'commit_ready'},
    {'expected': 'claimed', 'stage': 'commit_ready',
     'commit': replace(COMMIT, parent_id='0' * 40)},
    {'expected': 'claimed', 'stage': 'commit_ready', 'commit': COMMIT, 'pull_request': PR},
    {'expected': 'delivered', 'stage': 'claimed'},
])
def test_illegal_transition_cannot_advance(tmp_path, kwargs):
    item = plan()
    state = FileDeliveryState(tmp_path)
    state.claim(item)
    with pytest.raises(ValueError):
        state.advance(item.run_id, item.fingerprint, **kwargs)
    assert state.get(item.run_id).stage == 'claimed'


def test_stale_plan_or_duplicate_worker_cannot_advance(tmp_path):
    item = plan()
    state = FileDeliveryState(tmp_path)
    state.claim(item)
    with pytest.raises(StateConflict):
        state.advance(item.run_id, '0' * 64, expected='claimed', stage='commit_ready',
                      commit=COMMIT)
    state.advance(item.run_id, item.fingerprint, expected='claimed', stage='commit_ready',
                  commit=COMMIT)
    with pytest.raises(StateConflict):
        state.advance(item.run_id, item.fingerprint, expected='claimed', stage='commit_ready',
                      commit=COMMIT)


@pytest.mark.parametrize('corruption', ['missing', 'malformed', 'future', 'symlink', 'wrong_key'])
def test_bad_journal_never_resets(tmp_path, corruption):
    state = FileDeliveryState(tmp_path)
    state.claim(plan())
    path = state.directory / 'state.json'
    if corruption == 'missing':
        path.unlink()
    elif corruption == 'malformed':
        path.write_text('{')
    elif corruption == 'symlink':
        path.rename(state.directory / 'saved.json')
        path.symlink_to('saved.json')
    else:
        document = json.loads(path.read_text())
        if corruption == 'future':
            document['schema_version'] = 999
        else:
            document['runs']['0' * 32] = document['runs'].pop(plan().run_id)
        path.write_text(json.dumps(document))
    with pytest.raises(StateUnavailable):
        FileDeliveryState(tmp_path)


def test_uncertain_directory_fsync_keeps_claim_and_blocks_replay(tmp_path, monkeypatch):
    import sf_factory.file_document as document
    state = FileDeliveryState(tmp_path)
    original = document.os.fsync
    calls = 0
    def fail_after_replace(fd):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError('directory fsync outcome unknown')
        return original(fd)
    with monkeypatch.context() as patch:
        patch.setattr(document.os, 'fsync', fail_after_replace)
        with pytest.raises(RuntimeError):
            state.claim(plan())
    reopened = FileDeliveryState(tmp_path)
    assert reopened.get(plan().run_id).stage == 'claimed'
    with pytest.raises(StateConflict):
        reopened.claim(plan())


def _claim(root, queue):
    try:
        FileDeliveryState(root).claim(plan())
        queue.put('claimed')
    except StateConflict:
        queue.put('conflict')


def test_two_processes_cannot_claim_the_same_delivery(tmp_path):
    FileDeliveryState(tmp_path)
    context = multiprocessing.get_context('fork')
    queue = context.Queue()
    processes = [context.Process(target=_claim, args=(tmp_path, queue)) for _ in range(2)]
    try:
        for process in processes:
            process.start()
        outcomes = [queue.get(timeout=10) for _ in processes]
        for process in processes:
            process.join(timeout=10)
            assert process.exitcode == 0
        assert sorted(outcomes) == ['claimed', 'conflict']
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
        queue.close()
