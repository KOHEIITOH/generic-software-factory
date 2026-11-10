"""Real local Git materialization; external source API, model and delivery are simulated."""
import json
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_issue_development import flow as flow
from test_web_jobs import job_flow as job_flow
from test_web_jobs import login
from test_web_operator import HEADERS, ORIGIN

from sf_factory.collaboration_contracts import RevisionFile, RevisionSource
from sf_factory.issue_execution import execute_issue
from sf_factory.managed_repository import ManagedRepositories, execution_source
from sf_factory.operator_setup import SetupProposals, inspect_repository
from sf_factory.state_store import StateConflict
from sf_factory.web_api import create_app
from sf_factory.web_operator import OperatorProfiles


def source_for(flow):
    root = flow['config'].root
    return RevisionSource('fixture/repo', flow['scm'].parent, tuple(
        RevisionFile(path, '100644', (root / path).read_bytes())
        for path in ('AGENTS.md', 'app.py') if (root / path).exists()))


def adapter(flow):
    flow['scm'].read_revision = lambda repository, revision: source_for(flow)
    return flow['scm']


def test_acquire_then_setup_then_issue_to_draft_without_manual_path_or_clone(flow):
    scm = adapter(flow)
    store = ManagedRepositories(flow['factory'].root)
    value = store.acquire('fixture/repo', scm, lambda repo: 'https://github.com/' + repo + '.git')
    root = Path(value['root'])
    assert root != flow['config'].root and not root.is_relative_to(store.root)
    assert (root / 'app.py').read_bytes() == (flow['config'].root / 'app.py').read_bytes()
    assert value['local_revision'] != value['remote_revision']
    assert inspect_repository(root, 'fixture/repo', store.root)['files'] == ['app.py']
    assert store.acquire('fixture/repo', scm, lambda repo: 'unused') == value
    proposals = SetupProposals(store.root)
    proposal = proposals.initial(root=root, repository='fixture/repo', name='Managed fixture',
        provider='bedrock', image=flow['config'].image, allowed_paths=('app.py',),
        checks=flow['config'].checks)
    receipt = proposals.approve(proposal['id'], proposal['fingerprint'])
    _, config = OperatorProfiles(store.root).get(receipt['profile']['id'])
    result = execute_issue(**{**flow, 'config': config})
    assert result['status'] == 'completed' and flow['scm'].writes == 3
    assert result['requirement_sources']['revision'] == value['remote_revision']
    assert (root / 'app.py').read_text() == 'def add(a,b): return 0\n'


def test_modified_workspace_is_not_overwritten_or_executed(flow):
    scm = adapter(flow)
    store = ManagedRepositories(flow['factory'].root)
    value = store.acquire('fixture/repo', scm, lambda repo: 'https://github.com/' + repo + '.git')
    root = Path(value['root'])
    (root / 'app.py').write_text('modified locally')
    with pytest.raises(StateConflict):
        store.acquire('fixture/repo', scm, lambda repo: 'unused')
    with pytest.raises(StateConflict):
        execution_source(store.root, root, 'fixture/repo', scm)
    assert (root / 'app.py').read_text() == 'modified locally'


def test_recovery_after_intent_before_workspace_publication(flow, monkeypatch):
    import sf_factory.managed_repository as module
    scm = adapter(flow)
    store = ManagedRepositories(flow['factory'].root)
    original = module.os.rename
    def crash(*args, **kwargs):
        if Path(args[1]).parent == store.workspaces:
            raise KeyboardInterrupt('fixture before workspace publication')
        return original(*args, **kwargs)
    monkeypatch.setattr(module.os, 'rename', crash)
    with pytest.raises(KeyboardInterrupt):
        store.acquire('fixture/repo', scm, lambda repo: 'https://github.com/' + repo + '.git')
    monkeypatch.setattr(module.os, 'rename', original)
    result = store.acquire('fixture/repo', scm, lambda repo: 'https://github.com/' + repo + '.git')
    assert Path(result['root']).is_dir()
    assert len(list(store.directory.iterdir())) == 2  # One metadata directory plus lock.


def test_git_global_hooks_filters_and_redirects_are_not_used(flow, monkeypatch, tmp_path):
    canary = tmp_path / 'executed'
    config = tmp_path / 'host-gitconfig'
    config.write_text('[core]\n hooksPath = /untrusted\n[filter "attack"]\n'
                      ' clean = touch ' + str(canary) + '\n required = true\n')
    monkeypatch.setenv('GIT_CONFIG_GLOBAL', str(config))
    monkeypatch.setenv('GIT_DIR', str(tmp_path / 'wrong.git'))
    scm = adapter(flow)
    original = source_for(flow)
    source = replace(original, files=(*original.files,
        RevisionFile('.gitattributes', '100644', b'*.py filter=attack\n')))
    scm.read_revision = lambda repository, revision: source
    value = ManagedRepositories(flow['factory'].root).acquire('fixture/repo', scm,
        lambda repo: 'https://github.com/' + repo + '.git')
    assert Path(value['root']).is_dir() and not canary.exists()


@pytest.mark.parametrize('file', [RevisionFile('../escape.py', '100644', b'x'),
    RevisionFile('link.py', '120000', b'/etc/passwd'),
    RevisionFile('.git/config', '100644', b'credential leak')])
def test_unsafe_remote_sources_never_publish_a_workspace(flow, file):
    scm = adapter(flow)
    scm.read_revision = lambda repository, revision: replace(source_for(flow), files=(file,))
    store = ManagedRepositories(flow['factory'].root)
    with pytest.raises(ValueError):
        store.acquire('fixture/repo', scm, lambda repo: 'unused')
    assert not any(store.workspaces.iterdir())


def test_acquisition_http_requires_operator_and_never_accepts_urls_or_paths(job_flow, flow,
                                                                          monkeypatch):
    root, auth, _, _ = job_flow
    scm = adapter(flow)
    calls = []
    def source():
        calls.append(True)
        return scm
    monkeypatch.setattr('sf_factory.integration_defaults.repository_source', source)
    with TestClient(create_app(data_dir=root, operator=auth), base_url=ORIGIN) as client:
        url = '/api/operator/setup/acquire'
        assert client.post(url, json={'repository': 'fixture/repo'},
                           headers=HEADERS).status_code == 401
        assert calls == []
        login(client, auth)
        assert client.post(url, json={'repository': 'fixture/repo', 'root': '/etc'},
                           headers=HEADERS).status_code == 422
        assert client.post(url, json={'repository': 'fixture/repo'},
                           headers={**HEADERS, 'origin': 'https://evil.invalid'}).status_code == 403
        result = client.post(url, json={'repository': 'fixture/repo'}, headers=HEADERS)
        assert result.status_code == 200
        assert result.json()['managed'] and result.json()['files'] == ['app.py']
        assert 'token' not in json.dumps(result.json())
        assert flow['scm'].writes == flow['implementer'].calls == 0


def test_source_failures_have_safe_codes_in_http_and_terminal(job_flow, monkeypatch, caplog):
    from urllib.error import HTTPError

    from sf_factory.source_control import SourceControlError

    root, auth, _, _ = job_flow
    failure = SourceControlError('access_denied', 'private token=secret')
    failure.__cause__ = HTTPError('https://private.invalid', 401, 'secret', {}, None)
    def fail(*args, **kwargs):
        raise failure
    monkeypatch.setattr('sf_factory.integration_defaults.repository_source', fail)
    monkeypatch.setattr('sf_factory.integration_defaults.repository_choices', fail)
    with TestClient(create_app(data_dir=root, operator=auth), base_url=ORIGIN) as client:
        login(client, auth)
        for response in (client.get('/api/operator/setup/repositories', headers=HEADERS),
                         client.post('/api/operator/setup/acquire',
                            json={'repository': 'fixture/repo'}, headers=HEADERS)):
            assert response.status_code == 502
            assert response.json() == {'detail': {'code': 'scm_credentials_rejected'}}
    assert 'scm_credentials_rejected upstream_status=401' in caplog.text
    assert 'private' not in caplog.text and 'secret' not in caplog.text


def test_refreshed_managed_revision_preserves_issue_project_membership(flow):
    scm = adapter(flow)
    store = ManagedRepositories(flow['factory'].root)
    first = store.acquire('fixture/repo', scm, lambda repo: 'https://github.com/' + repo + '.git')
    config = replace(flow['config'], root=Path(first['root']))
    flow['reviewer'].must_fix = True
    stopped = execute_issue(**{**flow, 'config': config})
    assert stopped['status'] == 'stopped'
    scm.parent = 'd' * 40
    second = store.acquire('fixture/repo', scm, lambda repo: 'https://github.com/' + repo + '.git')
    assert second['root'] != first['root']
    flow['reviewer'].must_fix = False
    delivered = execute_issue(**{**flow, 'config': replace(config, root=Path(second['root']))})
    assert delivered['status'] == 'completed'
    assert flow['scm'].writes == 3


def test_execution_uses_new_remote_code_without_mutating_approved_local_baseline(flow):
    scm = adapter(flow)
    store = ManagedRepositories(flow['factory'].root)
    value = store.acquire('fixture/repo', scm, lambda repo: 'https://github.com/' + repo + '.git')
    config = replace(flow['config'], root=Path(value['root']))
    scm.parent = 'c' * 40
    result = execute_issue(**{**flow, 'config': config})
    assert result['status'] == 'completed'
    assert result['requirement_sources']['revision'] == 'c' * 40
    assert Path(value['root']).exists()


def test_real_docker_managed_repository_to_draft(flow, monkeypatch):
    import os

    from sf_factory.docker_execution import run_offline_command

    if not os.environ.get('SF_TEST_DOCKER_IMAGE'):
        pytest.skip('optional real Docker image not configured')
    assert os.environ['SF_TEST_DOCKER_IMAGE'] == flow['config'].image
    monkeypatch.setattr('sf_factory.issue_development.run_offline_command', run_offline_command)
    monkeypatch.setattr('sf_factory.workspace_check.run_offline_command', run_offline_command)
    from test_harness_runs import commit, git
    (flow['config'].root / 'AGENTS.md').unlink()
    commit(flow['config'].root)
    flow['scm'].parent = git(flow['config'].root, 'rev-parse', 'HEAD')
    test_acquire_then_setup_then_issue_to_draft_without_manual_path_or_clone(flow)


def test_catalog_requires_operator_and_filters_response_to_safe_choices(job_flow, monkeypatch):
    from sf_factory.repository_contracts import RepositoryCapabilities
    from sf_factory.source_control import RepositoryInfo
    root, auth, _, _ = job_flow
    calls = []
    def catalog(cursor):
        calls.append(cursor)
        return [RepositoryInfo('fixture/repo', 'main',
                               RepositoryCapabilities(True, True, True))], 'page-2'
    monkeypatch.setattr('sf_factory.integration_defaults.repository_choices', catalog)
    with TestClient(create_app(data_dir=root, operator=auth), base_url=ORIGIN) as client:
        url = '/api/operator/setup/repositories'
        assert client.get(url, headers=HEADERS).status_code == 401
        assert calls == []
        login(client, auth)
        result = client.get(url + '?cursor=page-1', headers=HEADERS)
        assert result.status_code == 200 and calls == ['page-1']
        assert result.json() == {'repositories': [{'repository': 'fixture/repo',
            'can_push': True}], 'next_cursor': 'page-2'}
        assert client.get(url + '?cursor=' + 'x' * 513, headers=HEADERS).status_code == 422


def test_changed_remote_harness_requires_review_before_any_inference(flow):
    scm = adapter(flow)
    store = ManagedRepositories(flow['factory'].root)
    value = store.acquire('fixture/repo', scm, lambda repo: 'https://github.com/' + repo + '.git')
    source = source_for(flow)
    scm.read_revision = lambda repository, revision: replace(source, files=(
        RevisionFile('AGENTS.md', '100644', b'Changed policy without approval'), source.files[1]))
    result = execute_issue(**{**flow, 'config': replace(flow['config'], root=Path(value['root']))})
    assert result['reason'] == 'managed_harness_review_required'
    assert result['status'] == 'waiting'
    assert flow['implementer'].calls == flow['scm'].writes == 0
    assert (Path(value['root']) / 'AGENTS.md').read_bytes() == source.files[0].content


def test_existing_local_issue_can_adopt_managed_sources_without_project_reassignment(flow):
    flow['reviewer'].must_fix = True
    assert execute_issue(**flow)['status'] == 'stopped'
    scm = adapter(flow)
    value = ManagedRepositories(flow['factory'].root).acquire('fixture/repo', scm,
        lambda repo: 'https://github.com/' + repo + '.git')
    flow['reviewer'].must_fix = False
    result = execute_issue(**{**flow, 'config': replace(flow['config'], root=Path(value['root']))})
    assert result['status'] == 'completed' and scm.writes == 3


def test_managed_adoption_does_not_bypass_explicit_shared_project(flow):
    from sf_factory.project_harness import ProjectHarness, ProjectRule

    flow['reviewer'].must_fix = True
    shared = replace(flow['config'], project_harness=ProjectHarness(
        'shared-project', (ProjectRule('quality', 'Require the shared project policy.'),)))
    assert execute_issue(**{**flow, 'config': shared})['status'] == 'stopped'
    scm = adapter(flow)
    value = ManagedRepositories(flow['factory'].root).acquire('fixture/repo', scm,
        lambda repo: 'https://github.com/' + repo + '.git')
    flow['reviewer'].must_fix = False
    result = execute_issue(**{**flow, 'config': replace(flow['config'], root=Path(value['root']))})
    assert result['status'] == 'waiting' and scm.writes == 0
    assert flow['implementer'].calls == 1
