"""Diagnostics report known/unknown facts without inference or external mutation."""
import json
from dataclasses import asdict
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from test_issue_development import flow as flow
from test_web_operator import HEADERS, ORIGIN

from sf_factory.model_provider_status import BedrockConfiguration
from sf_factory.operator_diagnostics import diagnose_profile
from sf_factory.web_api import create_app
from sf_factory.web_operator import OperatorProfiles, WebOperator


@pytest.fixture
def diagnostic_flow(flow, monkeypatch):
    root = flow['factory'].root
    path = root.parent / 'diagnostic.json'
    path.write_text(json.dumps(asdict(flow['config']), default=str))
    profile = OperatorProfiles(root).register(path, 'Diagnostic fixture')
    monkeypatch.setattr('sf_factory.operator_diagnostics._revision', lambda p: 'a' * 40)
    monkeypatch.setattr('sf_factory.operator_diagnostics.repository_binding',
                        lambda: SimpleNamespace(
        verify=lambda **k: k['local_path']))
    monkeypatch.setattr('sf_factory.operator_diagnostics.bedrock_configuration', lambda:
        BedrockConfiguration('private-model', 'private-region', True))
    monkeypatch.setattr('sf_factory.operator_diagnostics.docker_execution.resource_limits_available',
                        lambda: True)
    monkeypatch.setattr('sf_factory.operator_diagnostics.docker_execution._docker', lambda *a, **k:
                        SimpleNamespace(returncode=0, stdout='sha256:' + 'a' * 64))
    monkeypatch.setattr('sf_factory.operator_diagnostics.credential_status', lambda:
                        {'configured': True})
    return root, profile


def test_local_diagnostics_never_contact_scm_or_infer_and_keep_auth_unknown(
        diagnostic_flow, monkeypatch):
    root, profile = diagnostic_flow
    monkeypatch.setattr('sf_factory.operator_diagnostics.source_control', lambda:
                        pytest.fail('local checks must not contact SCM'))
    result = diagnose_profile(root, profile['id'], profile['fingerprint'])
    assert result['can_attempt'] and result['inference_invoked'] is False
    assert {r['id']: r['status'] for r in result['checks']}['model_authorization'] == 'unknown'
    assert next(r for r in result['checks'] if r['id'] == 'issue_pr_write')['status'] == 'unknown'
    assert 'private-model' not in json.dumps(result) and 'private-region' not in json.dumps(result)


def test_remote_diagnostic_only_uses_repository_read_contract(diagnostic_flow, monkeypatch):
    root, profile = diagnostic_flow
    calls = []
    def describe(repo):
        calls.append(repo)
        return SimpleNamespace(capabilities=SimpleNamespace(read=True, write=False))
    monkeypatch.setattr('sf_factory.operator_diagnostics.source_control', lambda:
                        SimpleNamespace(describe_repository=describe))
    result = diagnose_profile(root, profile['id'], profile['fingerprint'], check_remote=True)
    assert calls == ['fixture/repo'] and result['can_attempt'] is False
    assert next(r for r in result['checks'] if r['id'] == 'repository_push')['status'] == 'blocked'


def test_probe_errors_and_configuration_changes_do_not_expose_sdk_or_paths(
        diagnostic_flow, monkeypatch):
    root, profile = diagnostic_flow
    def fail(*a, **k):
        raise RuntimeError('PRIVATE_TOKEN /private/config/path')
    monkeypatch.setattr('sf_factory.operator_diagnostics.source_control', fail)
    result = diagnose_profile(root, profile['id'], profile['fingerprint'], check_remote=True)
    assert 'PRIVATE_TOKEN' not in json.dumps(result)
    assert diagnose_profile(root, profile['id'], 'f' * 64)['can_attempt'] is False
    assert '/private/' not in json.dumps(result)


def test_diagnostics_are_operator_authenticated_and_allow_no_path(diagnostic_flow):
    root, profile = diagnostic_flow
    auth = WebOperator(ORIGIN)
    route = '/api/operator/profiles/' + profile['id'] + '/diagnostics'
    with TestClient(create_app(data_dir=root, operator=auth), base_url=ORIGIN) as client:
        body = {'config_fingerprint': profile['fingerprint']}
        assert client.post(route, json=body, headers=HEADERS).status_code == 401
        client.post('/api/operator/session', headers={**HEADERS,
                    'authorization': 'Bearer ' + auth.token})
        assert client.post(route, json=body, headers=HEADERS).status_code == 200
        assert client.post(route, json={**body, 'path': '/etc/passwd'},
                           headers=HEADERS).status_code == 422
