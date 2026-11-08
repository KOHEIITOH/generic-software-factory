"""SIGKILL, interrupted atomic publication and broken transport preserve at-most-once intent."""
import json
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from test_issue_development import flow as flow
from test_web_jobs import job_flow as job_flow

from sf_factory.automation_state import AutomationSession
from sf_factory.budgeted_model import BudgetedModel
from sf_factory.file_document import read_document, write_document
from sf_factory.file_state import lock_directory
from sf_factory.state_store import StateConflict
from sf_factory.web_jobs import WebJobs

HELPER = Path(__file__).with_name('crash_recovery_fixture.py')


def child(root, mode, recover=False):
    code = ('import runpy,sys; folder=sys.argv.pop(1); sys.path.insert(0,folder); '
            'runpy.run_path(folder+"/crash_recovery_fixture.py",run_name="__main__")')
    return subprocess.Popen([sys.executable, '-I', '-c', code, str(HELPER.parent), str(root), mode,
        'recover' if recover else 'crash'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def kill_at_checkpoint(root, mode):
    process = child(root, mode)
    try:
        deadline = time.monotonic() + 10
        while not (root / 'ready').exists() and time.monotonic() < deadline:
            if process.poll() is not None:
                pytest.fail('fault injection child exited before checkpoint')
            time.sleep(0.02)
        assert (root / 'ready').exists(), 'fault injection checkpoint deadline'
        process.kill()
        assert process.wait(timeout=5) < 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_killed_model_worker_releases_lease_but_never_replays_inference_or_resets_budget(job_flow):
    root, auth, payload, calls = job_flow
    store = WebJobs(root)
    command = {k: v for k, v in payload.items() if k != 'confirm_run'}
    store.enqueue(**command)
    kill_at_checkpoint(root, 'model')
    assert not store.live('a' * 32)
    with lock_directory(store.directory) as fd:
        state = read_document(fd)
        state['jobs']['a' * 32]['updated_at'] = '2000-01-01T00:00:00+00:00'
        write_document(fd, state)
    assert WebJobs(root).list()[0]['status'] == 'interrupted'
    session = AutomationSession(root, subject='crash-model', config_fingerprint='f' * 64)
    before = session.snapshot()['counts']
    assert before['model'] == 1
    store.enqueue(**{**command, 'request_id': 'b' * 32})
    process = child(root, 'model', recover=True)
    assert process.wait(timeout=10) == 0
    assert WebJobs(root).get('b' * 32)['result']['status'] == 'stopped'
    assert session.snapshot()['counts'] == before
    assert (root / 'effects').read_text().splitlines() == ['model']


@pytest.mark.parametrize('stage', ['commit', 'branch', 'pr'])
def test_kill_after_remote_effect_before_receipt_reconciles_without_repeating_writes(
        tmp_path, stage):
    kill_at_checkpoint(tmp_path, stage)
    before = (tmp_path / 'effects').read_text().splitlines()
    process = child(tmp_path, stage, recover=True)
    assert process.wait(timeout=10) == 0
    assert (tmp_path / 'outcome').read_text() == json.dumps({
        'status': 'stopped' if stage == 'commit' else 'delivered'})
    after = (tmp_path / 'effects').read_text().splitlines()
    assert after.count(stage) == before.count(stage) == 1
    assert all(after.count(kind) <= 1 for kind in ('commit', 'branch', 'pr'))


@pytest.mark.parametrize('point,expected', [('atomic-before', 1), ('atomic-after', 2)])
def test_kill_during_atomic_document_publication_keeps_whole_old_or_new_record(
        tmp_path, point, expected):
    directory = tmp_path / 'atomic'
    directory.mkdir()
    with lock_directory(directory) as fd:
        write_document(fd, {'generation': 1})
    kill_at_checkpoint(tmp_path, point)
    with lock_directory(directory) as fd:
        assert read_document(fd) == {'generation': expected}
    # Orphan staging files never replace the authoritative state on reopen.
    assert json.loads((directory / 'state.json').read_text()) == {'generation': expected}


def test_connection_reset_after_request_keeps_unknown_model_reservation(tmp_path):
    server = socket.socket()
    server.bind(('127.0.0.1', 0))
    server.listen(1)
    received = []
    def disconnect():
        connection, _ = server.accept()
        with connection:
            received.append(connection.recv(64))
    thread = threading.Thread(target=disconnect, daemon=True)
    thread.start()
    class Provider:
        def generate(self, prompt):
            with socket.create_connection(server.getsockname(), timeout=3) as connection:
                connection.sendall(b'inference-request')
                if connection.recv(1) == b'':
                    raise ConnectionResetError('fixture response lost')
            pytest.fail('response must be lost')
    session = AutomationSession(tmp_path, subject='broken-transport', config_fingerprint='f' * 64)
    provider = BudgetedModel(Provider(), session, role='fixture')
    try:
        with pytest.raises(ConnectionResetError):
            provider.generate('same prompt')
        with pytest.raises(StateConflict, match='do not replay'):
            provider.generate('same prompt')
        assert session.snapshot()['counts']['model'] == 1
        thread.join(timeout=5)
        assert received == [b'inference-request']
    finally:
        server.close()
