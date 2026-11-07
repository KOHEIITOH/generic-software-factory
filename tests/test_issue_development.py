"""Real Git/File/evidence path, with explicitly simulated model and SCM services."""
import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path

import pytest
from test_harness_runs import commit, git

from sf_factory.behavioral_check import BehavioralCheck
from sf_factory.development_config import DevelopmentConfig
from sf_factory.docker_execution import DockerExecutionResult
from sf_factory.file_dashboard import FileDashboardFactory
from sf_factory.issue_development import DevelopmentStopped, develop_issue
from sf_factory.model_provider import ModelResponse
from sf_factory.repository_contracts import RepositoryCapabilities
from sf_factory.source_control import PreparedCommit, PullRequestReference, RepositoryInfo
from sf_factory.task_sources import ExternalIssue

IMAGE = 'python@sha256:09a17cad02668ae61ece136b4fd36ac3849e14f670ebedb637ea3e15580525bc'


class Binding:
    def verify(self, *, provider, instance, repository, local_path):
        assert provider == 'fixture-issues' and instance == repository == 'fixture/repo'
        return local_path


class Source:
    def fetch_issue(self, external_id):
        return ExternalIssue('fixture-issues', 'fixture/repo', external_id,
                             'Implement add(a,b) in app.py to return their sum.',
                             'https://fixture.invalid/issues/' + external_id)


class Model:
    def __init__(self, identity):
        self.identity = identity
        self.calls = 0
        self.must_fix = False
        self.invalid = False

    def generate(self, prompt):
        self.calls += 1
        data = json.loads(prompt.split('\n', 1)[1])
        if 'scope' in data:
            report = {'schema_version': 1, **{k: v for k, v in data['scope'].items()
                                             if k != 'allowed_paths'}, 'changes': [
                {'path': 'app.py', 'before_sha256': hashlib.sha256(b'def add(a,b): return 0\n')
                    .hexdigest(), 'content': 'def add(a,b): return a+b\n'}]}
        else:
            report = {'schema_version': 1, **{k: data[k] for k in
                ('run_id', 'revision', 'bundle_hash', 'diff_sha256')}, 'status': 'completed',
                'complete': True, 'truncated': False, 'reviewed_paths': ['app.py'],
                'findings': []}
            if self.must_fix:
                report['findings'] = [{'severity': 'must-fix', 'path': 'app.py', 'line': 1,
                                      'summary': 'fixture finding', 'evidence': 'fixture evidence'}]
        return ModelResponse('fixture-model', 'fixture', 'bad json' if self.invalid else
                             json.dumps(report), session_id=self.identity)


class SCM:
    def __init__(self, parent):
        self.parent, self.revision, self.pr = parent, None, None
        self.writes = 0
        self.fail_pr = False

    def describe_repository(self, repository):
        return RepositoryInfo(repository, 'main', RepositoryCapabilities(True, True, True))

    def branch_revision(self, repository, branch):
        return self.parent

    def prepare_commit(self, repository, **kwargs):
        self.writes += 1
        assert kwargs['parent_revision'] == self.parent
        assert kwargs['changes'][0].after == b'def add(a,b): return a+b\n'
        return PreparedCommit('e' * 40, 'f' * 40, self.parent)

    def ensure_branch(self, repository, branch, revision):
        self.writes += 1
        self.revision = revision

    def verified_branch_revision(self, repository, branch):
        return self.revision

    def find_draft_pull_request(self, repository, **kwargs):
        return self.pr

    def create_draft_pull_request(self, repository, **kwargs):
        self.writes += 1
        assert 'Issue: https://fixture.invalid/issues/1' in kwargs['body']
        self.pr = PullRequestReference('7', 'https://fixture.invalid/pr/7')
        if self.fail_pr:
            raise TimeoutError('fixture unknown outcome')
        return self.pr


def fake_execution(**kwargs):
    if 'input_bytes' not in kwargs:
        return DockerExecutionResult('succeeded', 0, 'SF_EXECUTION_READY\n', IMAGE, True)
    raw = kwargs['input_bytes']
    payload = json.loads(raw)
    app = next(f for f in payload['files'] if f['path'] == 'app.py')
    assert app['sha256'] == hashlib.sha256(b'def add(a,b): return a+b\n').hexdigest()
    return DockerExecutionResult('succeeded', 0, json.dumps({'schema_version': 1,
        'request_sha256': hashlib.sha256(raw).hexdigest(), 'status': 'succeeded',
        'exit_code': 0, 'source_unchanged': True, 'output': '5\n'}), IMAGE, True)


@pytest.fixture
def flow(tmp_path, monkeypatch):
    global_config = tmp_path / 'gitconfig'
    global_config.write_text('')
    monkeypatch.setenv('GIT_CONFIG_GLOBAL', str(global_config))
    monkeypatch.setenv('GIT_CONFIG_NOSYSTEM', '1')
    root = tmp_path / 'repo'
    root.mkdir()
    git(root, 'init', '-q')
    (root / 'AGENTS.md').write_text('Implement the Issue. Preserve approved tests and scope.')
    (root / 'app.py').write_text('def add(a,b): return 0\n')
    commit(root)
    factory = FileDashboardFactory(tmp_path / 'data', repository_binding=Binding())
    config = DevelopmentConfig('fixture/repo', '1', root, factory.root, 'bedrock', IMAGE,
        ('app.py',), ('AGENTS.md',), (),
        (BehavioralCheck('addition', ('python', '-c',
                                      'from app import add; print(add(2,3))'), '5\n'),))
    monkeypatch.setattr('sf_factory.issue_development.run_offline_command', fake_execution)
    monkeypatch.setattr('sf_factory.workspace_check.run_offline_command', fake_execution)
    return dict(factory=factory, config=config, source=Source(),
                scm=SCM(git(root, 'rev-parse', 'HEAD')),
                implementer=Model('implementation-request'),
                reviewer=Model('review-request'), confirmed=True)


def test_issue_candidate_check_review_to_draft_uses_real_file_state_without_host_edit(flow):
    result = develop_issue(**flow)
    assert result['status'] == 'draft_pr_created'
    assert result['pull_request']['external_id'] == '7'
    assert flow['scm'].writes == 3
    assert flow['implementer'].calls == flow['reviewer'].calls == 1
    assert (flow['config'].root / 'app.py').read_text() == 'def add(a,b): return 0\n'
    assert git(flow['config'].root, 'status', '--porcelain') == ''
    assert not list(flow['factory'].root.rglob('*.sqlite3'))
    artifact = json.loads((flow['factory'].root / 'development-v1' / result['run_id'] /
                          'state.json').read_text())
    assert artifact['phase'] == 'delivered'
    assert artifact['issue']['external_id'] == '1'
    assert artifact['implementer'] != artifact['reviewer']


@pytest.mark.parametrize('failure', ['model', 'review', 'same_session', 'tests'])
def test_untrusted_or_incomplete_results_never_reach_scm_write(flow, failure, monkeypatch):
    if failure == 'model':
        flow['implementer'].invalid = True
    elif failure == 'review':
        flow['reviewer'].must_fix = True
    elif failure == 'same_session':
        flow['reviewer'].identity = flow['implementer'].identity
    else:
        def unavailable(**kwargs):
            return DockerExecutionResult('unavailable', None, '', IMAGE, True)
        monkeypatch.setattr('sf_factory.workspace_check.run_offline_command', unavailable)
    with pytest.raises(DevelopmentStopped) as stopped:
        develop_issue(**flow)
    assert len(stopped.value.run_id) == 32
    assert flow['scm'].writes == 0


def test_unavailable_preflight_never_starts_inference_or_prepares_run(flow, monkeypatch):
    monkeypatch.setattr('sf_factory.issue_development.run_offline_command',
        lambda **kw: DockerExecutionResult('unavailable', None, '', IMAGE, True))
    with pytest.raises(RuntimeError, match='no inference'):
        develop_issue(**flow)
    assert flow['implementer'].calls == 0
    assert flow['factory'].list_runs() == []


def test_unconfirmed_operator_never_starts_inference(flow):
    with pytest.raises(PermissionError):
        develop_issue(**{**flow, 'confirmed': False})
    assert flow['implementer'].calls == flow['scm'].writes == 0


def test_resume_reconciles_exact_pr_without_inference_or_duplicate_writes(flow):
    flow['scm'].fail_pr = True
    with pytest.raises(DevelopmentStopped) as stopped:
        develop_issue(**flow)
    writes = flow['scm'].writes
    flow['scm'].fail_pr = False
    result = develop_issue(**flow, resume=stopped.value.run_id)
    assert result['status'] == 'draft_pr_created'
    assert flow['scm'].writes == writes == 3
    assert flow['implementer'].calls == flow['reviewer'].calls == 1


def test_resume_does_not_accept_changed_execution_scope(flow):
    result = develop_issue(**flow)
    with pytest.raises(PermissionError):
        develop_issue(**{**flow, 'config': replace(flow['config'], allowed_paths=('other.py',))},
                      resume=result['run_id'])


def test_real_local_issue_workflow_with_offline_docker(flow, monkeypatch):
    image = os.environ.get('SF_TEST_DOCKER_IMAGE')
    if not image:
        pytest.skip('optional real Docker execution image not configured')
    from sf_factory.docker_execution import run_offline_command
    monkeypatch.setattr('sf_factory.issue_development.run_offline_command', run_offline_command)
    monkeypatch.setattr('sf_factory.workspace_check.run_offline_command', run_offline_command)
    flow['config'] = replace(flow['config'], image=image)
    result = develop_issue(**flow)
    assert result['status'] == 'draft_pr_created'
    assert flow['scm'].writes == 3
    assert Path(flow['config'].root / 'app.py').read_text() == 'def add(a,b): return 0\n'


def test_cli_without_confirmation_does_not_even_load_configuration(monkeypatch, capsys):
    from sf_factory.issue_development_cli import run_local_development
    def forbidden(*args, **kwargs):
        pytest.fail('unconfirmed request must not initialize anything')
    monkeypatch.setattr('sf_factory.issue_development_cli.load_config', forbidden)
    assert run_local_development(config_path=Path('/unused'), confirmed=False,
                                 confirm_bedrock=False, resume=None) == 2
    assert json.loads(capsys.readouterr().out)['status'] == 'confirmation_required'


def test_bedrock_requires_explicit_local_invocation_consent(flow, monkeypatch, capsys):
    from sf_factory.issue_development_cli import run_local_development
    monkeypatch.setattr('sf_factory.issue_development_cli.load_config', lambda path: flow['config'])
    assert run_local_development(config_path=Path('/unused'), confirmed=True,
                                 confirm_bedrock=False, resume=None) == 2
    assert json.loads(capsys.readouterr().out)['required'] == '--confirm-bedrock'
    assert flow['factory'].list_runs() == []


def test_execution_config_cannot_be_taken_from_untrusted_repository(flow):
    from dataclasses import asdict

    from sf_factory.issue_development_cli import load_config
    path = flow['config'].root / 'operator.json'
    path.write_text(json.dumps(asdict(flow['config']), default=str))
    with pytest.raises(PermissionError):
        load_config(path)


@pytest.mark.parametrize('field,value', [('image', 'python:latest'),
    ('allowed_paths', ['AGENTS.md']),
    ('checks', []), ('data_root', '/'), ('provider', 'host-cli')])
def test_unreviewed_execution_scope_is_rejected_before_inference(flow, field, value):
    from dataclasses import asdict
    document = json.loads(json.dumps(asdict(flow['config']), default=str))
    document[field] = value
    with pytest.raises((ValueError, TypeError)):
        DevelopmentConfig.from_document(document)


def test_unresolved_delivery_blocks_a_new_inference_attempt(flow):
    flow['scm'].fail_pr = True
    with pytest.raises(DevelopmentStopped) as stopped:
        develop_issue(**flow)
    with pytest.raises(DevelopmentStopped, match='resume the same Run') as blocked:
        develop_issue(**flow)
    assert blocked.value.run_id == stopped.value.run_id
    assert flow['implementer'].calls == flow['reviewer'].calls == 1


def test_snapshot_tamper_after_checks_never_reaches_delivery(flow, monkeypatch):
    from sf_factory.behavioral_check import collect_behavioral_check
    from sf_factory.source_snapshot import SourceSnapshotService
    def observe(**kwargs):
        result = collect_behavioral_check(**kwargs)
        service = SourceSnapshotService(flow['factory'])
        descriptor = service.verify(kwargs['scope'].run_id)
        (service.storage / descriptor['snapshot_id'] / 'payload/app.py').write_text('tampered')
        return result
    monkeypatch.setattr('sf_factory.issue_development.collect_behavioral_check', observe)
    with pytest.raises(DevelopmentStopped):
        develop_issue(**flow)
    assert flow['scm'].writes == 0


@pytest.mark.parametrize('mutation', ['future_schema', 'broader_scope', 'other_issue'])
def test_resume_rejects_modified_artifact_identity(flow, mutation):
    from sf_factory.state_store import StateUnavailable
    result = develop_issue(**flow)
    path = flow['factory'].root / 'development-v1' / result['run_id'] / 'state.json'
    value = json.loads(path.read_text())
    if mutation == 'future_schema':
        value['schema_version'] = 999
    elif mutation == 'broader_scope':
        value['scope']['allowed_paths'].append('other.py')
    else:
        value['issue']['external_id'] = '2'
    path.write_text(json.dumps(value))
    with pytest.raises((DevelopmentStopped, StateUnavailable)):
        develop_issue(**flow, resume=result['run_id'])
    assert flow['scm'].writes == 3


def test_execution_config_writable_by_other_users_is_rejected(flow):
    from dataclasses import asdict

    from sf_factory.issue_development_cli import load_config
    path = flow['config'].root.parent / 'operator.json'
    path.write_text(json.dumps(asdict(flow['config']), default=str))
    path.chmod(0o666)
    with pytest.raises(PermissionError, match='not writable'):
        load_config(path)
