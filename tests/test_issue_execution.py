"""Selected Issue uses the real evidence/delivery path; external model/SCM simulated."""
from dataclasses import replace

import pytest
from test_issue_development import flow as flow
from test_web_jobs import job_flow as job_flow
from test_web_jobs import login
from test_web_operator import HEADERS, ORIGIN

from sf_factory.automation_state import AutomationSession
from sf_factory.file_state import lock_directory
from sf_factory.issue_execution import execute_issue
from sf_factory.web_api import create_app
from sf_factory.web_jobs import WebJobs
from sf_factory.web_worker import run_job


def test_one_issue_to_draft_and_second_click_returns_same_receipt(flow):
    first = execute_issue(**flow)
    assert first['status'] == 'completed'
    assert first['pull_request']['external_id'] == '7'
    second = execute_issue(**flow)
    assert second['pull_request'] == first['pull_request']
    assert second['run_id'] == first['run_id']
    assert flow['scm'].writes == 3
    assert flow['implementer'].calls == flow['reviewer'].calls == 1
    assert len(flow['factory'].list_runs()) == 1


def test_failed_independent_review_is_terminal_and_does_not_retry(flow):
    flow['reviewer'].must_fix = True
    first = execute_issue(**flow)
    assert first['status'] == 'stopped'
    assert first['reason'] == 'issue_quality_failed'
    assert execute_issue(**flow)['status'] == 'stopped'
    assert flow['scm'].writes == 0
    assert flow['implementer'].calls == flow['reviewer'].calls == 1


def test_unknown_pr_response_reconciles_same_run_without_inference(flow):
    flow['scm'].fail_pr = True
    first = execute_issue(**flow)
    assert first['status'] == 'waiting'
    second = execute_issue(**flow)
    assert second['status'] == 'completed'
    assert first['run_id'] == second['run_id']
    assert flow['scm'].writes == 3
    assert flow['implementer'].calls == flow['reviewer'].calls == 1


def test_lost_worker_after_inference_never_starts_new_candidate(flow):
    original = flow['implementer'].generate
    def killed(prompt):
        original(prompt)
        raise KeyboardInterrupt('simulated process loss')
    flow['implementer'].generate = killed
    with pytest.raises(KeyboardInterrupt):
        execute_issue(**flow)
    final = execute_issue(**flow)
    assert final['reason'] == 'issue_execution_outcome_unknown'
    assert flow['implementer'].calls == 1 and flow['scm'].writes == 0
    assert len(flow['factory'].list_runs()) == 1


def test_http_selection_is_scoped_to_registered_repository(job_flow, monkeypatch):
    from fastapi.testclient import TestClient

    root, auth, payload, calls = job_flow
    seen = []
    def listing(repository, page):
        seen.append((repository, page))
        return [], False
    monkeypatch.setattr('sf_factory.integration_defaults.list_open_issues', listing)
    with TestClient(create_app(data_dir=root, operator=auth), base_url=ORIGIN) as client:
        url = '/api/operator/profiles/' + payload['profile_id'] + '/issues'
        assert client.get(url, headers=HEADERS).status_code == 401
        login(client, auth)
        assert client.get(url, headers=HEADERS).json()['issues'] == []
        assert seen == [('fixture/repo', 1)]
        assert client.get(url + '?page=0', headers=HEADERS).status_code == 422
        for changes in ({'issue_id': None}, {'issue_id': '../2'}, {'repository': 'other/repo'},
                        {'allowed_paths': ['*']}, {'issue_id': '2', 'confirm_bedrock': False}):
            result = client.post('/api/operator/jobs', headers=HEADERS,
                json={**payload, 'action': 'develop', 'issue_id': '2', **changes})
            assert result.status_code in {403, 422}
        accepted = client.post('/api/operator/jobs', headers=HEADERS,
            json={**payload, 'action': 'develop', 'issue_id': '2'})
        assert accepted.status_code == 202
        assert accepted.json()['job']['issue_id'] == '2'
    executions = []
    def executor(**kwargs):
        executions.append(kwargs)
        assert kwargs['issue_id'] == '2' and kwargs['workflow_action'] == 'develop'
        assert kwargs['expected_fingerprint'] == payload['config_fingerprint']
        return {'status': 'completed'}
    assert run_job(root, payload['request_id'], executor=executor)
    assert len(executions) == 1 and calls == [payload['request_id']]


def test_worker_to_draft_has_no_import_or_plan_steps(job_flow, flow, monkeypatch):
    root, auth, payload, calls = job_flow
    store = WebJobs(root)
    job, _ = store.enqueue(**{k: v for k, v in {**payload, 'action': 'develop',
        'issue_id': '1'}.items() if k != 'confirm_run'})
    def executor(**kwargs):
        return execute_issue(**flow)
    assert run_job(root, job['id'], executor=executor)
    assert store.get(job['id'])['result']['status'] == 'completed'
    progress = store.progress(job['id'])
    assert progress['pr_url'] == 'https://fixture.invalid/pr/7'
    assert progress['counts']['model'] == 2
    assert not progress['children'] and progress['plan_preview'] is None
    assert not list(root.glob('requirement-controller-v1/*'))
    with lock_directory(
            root / 'automation-v1' / job['session_id']) as fd:
        assert AutomationSession._read(fd)['status'] == 'completed'


def test_selected_issue_cli_keeps_registered_execution_scope(flow, monkeypatch, tmp_path):
    import json
    from dataclasses import asdict

    from sf_factory.issue_development_cli import execute_local_development

    path = tmp_path / 'operator.json'
    path.write_text(json.dumps(asdict(flow['config']), default=str))
    captured = []
    def execute(**kwargs):
        captured.append(kwargs['config'])
        return {'status': 'completed'}
    monkeypatch.setattr('sf_factory.issue_execution.execute_issue', execute)
    monkeypatch.setattr('sf_factory.bedrock_provider.BedrockModelProvider',
                        lambda *a, **k: object())
    from types import SimpleNamespace
    monkeypatch.setattr('sf_factory.model_provider_status.bedrock_configuration', lambda:
        SimpleNamespace(configured=True, model_id='fixture-model', region_name='fixture-region'))
    execute_local_development(config_path=path, confirmed=True, confirm_bedrock=True,
        workflow_action='develop', issue_id='2', expected_fingerprint=flow['config'].fingerprint)
    assert captured == [replace(flow['config'], issue='2')]


def test_real_docker_selected_issue_to_draft(job_flow, flow, monkeypatch):
    import os

    from sf_factory.docker_execution import run_offline_command

    image = os.environ.get('SF_TEST_DOCKER_IMAGE')
    if not image:
        pytest.skip('optional real Docker execution image not configured')
    assert image == flow['config'].image
    monkeypatch.setattr('sf_factory.issue_development.run_offline_command', run_offline_command)
    monkeypatch.setattr('sf_factory.workspace_check.run_offline_command', run_offline_command)
    test_worker_to_draft_has_no_import_or_plan_steps(job_flow, flow, monkeypatch)


def test_simple_execution_includes_discovered_requirements_as_read_only_context(flow):
    from test_harness_runs import commit, git

    root = flow['config'].root
    (root / 'README.md').write_text('Requirement: add(a,b) returns the sum of its inputs.')
    commit(root)
    flow['scm'].parent = git(root, 'rev-parse', 'HEAD')
    observed = []
    original = flow['implementer'].generate
    def generate(prompt):
        observed.append(prompt)
        return original(prompt)
    flow['implementer'].generate = generate
    result = execute_issue(**flow)
    assert result['status'] == 'completed'
    assert result['requirement_sources']['documents'][0]['path'] == 'README.md'
    assert 'Requirement: add(a,b)' in observed[0]


def test_prerequisites_can_be_fixed_without_resetting_budget(flow, monkeypatch):
    from test_issue_development import fake_execution

    def unavailable(**kwargs):
        raise RuntimeError('fixture Docker unavailable')
    monkeypatch.setattr('sf_factory.issue_development.run_offline_command', unavailable)
    first = execute_issue(**flow)
    assert first['status'] == 'waiting'
    assert first['reason'] == 'issue_prerequisites_unavailable'
    assert flow['implementer'].calls == flow['reviewer'].calls == flow['scm'].writes == 0
    monkeypatch.setattr('sf_factory.issue_development.run_offline_command', fake_execution)
    second = execute_issue(**flow)
    assert second['status'] == 'completed' and second['session_id'] == first['session_id']


def test_recovery_after_completion_receipt_before_final_publication(flow, monkeypatch):
    import sf_factory.issue_execution as controller

    original = controller._save
    def crash(session, data, code, **kwargs):
        if code == 'draft_pr_created':
            raise KeyboardInterrupt('fixture crash before final session publication')
        return original(session, data, code, **kwargs)
    monkeypatch.setattr(controller, '_save', crash)
    with pytest.raises(KeyboardInterrupt):
        execute_issue(**flow)
    monkeypatch.setattr(controller, '_save', original)
    final = execute_issue(**flow)
    assert final['status'] == 'completed'
    assert flow['scm'].writes == 3
    assert flow['implementer'].calls == flow['reviewer'].calls == 1


def test_exhausted_model_budget_stops_without_sending_or_throwing(flow):
    from sf_factory.automation_state import fingerprint

    config = flow['config']
    session = AutomationSession(flow['factory'].root,
        subject='issue-development:' + config.repository + ':' + config.issue,
        config_fingerprint=fingerprint({'development': config.fingerprint, 'reviewers': ()}))
    for index in range(session.snapshot()['limits']['max_model_calls']):
        session.reserve('model', 'prior:' + str(index))
    assert execute_issue(**flow)['status'] == 'stopped'
    assert flow['implementer'].calls == 0 and flow['scm'].writes == 0
    assert session.snapshot()['decisions'][-1]['code'] == 'budget_exhausted'
