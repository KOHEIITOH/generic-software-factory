"""Known failures can repair; unknown effects, repeated candidates and budgets cannot replay."""
import base64
import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from test_issue_development import Model
from test_issue_development import flow as flow
from test_web_jobs import job_flow as job_flow
from test_web_jobs import login
from test_web_operator import HEADERS, ORIGIN

from sf_factory.automation_state import AutomationSession
from sf_factory.docker_execution import DockerExecutionResult
from sf_factory.issue_execution import execute_issue
from sf_factory.issue_improvement import improve_issue
from sf_factory.state_store import StatePermissionDenied
from sf_factory.web_api import create_app
from sf_factory.web_jobs import WebJobs
from sf_factory.web_worker import run_job


class RepairModel(Model):
    def __init__(self, candidates):
        super().__init__('repair-implementation')
        self.candidates, self.prompts = candidates, []

    def generate(self, prompt):
        self.prompts.append(prompt)
        result = super().generate(prompt)
        report = json.loads(result.text)
        report['changes'][0]['content'] = self.candidates[min(self.calls - 1,
                                                            len(self.candidates) - 1)]
        return replace(result, text=json.dumps(report))


@pytest.fixture
def repair(flow, monkeypatch):
    flow['config'] = replace(flow['config'], auto_improve=True)
    flow['implementer'] = RepairModel(['def add(a,b): return a-b\n',
                                      'def add(a,b): return a+b\n'])
    def execute(**kwargs):
        if 'input_bytes' not in kwargs:
            return DockerExecutionResult('succeeded', 0, 'SF_EXECUTION_READY\n',
                                         kwargs['image'], True)
        raw = kwargs['input_bytes']
        data = json.loads(raw)
        code = base64.b64decode(next(f['content'] for f in data['files']
                                    if f['path'] == 'app.py')).decode()
        output = '5\n' if 'returna+b' in code.replace(' ', '') else '-1\n'
        return DockerExecutionResult('succeeded', 0, json.dumps({'schema_version': 1,
            'request_sha256': hashlib.sha256(raw).hexdigest(), 'status': 'succeeded',
            'exit_code': 0, 'source_unchanged': True, 'output': output}), kwargs['image'], True)
    monkeypatch.setattr('sf_factory.issue_development.run_offline_command', execute)
    monkeypatch.setattr('sf_factory.workspace_check.run_offline_command', execute)
    return flow


def test_failure_evidence_drives_repair_and_exactly_one_draft(repair):
    result = execute_issue(**repair)
    assert result['status'] == 'completed', result
    assert result['attempt'] == 2
    assert result['attempts'][0]['failed_checks'] == ['addition']
    assert repair['implementer'].calls == 2 and repair['reviewer'].calls == 1
    assert 'Previous failed attempt' in repair['implementer'].prompts[1]
    assert '-1' in repair['implementer'].prompts[1]
    assert repair['scm'].writes == 3
    assert execute_issue(**repair)['pull_request'] == result['pull_request']
    assert repair['implementer'].calls == 2
    assert (repair['config'].root / 'app.py').read_text() == 'def add(a,b): return 0\n'
    opposite = execute_issue(**{**repair, 'config': replace(repair['config'], auto_improve=False)})
    assert opposite['pull_request'] == result['pull_request']
    assert repair['implementer'].calls == 2 and repair['scm'].writes == 3


def test_improvement_entry_requires_explicit_confirmation_and_policy(repair):
    with pytest.raises(StatePermissionDenied):
        improve_issue(**{**repair, 'confirmed': False})
    with pytest.raises(StatePermissionDenied):
        improve_issue(**{**repair, 'config': replace(repair['config'], auto_improve=False)})
    assert repair['implementer'].calls == 0 and repair['scm'].writes == 0


def test_review_findings_drive_a_distinct_candidate_and_fresh_review(repair):
    repair['implementer'].candidates = ['def add(a,b): return a + b\n',
                                        'def add(a,b): return a+b\n']
    reviewer = repair['reviewer']
    original = reviewer.generate
    def review(prompt):
        reviewer.must_fix = reviewer.calls == 0
        return original(prompt)
    reviewer.generate = review
    result = execute_issue(**repair)
    assert result['status'] == 'completed', result
    assert result['attempts'][0]['kind'] == 'review'
    assert result['attempts'][0]['must_fix'] == 1
    assert 'fixture finding' in repair['implementer'].prompts[1]
    assert reviewer.calls == repair['implementer'].calls == 2
    assert repair['scm'].writes == 3


def test_identical_changes_stop_before_repeating_checks(repair):
    repair['implementer'].candidates = ['def add(a,b): return a-b\n']
    result = execute_issue(**repair)
    assert result['reason'] == 'candidate_repeated', result
    assert repair['implementer'].calls == 2 and repair['scm'].writes == 0
    assert execute_issue(**repair)['reason'] == 'candidate_repeated'
    assert repair['implementer'].calls == 2


def test_known_invalid_json_response_is_repaired_without_replaying_unknown_calls(repair):
    model = repair['implementer']
    model.candidates = ['def add(a,b): return a+b\n']
    original = model.generate
    def malformed_once(prompt):
        result = original(prompt)
        return replace(result, text='not valid JSON') if model.calls == 1 else result
    model.generate = malformed_once
    result = execute_issue(**repair)
    assert result['status'] == 'completed', result
    assert result['attempts'][0]['kind'] == 'candidate'
    assert model.calls == 2 and repair['scm'].writes == 3


def test_repeated_invalid_json_stops_automatically(repair):
    model = repair['implementer']
    original = model.generate
    model.generate = lambda prompt: replace(original(prompt), text='not valid JSON')
    result = execute_issue(**repair)
    assert result['reason'] == 'candidate_repeated', result
    assert model.calls == 2 and repair['scm'].writes == 0


def test_three_distinct_failures_exhaust_persistent_budget(repair):
    repair['implementer'].candidates = [f'def add(a,b): return a-b # {i}\n' for i in range(3)]
    result = execute_issue(**repair)
    assert result['reason'] == 'auto_improvement_exhausted', result
    assert len(result['attempts']) == 3
    assert repair['implementer'].calls == 3 and repair['scm'].writes == 0
    assert execute_issue(**repair)['reason'] == result['reason']
    assert repair['implementer'].calls == 3


def test_lost_model_effect_is_not_automatically_retried(repair):
    def lost(prompt):
        repair['implementer'].calls += 1
        raise TimeoutError('unknown response')
    repair['implementer'].generate = lost
    result = execute_issue(**repair)
    assert result['reason'] == 'auto_improvement_unknown_inference', result
    assert execute_issue(**repair)['reason'] == result['reason']
    assert repair['implementer'].calls == 1 and repair['scm'].writes == 0


def test_worker_crash_cannot_start_a_second_candidate(repair):
    def crash(prompt):
        repair['implementer'].calls += 1
        raise KeyboardInterrupt('worker lost')
    repair['implementer'].generate = crash
    with pytest.raises(KeyboardInterrupt):
        execute_issue(**repair)
    result = execute_issue(**repair)
    assert result['reason'] == 'issue_execution_outcome_unknown', result
    assert repair['implementer'].calls == 1 and repair['scm'].writes == 0


def test_unknown_delivery_resumes_same_reviewed_run_without_new_inference(repair):
    repair['scm'].fail_pr = True
    first = execute_issue(**repair)
    assert first['reason'] == 'issue_delivery_reconciliation_required', first
    second = execute_issue(**repair)
    assert second['status'] == 'completed', second
    assert second['run_id'] == first['run_id']
    assert repair['implementer'].calls == 2 and repair['reviewer'].calls == 1
    assert repair['scm'].writes == 3


def test_ready_repair_survives_restart_without_replaying_first_inference(repair, monkeypatch):
    import sf_factory.issue_improvement as controller
    save = controller._save
    def crash_after_save(session, data, code, **kwargs):
        result = save(session, data, code, **kwargs)
        if code == 'auto_improvement_planned':
            raise KeyboardInterrupt('worker lost after durable repair plan')
        return result
    monkeypatch.setattr(controller, '_save', crash_after_save)
    with pytest.raises(KeyboardInterrupt):
        execute_issue(**repair)
    monkeypatch.setattr(controller, '_save', save)
    result = execute_issue(**repair)
    assert result['status'] == 'completed', result
    assert repair['implementer'].calls == 2 and repair['scm'].writes == 3


def test_shared_model_budget_cannot_reset_between_candidates(repair, monkeypatch):
    import sf_factory.issue_improvement as controller
    monkeypatch.setattr(controller, 'LIMITS', replace(controller.LIMITS, max_model_calls=1))
    result = execute_issue(**repair)
    assert result['reason'] == 'budget_exhausted', result
    assert execute_issue(**repair)['reason'] == 'budget_exhausted'
    assert repair['implementer'].calls == 1 and repair['scm'].writes == 0


def test_deadline_stops_before_checks_and_new_inference(repair, monkeypatch):
    import sf_factory.issue_improvement as controller
    now = [datetime(2026, 11, 17, tzinfo=UTC)]
    monkeypatch.setattr(controller, 'AutomationSession',
        lambda *a, **kw: AutomationSession(*a, **kw, clock=lambda: now[0]))
    generate = repair['implementer'].generate
    def expire(prompt):
        result = generate(prompt)
        now[0] += timedelta(seconds=3601)
        return result
    repair['implementer'].generate = expire
    result = execute_issue(**repair)
    assert result['reason'] == 'deadline_exhausted', result
    assert repair['implementer'].calls == 1 and repair['scm'].writes == 0


def test_web_flag_is_authenticated_frozen_and_passed_to_worker(job_flow, monkeypatch):
    from fastapi.testclient import TestClient
    root, auth, payload, calls = job_flow
    payload = {**payload, 'action': 'develop', 'issue_id': '1', 'auto_improve': True}
    with TestClient(create_app(data_dir=root, operator=auth), base_url=ORIGIN) as client:
        url = '/api/operator/jobs'
        assert client.post(url, json=payload, headers=HEADERS).status_code == 401
        login(client, auth)
        response = client.post(url, json=payload, headers=HEADERS)
        assert response.status_code == 202
        assert response.json()['job']['auto_improve'] is True
        changed = client.post(url, json={**payload, 'auto_improve': False}, headers=HEADERS)
        assert changed.status_code == 409
    def execute(**kwargs):
        assert kwargs['auto_improve'] is True and kwargs['issue_id'] == '1'
        return {'status': 'completed'}
    assert run_job(root, payload['request_id'], executor=execute)
    assert WebJobs(root).get(payload['request_id'])['result']['status'] == 'completed'


def test_real_docker_issue_auto_improvement_to_draft(repair, job_flow, monkeypatch):
    import os
    if not os.environ.get('SF_TEST_DOCKER_IMAGE'):
        pytest.skip('requires configured real Docker integration')
    from sf_factory.docker_execution import run_offline_command
    monkeypatch.setattr('sf_factory.issue_development.run_offline_command', run_offline_command)
    monkeypatch.setattr('sf_factory.workspace_check.run_offline_command', run_offline_command)
    root, auth, payload, calls = job_flow
    store = WebJobs(root)
    command = {**payload, 'action': 'develop', 'issue_id': '1', 'auto_improve': True}
    job, _ = store.enqueue(**{k: v for k, v in command.items() if k != 'confirm_run'})
    assert run_job(root, job['id'], executor=lambda **kwargs: execute_issue(**repair))
    result = store.get(job['id'])['result']
    assert result['status'] == 'completed', result
    progress = store.progress(job['id'])
    assert progress['improvement']['attempt'] == 2
    assert progress['improvement']['attempts'][0]['kind'] == 'checks'
    assert progress['counts']['model'] == 3
    assert progress['pr_url'] == 'https://fixture.invalid/pr/7'
    assert repair['scm'].writes == 3
    assert 'previous_changes' not in json.dumps(progress)
