"""Guided setup pins reviewed scopes, never executes repository commands or edits Git."""
import json
from dataclasses import asdict, replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_harness_runs import commit, git
from test_issue_development import flow as flow
from test_web_jobs import job_flow as job_flow
from test_web_jobs import login
from test_web_operator import HEADERS, ORIGIN

from sf_factory.harness_composition import compose_harness
from sf_factory.harness_validation import validate_harness
from sf_factory.issue_development import develop_issue
from sf_factory.issue_execution import execute_issue
from sf_factory.operator_setup import SetupProposals
from sf_factory.state_store import StateConflict, StatePermissionDenied
from sf_factory.web_api import create_app
from sf_factory.web_jobs import WebJobs
from sf_factory.web_operator import OperatorProfiles
from sf_factory.web_worker import run_job


@pytest.fixture(autouse=True)
def github_origin(flow):
    git(flow['config'].root, 'remote', 'add', 'origin', 'https://github.com/fixture/repo.git')


def setup_args(flow):
    config = flow['config']
    return dict(root=config.root, repository=config.repository, name='Web fixture',
                provider=config.provider, image=config.image, allowed_paths=config.allowed_paths,
                checks=config.checks)


def test_existing_harness_is_reused_and_approval_registers_private_config(flow):
    store = SetupProposals(flow['factory'].root)
    value = store.initial(**setup_args(flow))
    assert value['selected_harness'] == ['AGENTS.md']
    assert value['project_harness'] is None
    assert OperatorProfiles(store.root).list() == []
    assert flow['implementer'].calls == 0 and flow['scm'].writes == 0
    approved = store.approve(value['id'], value['fingerprint'])
    profile, config = OperatorProfiles(store.root).get(approved['profile']['id'])
    assert config == flow['config']
    assert not Path(profile['path']).is_relative_to(config.root)
    assert store.approve(value['id'], value['fingerprint']) == approved
    assert git(config.root, 'status', '--porcelain') == ''


def test_no_harness_generates_project_layer_and_runs_full_delivery(flow):
    root = flow['config'].root
    (root / 'AGENTS.md').unlink()
    commit(root)
    flow['scm'].parent = git(root, 'rev-parse', 'HEAD')
    store = SetupProposals(flow['factory'].root)
    value = store.initial(**setup_args(flow))
    assert value['selected_harness'] == []
    assert value['project_harness']['rules'][1]['name'] == 'quality'
    receipt = store.approve(value['id'], value['fingerprint'])
    _, config = OperatorProfiles(store.root).get(receipt['profile']['id'])
    assert config.project_harness and not config.selected_harness
    compose_harness(validate_harness(root), target='.', selected=(),
                    project_harness=config.project_harness, change_paths=config.allowed_paths)
    result = develop_issue(**{**flow, 'config': config})
    assert result['status'] == 'draft_pr_created'
    assert not (root / 'AGENTS.md').exists()
    assert git(root, 'status', '--porcelain') == ''
    run = flow['factory'].show_run(result['run_id'])
    assert run['harness_manifest']['composition']['project_harness']['rules']


def test_changed_revision_hash_or_symlink_cannot_approve(flow, tmp_path):
    store = SetupProposals(flow['factory'].root)
    value = store.initial(**setup_args(flow))
    with pytest.raises(StateConflict):
        store.approve(value['id'], 'f' * 64)
    (flow['config'].root / 'AGENTS.md').write_text('Changed rules')
    commit(flow['config'].root)
    with pytest.raises(StateConflict):
        store.approve(value['id'], value['fingerprint'])
    link = tmp_path / 'linked'
    link.symlink_to(flow['config'].root, target_is_directory=True)
    with pytest.raises(ValueError):
        store.initial(**{**setup_args(flow), 'root': link})


def test_registration_lost_response_does_not_revive_revoked_profile(flow, monkeypatch):
    store = SetupProposals(flow['factory'].root)
    value = store.initial(**setup_args(flow))
    original = OperatorProfiles.register
    def lose_response(self, *args, **kwargs):
        original(self, *args, **kwargs)
        raise KeyboardInterrupt('fixture after registry commit')
    monkeypatch.setattr(OperatorProfiles, 'register', lose_response)
    with pytest.raises(KeyboardInterrupt):
        store.approve(value['id'], value['fingerprint'])
    monkeypatch.setattr(OperatorProfiles, 'register', original)
    profile = OperatorProfiles(store.root).list()[0]
    OperatorProfiles(store.root).revoke(profile['id'])
    with pytest.raises(StateConflict):
        store.approve(value['id'], value['fingerprint'])
    assert OperatorProfiles(store.root).list()[0]['available'] is False


def test_failed_web_run_generates_bounded_evidence_linked_improvement(job_flow, flow):
    root, _, payload, _ = job_flow
    flow['reviewer'].must_fix = True
    store = WebJobs(root)
    store.enqueue(**{k: v for k, v in {**payload, 'action': 'develop', 'issue_id': '1'}.items()
                     if k != 'confirm_run'})
    assert run_job(root, payload['request_id'], executor=lambda **kwargs: execute_issue(**flow))
    assert store.get(payload['request_id'])['result']['reason'] == 'issue_quality_failed'
    proposals = SetupProposals(root)
    values = proposals.list()
    assert len(values) == 1 and values[0]['kind'] == 'improvement'
    proposal = values[0]
    assert proposal['run_id'] == store.get(payload['request_id'])['result']['run_id']
    assert proposal['allowed_paths'] == list(flow['config'].allowed_paths)
    assert proposal['checks'] == json.loads(json.dumps([asdict(c) for c in flow['config'].checks]))
    assert len(OperatorProfiles(root).list()) == 1  # No automatic adoption.
    proposals.feedback(payload['profile_id'], payload['config_fingerprint'],
                       '1', proposal['run_id'],
                       store.get(payload['request_id'])['result']['session_id'])
    assert len(proposals.list()) == 1  # Repeated readback never duplicates suggestions.
    result = proposals.approve(proposal['id'], proposal['fingerprint'])
    _, config = OperatorProfiles(root).get(result['profile']['id'])
    assert replace(config, project_harness=None) == flow['config']
    assert config.project_harness.rules[-1].name == 'behavior-and-review'
    assert flow['implementer'].calls == flow['reviewer'].calls == 1


def test_feedback_must_match_exact_registered_scope(job_flow, flow):
    root, _, payload, _ = job_flow
    flow['reviewer'].must_fix = True
    result = execute_issue(**flow)
    with pytest.raises(StateConflict):
        SetupProposals(root).feedback(payload['profile_id'], payload['config_fingerprint'],
                                     '2', result['run_id'], result['session_id'])
    OperatorProfiles(root).revoke(payload['profile_id'])
    with pytest.raises(StatePermissionDenied):
        SetupProposals(root).feedback(payload['profile_id'], payload['config_fingerprint'],
                                     '1', result['run_id'], result['session_id'])


def test_setup_http_requires_operator_origin_strict_schema_and_explicit_approval(job_flow, flow):
    root, auth, _, _ = job_flow
    config = flow['config']
    inspect = {'root': str(config.root), 'repository': config.repository}
    payload = {**setup_args(flow), 'root': str(config.root),
               'checks': json.loads(json.dumps([asdict(c) for c in config.checks]))}
    payload['allowed_paths'] = list(config.allowed_paths)
    with TestClient(create_app(data_dir=root, operator=auth), base_url=ORIGIN) as client:
        assert client.post('/api/operator/setup/inspect', json=inspect,
                           headers=HEADERS).status_code == 401
        login(client, auth)
        result = client.post('/api/operator/setup/inspect', json=inspect, headers=HEADERS)
        assert result.status_code == 200 and result.json()['files'] == ['app.py']
        assert client.post('/api/operator/setup/inspect', json=inspect,
                           headers={**HEADERS, 'origin': 'https://evil.invalid'}).status_code == 403
        for change in ({'data_root': '/etc'}, {'selected_harness': []},
                       {'allowed_paths': ['AGENTS.md']}, {'allowed_paths': ['../other.py']},
                       {'checks': []}, {'provider': 'unapproved'}):
            result = client.post('/api/operator/setup/proposals', json={**payload, **change},
                                 headers=HEADERS)
            assert result.status_code in {422, 403}
        result = client.post('/api/operator/setup/proposals', json=payload, headers=HEADERS)
        assert result.status_code == 201
        proposal = result.json()
        url = '/api/operator/setup/proposals/' + proposal['id'] + '/approve'
        assert client.post(url, json={'fingerprint': proposal['fingerprint'], 'confirmed': False},
                           headers=HEADERS).status_code == 403
        assert client.post(url, json={'fingerprint': 'f' * 64, 'confirmed': True},
                           headers=HEADERS).status_code == 409
        applied = client.post(url, json={'fingerprint': proposal['fingerprint'], 'confirmed': True},
                              headers=HEADERS)
        assert applied.status_code == 200 and applied.json()['profile']['id']
        assert applied.headers['cache-control'] == 'no-store'
        assert flow['implementer'].calls == flow['scm'].writes == 0


@pytest.mark.parametrize('mode', ['success', 'empty', 'skip', 'failure', 'expected-failure'])
def test_unittest_preset_requires_actual_non_skipped_success(tmp_path, mode):
    import os
    import subprocess
    import sys

    from sf_factory.operator_setup import UNITTEST_COMMAND

    case = 'import unittest\nclass TestBehavior(unittest.TestCase):\n'
    if mode == 'skip':
        case += '    @unittest.skip("fixture")\n'
    if mode == 'expected-failure':
        case += '    @unittest.expectedFailure\n'
    case += ('    def test_behavior(self): self.assertEqual(1, '
             + ('2' if mode in {'failure', 'expected-failure'} else '1') + ')\n')
    if mode != 'empty':
        (tmp_path / 'test_behavior.py').write_text(case)
    before = sorted(p.name for p in tmp_path.iterdir())
    result = subprocess.run([sys.executable, *UNITTEST_COMMAND[1:]], cwd=tmp_path,
        env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}, capture_output=True, text=True,
        timeout=10, check=False)
    assert (result.returncode == 0) == (mode == 'success')
    if mode == 'success':
        assert result.stdout == 'SF_TESTS_PASSED\n'
    assert sorted(p.name for p in tmp_path.iterdir()) == before


def test_real_docker_web_setup_no_harness_to_draft(flow, monkeypatch):
    import os

    from sf_factory.docker_execution import run_offline_command
    from sf_factory.operator_setup import UNITTEST_COMMAND

    if not os.environ.get('SF_TEST_DOCKER_IMAGE'):
        pytest.skip('optional real Docker image not configured')
    assert os.environ['SF_TEST_DOCKER_IMAGE'] == flow['config'].image
    monkeypatch.setattr('sf_factory.issue_development.run_offline_command', run_offline_command)
    monkeypatch.setattr('sf_factory.workspace_check.run_offline_command', run_offline_command)
    root = flow['config'].root
    (root / 'AGENTS.md').unlink()
    (root / 'test_behavior.py').write_text(
        'import unittest\nfrom app import add\nclass TestAdd(unittest.TestCase):\n'
        '    def test_sum(self): self.assertEqual(add(2,3),5)\n')
    commit(root)
    flow['scm'].parent = git(root, 'rev-parse', 'HEAD')
    from sf_factory.behavioral_check import BehavioralCheck
    args = setup_args(flow)
    args['checks'] = (BehavioralCheck('unittest', UNITTEST_COMMAND, 'SF_TESTS_PASSED\n'),)
    store = SetupProposals(flow['factory'].root)
    value = store.initial(**args)
    approved = store.approve(value['id'], value['fingerprint'])
    profile_id = approved['profile']['id']
    _, config = OperatorProfiles(store.root).get(profile_id)
    assert config.project_harness and config.selected_harness == ()
    jobs = WebJobs(store.root)
    job, _ = jobs.enqueue(profile_id=profile_id, config_fingerprint=config.fingerprint,
        action='develop', issue_id='1', request_id='c' * 32, confirm_bedrock=True)
    assert run_job(store.root, job['id'], executor=lambda **kwargs:
                   execute_issue(**{**flow, 'config': config}))
    assert jobs.progress(job['id'])['pr_url'] == 'https://fixture.invalid/pr/7'
    assert flow['scm'].writes == 3
    assert not (root / 'AGENTS.md').exists() and git(root, 'status', '--porcelain') == ''


@pytest.mark.parametrize('kind', ['unittest', 'pytest', 'unknown'])
def test_test_framework_suggestion_is_static_and_framework_specific(flow, kind):
    from sf_factory.operator_setup import inspect_repository
    root = flow['config'].root
    text = {'unittest': 'import unittest\nclass Sum(unittest.TestCase):\n'
            '    def test_sum(self): self.assertEqual(1, 1)\n',
            'pytest': 'def test_sum(): assert 1 == 1\n',
            'unknown': 'raise RuntimeError("must not execute on host")\n'}[kind]
    (root / 'test_behavior.py').write_text(text)
    commit(root)
    data = inspect_repository(root, 'fixture/repo', flow['factory'].root)
    assert data['test_preset'] == (None if kind == 'unknown' else kind)
    assert (data['test_argv'] is not None) == (kind != 'unknown')


@pytest.mark.parametrize('mode', ['success', 'empty', 'skip', 'failure', 'xfail'])
def test_pytest_preset_rejects_empty_skipped_failed_and_xfail(tmp_path, mode):
    import os
    import subprocess
    import sys

    from sf_factory.operator_setup import PYTEST_COMMAND
    if mode != 'empty':
        code = ('import pytest\n' +
            ('@pytest.mark.skip(reason="fixture")\n' if mode == 'skip' else '') +
            ('@pytest.mark.xfail(reason="fixture")\n' if mode == 'xfail' else '') +
            'def test_behavior(): assert 1 == ' + ('2' if mode in {'failure', 'xfail'} else '1'))
        (tmp_path / 'test_behavior.py').write_text(code)
    result = subprocess.run([sys.executable, *PYTEST_COMMAND[1:]], cwd=tmp_path,
        env={**os.environ, 'PYTEST_ADDOPTS': '-k nonexistent'},
        capture_output=True, text=True, check=False, timeout=15)
    assert (result.returncode == 0) == (mode == 'success')
    if mode == 'success':
        assert result.stdout == 'SF_TESTS_PASSED\n'
    assert not (tmp_path / '.pytest_cache').exists()
    assert not (tmp_path / '__pycache__').exists()


def test_improvement_is_evaluated_with_unchanged_checks_before_next_pr(job_flow, flow):
    root, _, payload, _ = job_flow
    flow['reviewer'].must_fix = True
    result = execute_issue(**flow)
    proposals = SetupProposals(root)
    value = proposals.feedback(payload['profile_id'], payload['config_fingerprint'],
                               '1', result['run_id'], result['session_id'])
    approved = proposals.approve(value['id'], value['fingerprint'])
    _, improved = OperatorProfiles(root).get(approved['profile']['id'])
    assert improved.checks == flow['config'].checks
    assert improved.allowed_paths == flow['config'].allowed_paths
    flow['reviewer'].must_fix = False
    delivered = execute_issue(**{**flow, 'config': improved})
    assert delivered['status'] == 'completed' and flow['scm'].writes == 3
    assert delivered['run_id'] != result['run_id']
    assert result['session_id'] != delivered['session_id']
    assert flow['implementer'].calls == flow['reviewer'].calls == 2
    assert flow['factory'].show_run(delivered['run_id'])['harness_manifest'][
        'composition']['project_harness']['rules'][-1]['name'] == 'behavior-and-review'


@pytest.mark.parametrize('failure', ['model_auth', 'docker', 'review_auth'])
def test_infrastructure_failures_do_not_create_harness_learning(
        job_flow, flow, failure, monkeypatch):
    from sf_factory.docker_execution import DockerExecutionResult
    root, _, payload, _ = job_flow
    def unavailable(prompt):
        raise RuntimeError('simulated unavailable authentication')
    if failure == 'model_auth':
        flow['implementer'].generate = unavailable
    elif failure == 'review_auth':
        flow['reviewer'].generate = unavailable
    else:
        monkeypatch.setattr('sf_factory.workspace_check.run_offline_command',
            lambda **kwargs: DockerExecutionResult('unavailable', None, '', flow['config'].image,
                                                   True))
    result = execute_issue(**flow)
    assert result['status'] == 'stopped'
    proposals = SetupProposals(root)
    assert proposals.feedback(payload['profile_id'], payload['config_fingerprint'],
                              '1', result['run_id'], result['session_id']) is None
    assert proposals.list() == []


def test_setup_retry_reuses_proposal_and_installed_profile(flow):
    store = SetupProposals(flow['factory'].root)
    first = store.initial(**setup_args(flow))
    assert store.initial(**setup_args(flow))['id'] == first['id']
    receipt = store.approve(first['id'], first['fingerprint'])
    assert store.initial(**setup_args(flow)) == receipt
    assert len(store.list()) == len(OperatorProfiles(store.root).list()) == 1


def test_model_proposal_format_feedback_requires_a_received_response(job_flow, flow):
    root, _, payload, _ = job_flow
    flow['implementer'].invalid = True
    result = execute_issue(**flow)
    value = SetupProposals(root).feedback(payload['profile_id'], payload['config_fingerprint'],
                                         '1', result['run_id'], result['session_id'])
    assert value['project_harness']['rules'][-1]['name'] == 'proposal-format'


def test_clean_source_revision_change_invalidates_even_unchanged_harness(flow):
    store = SetupProposals(flow['factory'].root)
    value = store.initial(**setup_args(flow))
    (flow['config'].root / 'app.py').write_text('def add(a,b): return a+b\n')
    commit(flow['config'].root)
    with pytest.raises(StateConflict):
        store.approve(value['id'], value['fingerprint'])
    assert not OperatorProfiles(store.root).list()


def test_setup_can_choose_parent_issue_without_changing_selected_issue_contract(flow):
    store = SetupProposals(flow['factory'].root)
    value = store.initial(**setup_args(flow), issue='42')
    assert value['issue'] == '42'
    approved = store.approve(value['id'], value['fingerprint'])
    _, config = OperatorProfiles(store.root).get(approved['profile']['id'])
    assert config.issue == '42'
    assert config.allowed_paths == flow['config'].allowed_paths


def test_real_docker_failed_review_to_approved_improvement_to_draft(job_flow, flow, monkeypatch):
    import os

    from sf_factory.docker_execution import run_offline_command

    if not os.environ.get('SF_TEST_DOCKER_IMAGE'):
        pytest.skip('optional real Docker image not configured')
    assert os.environ['SF_TEST_DOCKER_IMAGE'] == flow['config'].image
    monkeypatch.setattr('sf_factory.issue_development.run_offline_command', run_offline_command)
    monkeypatch.setattr('sf_factory.workspace_check.run_offline_command', run_offline_command)
    test_improvement_is_evaluated_with_unchanged_checks_before_next_pr(job_flow, flow)


def test_same_failed_run_does_not_duplicate_learning_through_an_equivalent_profile(job_flow, flow):
    root, _, payload, _ = job_flow
    flow['implementer'].invalid = True
    result = execute_issue(**flow)
    store = SetupProposals(root)
    original = store.feedback(payload['profile_id'], payload['config_fingerprint'],
                              '1', result['run_id'], result['session_id'])
    copy = root.parent / 'equivalent.json'
    copy.write_text(json.dumps(asdict(flow['config']), default=str))
    alternate = OperatorProfiles(root).register(copy, 'Equivalent operator scope')
    repeated = store.feedback(alternate['id'], alternate['fingerprint'],
                              '1', result['run_id'], result['session_id'])
    assert repeated['id'] == original['id'] and len(store.list()) == 1


def test_improvement_preserves_project_when_adapter_canonicalizes_repository(job_flow, flow):
    from sf_factory.repository_contracts import RepositoryCapabilities
    from sf_factory.source_control import RepositoryInfo

    root, _, payload, _ = job_flow
    flow['config'] = replace(flow['config'], repository='Fixture/Repo')
    path = root.parent / 'operator.json'
    path.write_text(json.dumps(asdict(flow['config']), default=str))
    registered = OperatorProfiles(root).register(path, 'Canonical repository fixture')
    payload.update(profile_id=registered['id'], config_fingerprint=registered['fingerprint'])
    flow['scm'].describe_repository = lambda repository: RepositoryInfo(
        'fixture/repo', 'main', RepositoryCapabilities(True, True, True))
    test_improvement_is_evaluated_with_unchanged_checks_before_next_pr(job_flow, flow)
