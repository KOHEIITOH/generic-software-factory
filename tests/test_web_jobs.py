"""Real private durable state, fake execution; no network/AI/Docker charges."""
import fcntl
import json
import os
from dataclasses import asdict

import pytest
from fastapi.testclient import TestClient
from test_issue_development import flow as flow
from test_requirement_workflow import requirement_flow as requirement_flow
from test_web_operator import HEADERS, ORIGIN

from sf_factory.operation_control import checkpoint
from sf_factory.state_store import StateConflict
from sf_factory.web_api import create_app
from sf_factory.web_jobs import WebJobs
from sf_factory.web_operator import OperatorProfiles, WebOperator
from sf_factory.web_worker import run_job


@pytest.fixture
def job_flow(flow, monkeypatch):
    root = flow['factory'].root
    path = root.parent / 'operator.json'
    path.write_text(json.dumps(asdict(flow['config']), default=str))
    profile = OperatorProfiles(root).register(path, 'Test repository')
    auth = WebOperator(ORIGIN)
    calls = []
    monkeypatch.setattr(WebJobs, 'spawn', lambda self, key: calls.append(key))
    payload = {'profile_id': profile['id'], 'config_fingerprint': profile['fingerprint'],
               'request_id': 'a' * 32, 'action': 'advance', 'confirm_run': True,
               'confirm_bedrock': True}
    return root, auth, payload, calls


def login(client, auth):
    assert client.post('/api/operator/session', headers={**HEADERS,
        'authorization': 'Bearer ' + auth.token}).status_code == 200


def test_http_consent_auth_allowlist_and_duplicate_submission(job_flow):
    root, auth, payload, calls = job_flow
    with TestClient(create_app(data_dir=root, operator=auth), base_url=ORIGIN) as client:
        assert client.post('/api/operator/jobs', json=payload, headers=HEADERS).status_code == 401
        login(client, auth)
        for change in ({'confirm_run': False}, {'confirm_bedrock': False},
                       {'config_fingerprint': 'b' * 64}, {'profile_id': 'f' * 32}):
            assert client.post('/api/operator/jobs', json={**payload, **change},
                               headers=HEADERS).status_code == 403
        assert client.post('/api/operator/jobs', json={**payload, 'path': '/etc/passwd'},
                           headers=HEADERS).status_code == 422
        first = client.post('/api/operator/jobs', json=payload, headers=HEADERS)
        assert first.status_code == 202
        assert client.post('/api/operator/jobs', json=payload, headers=HEADERS).status_code == 202
        assert calls == ['a' * 32]
        assert client.post('/api/operator/jobs', json={**payload, 'request_id': 'b' * 32},
                           headers=HEADERS).status_code == 409
        view = client.get('/api/operator/jobs', headers=HEADERS)
        assert view.status_code == 200 and view.headers['cache-control'] == 'no-store'
        assert 'operator.json' not in view.text and auth.token not in view.text


def test_worker_calls_same_operator_entry_once_and_projects_result(job_flow):
    root, auth, payload, calls = job_flow
    with TestClient(create_app(data_dir=root, operator=auth), base_url=ORIGIN) as client:
        login(client, auth)
        client.post('/api/operator/jobs', json=payload, headers=HEADERS)
    executions = []
    def execute(**kwargs):
        executions.append(kwargs)
        assert kwargs['expected_fingerprint'] == payload['config_fingerprint']
        checkpoint()
        return {'status': 'waiting', 'reason': 'child_pr_submitted',
                'session_id': 'f' * 32, 'repository_context': 'PRIVATE SOURCE',
                'prompt': 'PRIVATE REQUIREMENT'}
    assert run_job(root, 'a' * 32, executor=execute)
    assert not run_job(root, 'a' * 32, executor=execute)
    assert len(executions) == 1
    store = WebJobs(root)
    assert store.get('a' * 32)['status'] == 'finished'
    assert 'PRIVATE' not in json.dumps(store.list())


def test_queued_stop_executes_nothing_and_running_stop_hits_checkpoint(job_flow):
    root, auth, payload, calls = job_flow
    store = WebJobs(root)
    command = {k: v for k, v in payload.items() if k != 'confirm_run'}
    store.enqueue(**command)
    store.stop('a' * 32)
    assert not run_job(root, 'a' * 32, executor=lambda **k: pytest.fail('must not execute'))
    command['request_id'] = 'b' * 32
    store.enqueue(**command)
    reached = []
    def execute(**kwargs):
        store.stop('b' * 32)
        checkpoint()
        reached.append('unexpected side effect')
        return {'status': 'waiting'}
    assert run_job(root, 'b' * 32, executor=execute)
    assert not reached and store.get('b' * 32)['status'] == 'stopped'


def test_live_lease_survives_new_store_but_missing_worker_is_interrupted(job_flow):
    root, auth, payload, calls = job_flow
    store = WebJobs(root)
    store.enqueue(**{k: v for k, v in payload.items() if k != 'confirm_run'})
    store.change('a' * 32, code='fixture', status='running')
    lease = store.lease('a' * 32)
    fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        # Old timestamps make PID-free lease ownership the authoritative fact.
        from sf_factory.file_document import read_document, write_document
        from sf_factory.file_state import lock_directory
        with lock_directory(store.directory) as fd:
            doc = read_document(fd)
            doc['jobs']['a' * 32]['updated_at'] = '2000-01-01T00:00:00+00:00'
            write_document(fd, doc)
        assert WebJobs(root).list()[0]['status'] == 'running'
    finally:
        os.close(lease)
    assert WebJobs(root).list()[0]['status'] == 'interrupted'
    assert not run_job(root, 'a' * 32, executor=lambda **k: pytest.fail('no auto replay'))


def test_profile_revocation_stops_before_the_next_effect(job_flow):
    root, auth, payload, calls = job_flow
    store = WebJobs(root)
    store.enqueue(**{k: v for k, v in payload.items() if k != 'confirm_run'})
    def execute(**kwargs):
        OperatorProfiles(root).revoke(payload['profile_id'])
        checkpoint()
        pytest.fail('revoked scope cannot reach next effect')
    assert run_job(root, 'a' * 32, executor=execute)
    assert store.get('a' * 32)['result']['status'] == 'stopped'


def test_default_uvicorn_app_has_no_execution_authority(tmp_path):
    with TestClient(create_app(data_dir=tmp_path), base_url=ORIGIN) as client:
        assert client.get('/api/operator/status').json() == {'enabled': False}
        assert client.get('/api/operator/profiles', headers=HEADERS).status_code == 403


def test_request_identity_cannot_be_rebound_to_other_action(job_flow):
    root, auth, payload, calls = job_flow
    store = WebJobs(root)
    command = {k: v for k, v in payload.items() if k != 'confirm_run'}
    store.enqueue(**command)
    with pytest.raises(StateConflict):
        store.enqueue(**{**command, 'action': 'plan'})


def test_real_private_subprocess_finishes_without_ai_when_provider_is_unconfigured(
        job_flow, monkeypatch):
    import time
    root, auth, payload, calls = job_flow
    store = WebJobs(root)
    store.enqueue(**{k: v for k, v in payload.items() if k != 'confirm_run'})
    monkeypatch.setenv('SF_BEDROCK_MODEL_ID', '')
    # Exercise the actual isolated module launch rather than the HTTP spawn mock.
    import subprocess
    import sys
    process = subprocess.Popen([sys.executable, '-I', '-m', 'sf_factory.web_worker',
        str(root), 'a' * 32], cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        assert process.wait(timeout=10) == 0
        for _ in range(20):
            if store.get('a' * 32)['status'] == 'finished':
                break
            time.sleep(0.05)
        assert store.get('a' * 32)['result']['status'] == 'stopped'
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def test_real_docker_web_worker_advances_existing_workflow(requirement_flow, monkeypatch):
    from sf_factory.docker_execution import run_offline_command
    args = requirement_flow
    image = os.environ.get('SF_TEST_DOCKER_IMAGE')
    if not image:
        pytest.skip('optional real Docker execution image not configured')
    assert image == args['config'].image
    monkeypatch.setattr('sf_factory.issue_development.run_offline_command', run_offline_command)
    monkeypatch.setattr('sf_factory.workspace_check.run_offline_command', run_offline_command)
    path = args['config'].root.parent / 'web-operator.json'
    path.write_text(json.dumps(asdict(args['config']), default=str))
    root = args['factory'].root
    profile = OperatorProfiles(root).register(path, 'Real Docker worker fixture')
    store = WebJobs(root)
    store.enqueue(profile_id=profile['id'], config_fingerprint=profile['fingerprint'],
        action='advance', request_id='a' * 32, confirm_bedrock=True)
    from sf_factory.requirement_workflow import advance_requirements
    assert run_job(root, 'a' * 32, executor=lambda **k: advance_requirements(**args, execute=True))
    assert store.get('a' * 32)['result']['reason'] == 'child_pr_submitted'
    assert store.progress('a' * 32)['children'][0]['pr_url']


def test_stop_checkpoint_blocks_actual_external_and_container_start_boundaries(flow):
    from sf_factory.automation_state import AutomationSession
    from sf_factory.budgeted_model import BudgetedModel
    from sf_factory.docker_execution import run_offline_command
    from sf_factory.github_issues_source import GitHubIssuesSource
    from sf_factory.github_source_control import GitHubSourceControl
    from sf_factory.operation_control import OperationStopped, operation_control
    session = AutomationSession(flow['factory'].root, subject='boundary-test',
                                config_fingerprint='e' * 64)
    def stop():
        raise OperationStopped('fixture stopped')
    with operation_control(stop):
        for operation in (
            lambda: GitHubSourceControl().describe_repository('fixture/repo'),
            lambda: GitHubIssuesSource('fixture/repo').fetch_issue('1'),
            lambda: run_offline_command(image=flow['config'].image, argv=('python', '-V')),
            lambda: BudgetedModel(flow['implementer'], session, role='fixture').generate('test'),
        ):
            with pytest.raises(OperationStopped):
                operation()
    assert flow['implementer'].calls == 0
    assert session.snapshot()['counts']['model'] == 0


def test_history_is_chronological_even_when_random_job_ids_sort_oppositely(job_flow):
    root, auth, payload, calls = job_flow
    store = WebJobs(root)
    command = {k: v for k, v in payload.items() if k != 'confirm_run'}
    store.enqueue(**{**command, 'request_id': 'f' * 32})
    store.stop('f' * 32)
    store.enqueue(**{**command, 'request_id': '0' * 32})
    assert [j['id'] for j in store.list()] == ['0' * 32, 'f' * 32]
