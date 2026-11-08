"""Exact reviewed-plan approval is persisted before native Issue writes; no model replay."""
import json
from dataclasses import asdict

import pytest
from test_issue_development import flow as flow
from test_requirement_discovery_workflow import install_documents
from test_requirement_workflow import requirement_flow as requirement_flow

from sf_factory.automation_state import AutomationSession, fingerprint
from sf_factory.requirement_workflow import PLAN_LIMITS, advance_requirements
from sf_factory.web_jobs import WebJobs
from sf_factory.web_operator import OperatorProfiles


def session(args):
    config = args['config']
    return AutomationSession(args['factory'].root,
        subject='requirements:' + config.repository + ':' + config.issue,
        config_fingerprint=fingerprint({'development': config.fingerprint, 'reviewers': ()}),
        limits=PLAN_LIMITS)


def test_preview_creates_no_child_or_pr_and_even_cli_cannot_bypass_required_approval(
        requirement_flow):
    args = requirement_flow
    result = advance_requirements(**args, execute=True, require_plan_approval=True)
    assert result['reason'] == 'awaiting_plan_approval'
    assert args['tracker'].creates == 0 and args['scm'].prs == {}
    calls = args['implementer'].calls
    token = result['plan_approval']['fingerprint']
    assert advance_requirements(**args, execute=True)['reason'] == 'awaiting_plan_approval'
    wrong = advance_requirements(**args, approved_plan='f' * 64)
    assert wrong['reason'] == 'plan_approval_mismatch'
    assert args['implementer'].calls == calls and args['tracker'].creates == 0
    approved = advance_requirements(**args, approved_plan=token)
    assert approved['reason'] == 'plan_ready' and args['tracker'].creates == 2
    assert args['implementer'].calls == calls
    assert approved['plan_approval']['status'] == 'approved'
    assert any(e['code'] == 'human_plan_approved' for e in session(args).snapshot()['decisions'])
    assert advance_requirements(**args, execute=True)['reason'] == 'child_pr_submitted'


def test_approval_rejects_changed_remote_source_and_never_uses_old_plan(requirement_flow):
    args = requirement_flow
    result = advance_requirements(**args, require_plan_approval=True)
    args['scm'].parent = 'f' * 40
    approved = advance_requirements(**args, approved_plan=result['plan_approval']['fingerprint'])
    assert approved['reason'] == 'plan_approval_stale' and args['tracker'].creates == 0


def test_approval_binds_local_baseline_and_exact_derived_plan(requirement_flow):
    args = requirement_flow
    result = advance_requirements(**args, require_plan_approval=True)
    (args['config'].root / 'app.py').write_text('dirty worktree')
    assert advance_requirements(**args, approved_plan=result['plan_approval']['fingerprint'])[
        'status'] == 'stopped'
    assert args['tracker'].creates == 0


def test_approval_of_unknown_plan_does_not_start_any_inference(requirement_flow):
    args = requirement_flow
    unknown = advance_requirements(**args, approved_plan='a' * 64)
    assert unknown['reason'] == 'plan_approval_not_ready'
    assert args['implementer'].calls == args['reviewer'].calls == args['tracker'].creates == 0


def test_approval_survives_process_loss_after_receipt_without_duplicate_publication(
        requirement_flow, monkeypatch):
    import sf_factory.requirement_workflow as workflow
    args = requirement_flow
    result = advance_requirements(**args, require_plan_approval=True)
    save = workflow._save
    class LostProcess(BaseException):
        pass
    def crash(session, data, code, **kwargs):
        result = save(session, data, code, **kwargs)
        if code == 'human_plan_approved':
            raise LostProcess()
        return result
    monkeypatch.setattr(workflow, '_save', crash)
    with pytest.raises(LostProcess):
        advance_requirements(**args, approved_plan=result['plan_approval']['fingerprint'])
    monkeypatch.setattr(workflow, '_save', save)
    assert session(args).snapshot()['data']['plan_approval']['status'] == 'approved'
    assert args['tracker'].creates == 0
    assert advance_requirements(**args)['reason'] == 'plan_ready'
    assert args['tracker'].creates == 2
    assert advance_requirements(**args)['reason'] == 'plan_ready'
    assert args['tracker'].creates == 2


def test_web_approval_requires_current_plan_token_but_not_bedrock_consent(requirement_flow):
    args = requirement_flow
    install_documents(args, {'docs/requirements.md': b'approved addition requirements'})
    result = advance_requirements(**args, require_plan_approval=True)
    root = args['factory'].root
    path = root.parent / 'profile.json'
    path.write_text(json.dumps(asdict(args['config']), default=str))
    profile = OperatorProfiles(root).register(path, 'Plan approval')
    store = WebJobs(root)
    token = result['plan_approval']['fingerprint']
    from sf_factory.state_store import StateConflict
    with pytest.raises(StateConflict):
        store.enqueue(profile_id=profile['id'], config_fingerprint=profile['fingerprint'],
            request_id='a' * 32, action='approve', confirm_bedrock=False, approved_plan='f' * 64)
    job, created = store.enqueue(
        profile_id=profile['id'], config_fingerprint=profile['fingerprint'],
        request_id='b' * 32, action='approve', confirm_bedrock=False, approved_plan=token)
    assert created and job['approved_plan'] == token
    preview = store.progress(job['id'])['plan_preview']
    assert preview['approval_status'] == 'pending' and preview['plan']['children'][0]['acceptance']
    assert preview['interpretation'] and 'repository_context' not in preview


def test_approve_operator_entry_does_not_initialize_ai_provider(requirement_flow, monkeypatch):
    from sf_factory.issue_development_cli import execute_local_development
    args = requirement_flow
    result = advance_requirements(**args, require_plan_approval=True)
    path = args['config'].root.parent / 'approve-config.json'
    path.write_text(json.dumps(asdict(args['config']), default=str))
    monkeypatch.setattr('sf_factory.factory_selection.open_factory', lambda p: args['factory'])
    monkeypatch.setattr('sf_factory.integration_defaults.task_source', lambda r: args['source'])
    monkeypatch.setattr('sf_factory.github_issue_tracker.GitHubIssueTracker', lambda: args['scm'])
    # The test SCM needs the external IssueTracker operations as well.
    for name in ('find_issue', 'create_issue', 'child_issues', 'attach_child'):
        monkeypatch.setattr(args['scm'], name, getattr(args['tracker'], name), raising=False)
    monkeypatch.setenv('SF_BEDROCK_MODEL_ID', '')
    assert execute_local_development(config_path=path, confirmed=True, confirm_bedrock=False,
        workflow_action='approve', require_plan_approval=True,
        approved_plan=result['plan_approval']['fingerprint'])['reason'] == 'plan_ready'


def test_source_change_after_durable_approval_before_publish_invalidates_it(requirement_flow):
    args = requirement_flow
    advance_requirements(**args, require_plan_approval=True)
    document = session(args)
    state = document.snapshot()
    data = state['data']
    # Reopen the exact state after durable approval and before first publication.
    data['plan_approval']['status'] = 'approved'
    document.save(data, expected_version=state['version'])
    args['scm'].parent = 'e' * 40
    assert advance_requirements(**args)['reason'] == 'plan_approval_stale'
    assert args['tracker'].creates == 0


def test_http_approval_requires_operator_consent_and_rejects_plan_payload_override(
        requirement_flow, monkeypatch):
    from fastapi.testclient import TestClient
    from test_web_operator import HEADERS, ORIGIN

    from sf_factory.web_api import create_app
    from sf_factory.web_operator import WebOperator
    args = requirement_flow
    result = advance_requirements(**args, require_plan_approval=True)
    root = args['factory'].root
    path = root.parent / 'profile.json'
    path.write_text(json.dumps(asdict(args['config']), default=str))
    profile = OperatorProfiles(root).register(path, 'Approve HTTP')
    calls = []
    monkeypatch.setattr(WebJobs, 'spawn', lambda self, key: calls.append(key))
    auth = WebOperator(ORIGIN)
    body = {'profile_id': profile['id'], 'config_fingerprint': profile['fingerprint'],
        'request_id': 'a' * 32, 'action': 'approve', 'confirm_run': True,
        'approved_plan': result['plan_approval']['fingerprint']}
    with TestClient(create_app(data_dir=root, operator=auth), base_url=ORIGIN) as client:
        assert client.post('/api/operator/jobs', json=body, headers=HEADERS).status_code == 401
        client.post('/api/operator/session', headers={**HEADERS,
            'authorization': 'Bearer ' + auth.token})
        assert client.post('/api/operator/jobs', json={**body, 'confirm_run': False},
                           headers=HEADERS).status_code == 403
        assert client.post('/api/operator/jobs', json={**body, 'plan': {}},
                           headers=HEADERS).status_code == 422
        assert client.post('/api/operator/jobs', json=body, headers=HEADERS).status_code == 202
        assert client.post('/api/operator/jobs', json=body, headers=HEADERS).status_code == 202
        assert calls == ['a' * 32]


def test_real_docker_plan_preview_approval_then_draft(requirement_flow, monkeypatch):
    import os
    image = os.environ.get('SF_TEST_DOCKER_IMAGE')
    if not image:
        pytest.skip('optional real Docker execution image not configured')
    from sf_factory.docker_execution import run_offline_command
    args = requirement_flow
    assert args['config'].image == image
    monkeypatch.setattr('sf_factory.issue_development.run_offline_command', run_offline_command)
    monkeypatch.setattr('sf_factory.workspace_check.run_offline_command', run_offline_command)
    preview = advance_requirements(**args, require_plan_approval=True)
    assert preview['reason'] == 'awaiting_plan_approval' and args['tracker'].creates == 0
    calls = args['implementer'].calls
    assert advance_requirements(**args,
        approved_plan=preview['plan_approval']['fingerprint'])['reason'] == 'plan_ready'
    assert args['implementer'].calls == calls
    assert advance_requirements(**args, execute=True)['reason'] == 'child_pr_submitted'


def test_preview_waits_for_durable_approval_request_after_plan_publication_crash(requirement_flow):
    from sf_factory.plan_preview import plan_preview
    args = requirement_flow
    advance_requirements(**args, require_plan_approval=True)
    document = session(args)
    state = document.snapshot()
    data = state['data']
    data.pop('plan_approval')
    document.save(data, expected_version=state['version'])
    assert plan_preview(document.snapshot()) is None
    calls = args['implementer'].calls
    assert advance_requirements(**args)['reason'] == 'awaiting_plan_approval'
    assert args['implementer'].calls == calls and args['tracker'].creates == 0


def test_damaged_approval_job_without_fingerprint_is_rejected(requirement_flow):
    from sf_factory.file_document import read_document, write_document
    from sf_factory.file_state import lock_directory
    from sf_factory.state_store import StateConflict
    args = requirement_flow
    result = advance_requirements(**args, require_plan_approval=True)
    root = args['factory'].root
    path = root.parent / 'profile.json'
    path.write_text(json.dumps(asdict(args['config']), default=str))
    profile = OperatorProfiles(root).register(path, 'Approval integrity')
    store = WebJobs(root)
    store.enqueue(profile_id=profile['id'], config_fingerprint=profile['fingerprint'],
        request_id='a' * 32, action='approve', confirm_bedrock=False,
        approved_plan=result['plan_approval']['fingerprint'])
    with lock_directory(store.directory) as fd:
        state = read_document(fd)
        state['jobs']['a' * 32].pop('approved_plan')
        write_document(fd, state)
    with pytest.raises(StateConflict, match='invalid Web job'):
        WebJobs(root)
