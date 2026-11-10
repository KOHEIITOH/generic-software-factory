"""Node setup stays static until approval; dependency checks run offline in Docker."""
import hashlib
import json
import os
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_harness_runs import commit, git
from test_issue_development import SCM, Model
from test_issue_development import flow as flow
from test_web_jobs import job_flow as job_flow
from test_web_jobs import login
from test_web_operator import HEADERS, ORIGIN

from sf_factory.behavioral_check import BehavioralCheck
from sf_factory.change_proposal import ProposalScope, parse_change_proposal
from sf_factory.issue_execution import execute_issue
from sf_factory.model_provider import ModelResponse
from sf_factory.node_setup import DOCKERFILE, NODE_IMAGE, node_plan, prepare_image
from sf_factory.operator_setup import SetupProposals, inspect_repository
from sf_factory.source_control import PreparedCommit
from sf_factory.task_sources import ExternalIssue
from sf_factory.web_api import create_app
from sf_factory.web_operator import OperatorProfiles
from sf_factory.workspace_check import run_candidate_check

FIXTURE = Path(__file__).parent / 'fixtures/node-project'
BAD = (FIXTURE / 'src/add.ts').read_bytes()
GOOD = b'export function add(a: number, b: number): number { return a + b; }\n'


def node_repository(flow):
    root = flow['config'].root
    (root / 'app.py').unlink()
    shutil.copytree(FIXTURE, root, dirs_exist_ok=True)
    git(root, 'remote', 'add', 'origin', 'https://github.com/fixture/repo.git')
    commit(root)
    return root


def inspect(flow):
    return inspect_repository(flow['config'].root, 'fixture/repo', flow['factory'].root)


def test_node_detection_offers_real_scripts_and_never_python_image_or_install(flow, monkeypatch):
    root = node_repository(flow)
    monkeypatch.setattr('sf_factory.node_setup.subprocess.run',
                        lambda *a, **k: pytest.fail('static inspection must not build'))
    # _git uses Popen; no import or execution of the repository/package scripts.
    plan = node_plan(root, ['package.json', 'package-lock.json'], flow['factory'].root)
    assert plan and plan['available'] and not plan['image']
    assert [s['kind'] for s in plan['scripts']] == ['vitest', 'typecheck', 'lint']
    assert all(c['argv'][:4] == ['python', '-I', '-B', '-c'] for c in plan['checks'])
    assert '--ignore-scripts' in DOCKERFILE and 'COPY . ' not in DOCKERFILE
    assert '@sha256:' in NODE_IMAGE


@pytest.mark.parametrize('case', ['missing_lock', 'external_url', 'local_link', 'traversal',
                                  'bad_integrity', 'workspace', 'unknown_test'])
def test_unsupported_dependencies_or_scripts_are_explained_not_run(flow, case):
    root = node_repository(flow)
    lock = json.loads((root / 'package-lock.json').read_text())
    package = json.loads((root / 'package.json').read_text())
    entry = next(v for k, v in lock['packages'].items() if k)
    if case == 'missing_lock':
        (root / 'package-lock.json').unlink()
    elif case == 'external_url':
        entry['resolved'] = 'https://private.invalid/package.tgz?token=private'
    elif case == 'local_link':
        entry['link'] = True
    elif case == 'traversal':
        lock['packages']['node_modules/../../escape'] = entry
    elif case == 'bad_integrity':
        entry.pop('integrity')
    elif case == 'workspace':
        package['workspaces'] = ['*']
    else:
        package['scripts']['test'] = 'node scripts/arbitrary.js'
    if case != 'missing_lock':
        (root / 'package-lock.json').write_text(json.dumps(lock))
    (root / 'package.json').write_text(json.dumps(package))
    commit(root)
    data = inspect(flow)
    assert data['node']['available'] is False and data['image'] == ''
    assert 'private' not in data['node']['reason']


def test_image_http_requires_exact_plan_approval_and_has_no_caller_build_inputs(job_flow, flow,
                                                                             monkeypatch):
    root = node_repository(flow)
    data_root, auth, _, _ = job_flow
    calls = []
    monkeypatch.setattr('sf_factory.node_setup.prepare_image',
                        lambda *args: calls.append(args) or 'sha256:' + 'e' * 64)
    with TestClient(create_app(data_dir=data_root, operator=auth), base_url=ORIGIN) as client:
        url = '/api/operator/setup/node-image'
        data = inspect_repository(root, 'fixture/repo', data_root)
        payload = {'root': str(root), 'repository': 'fixture/repo',
                   'fingerprint': data['node']['fingerprint'], 'confirmed': True}
        assert client.post(url, json=payload, headers=HEADERS).status_code == 401
        login(client, auth)
        assert client.post(url, json={**payload, 'confirmed': False},
                           headers=HEADERS).status_code == 403
        assert client.post(url, json={**payload, 'fingerprint': 'f' * 64},
                           headers=HEADERS).status_code == 409
        assert client.post(url, json={**payload, 'dockerfile': 'evil'},
                           headers=HEADERS).status_code == 422
        assert calls == []
        assert client.post(url, json=payload, headers=HEADERS).status_code == 200
        assert len(calls) == 1


def test_node_config_freezes_lock_and_uses_multiple_reviewed_checks(flow):
    root = node_repository(flow)
    data = inspect(flow)
    checks = tuple(BehavioralCheck(c['id'], tuple(c['argv']), c['stdout'])
                   for c in data['checks'])
    store = SetupProposals(flow['factory'].root)
    proposal = store.initial(root=root, repository='fixture/repo', name='Node',
        provider='bedrock', image='sha256:' + 'e' * 64, allowed_paths=('src/add.ts',),
        checks=checks)
    receipt = store.approve(proposal['id'], proposal['fingerprint'])
    _, config = OperatorProfiles(store.root).get(receipt['profile']['id'])
    assert dict(config.context_hashes) == data['node']['hashes']
    assert len(config.checks) == 3
    with (root / 'package-lock.json').open('a') as stream:
        stream.write('\n')
    commit(root)
    flow['scm'].parent = git(root, 'rev-parse', 'HEAD')
    result = execute_issue(**{**flow, 'config': config})
    assert result['status'] != 'completed'
    assert flow['implementer'].calls == flow['scm'].writes == 0


class NodeModel(Model):
    def generate(self, prompt):
        self.calls += 1
        data = json.loads(prompt.split('\n', 1)[1])
        if 'scope' in data:
            report = {'schema_version': 1, **{k: v for k, v in data['scope'].items()
                                             if k != 'allowed_paths'}, 'changes': [{
                'path': 'src/add.ts', 'before_sha256': hashlib.sha256(BAD).hexdigest(),
                'content': GOOD.decode()}]}
        else:
            report = {'schema_version': 1, **{k: data[k] for k in
                ('run_id', 'revision', 'bundle_hash', 'diff_sha256')}, 'status': 'completed',
                'complete': True, 'truncated': False, 'reviewed_paths': ['src/add.ts'],
                'findings': []}
        return ModelResponse('fixture-model', 'fixture', json.dumps(report),
                             session_id=self.identity)


class NodeSCM(SCM):
    def prepare_commit(self, repository, **kwargs):
        self.writes += 1
        assert kwargs['changes'][0].after == GOOD
        return PreparedCommit('e' * 40, 'f' * 40, self.parent)


def test_real_docker_node_setup_checks_and_issue_to_draft(flow, monkeypatch):
    if not os.environ.get('SF_TEST_DOCKER_IMAGE'):
        pytest.skip('requires explicit real Docker integration')
    from sf_factory.docker_execution import run_offline_command

    root = node_repository(flow)
    data = inspect(flow)
    image = prepare_image(root, flow['factory'].root, data['node'])
    assert image.startswith('sha256:') and inspect(flow)['node']['image'] == image
    monkeypatch.setattr('sf_factory.issue_development.run_offline_command', run_offline_command)
    monkeypatch.setattr('sf_factory.workspace_check.run_offline_command', run_offline_command)
    checks = tuple(BehavioralCheck(c['id'], tuple(c['argv']), c['stdout']) for c in data['checks'])
    store = SetupProposals(flow['factory'].root)
    proposal = store.initial(root=root, repository='fixture/repo', name='Node E2E',
        provider='bedrock', image=image, allowed_paths=('src/add.ts',), checks=checks)
    receipt = store.approve(proposal['id'], proposal['fingerprint'])
    _, config = OperatorProfiles(store.root).get(receipt['profile']['id'])
    scm = NodeSCM(git(root, 'rev-parse', 'HEAD'))
    flow['source'].fetch_issue = lambda issue: ExternalIssue('fixture-issues', 'fixture/repo',
        issue, 'Implement add(a,b) in src/add.ts to return their sum.',
        'https://fixture.invalid/issues/' + issue)
    result = execute_issue(**{**flow, 'config': config, 'scm': scm,
        'implementer': NodeModel('node-implementation'), 'reviewer': NodeModel('node-review')})
    from sf_factory.issue_development import _artifact
    observations = (_artifact(flow['factory'], result['run_id']).get('checks', [])
                    if result.get('run_id') else [])
    assert result['status'] == 'completed' and scm.writes == 3, (result, observations)
    assert (root / 'src/add.ts').read_bytes() == BAD
    # Real test gate rejects wrong implementations, skipped and zero-test reports.
    files = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*')
             if p.is_file() and '.git' not in p.parts}
    scope = ProposalScope('a' * 32, 'b' * 40, 'c' * 64, 'd' * 64, ('src/add.ts',))
    candidate = parse_change_proposal(json.dumps({'schema_version': 1,
        'run_id': scope.run_id, 'revision': scope.revision, 'bundle_hash': scope.bundle_hash,
        'source_fingerprint': scope.source_fingerprint, 'changes': [{
            'path': 'src/add.ts', 'before_sha256': hashlib.sha256(BAD).hexdigest(),
            'content': GOOD.decode()}]}), scope=scope, source_files=files)
    wrong = parse_change_proposal(json.dumps({'schema_version': 1,
        'run_id': scope.run_id, 'revision': scope.revision, 'bundle_hash': scope.bundle_hash,
        'source_fingerprint': scope.source_fingerprint, 'changes': [{
            'path': 'src/add.ts', 'before_sha256': hashlib.sha256(BAD).hexdigest(),
            'content': GOOD.decode().replace('a + b', 'a - b')}]}), scope=scope, source_files=files)
    checked = run_candidate_check(image=image, scope=scope, proposal=wrong,
                                  source_files=files, argv=checks[0].argv)
    assert checked.status != 'succeeded' or checked.exit_code != 0
    assert checked.cleaned_up and checked.source_unchanged
    for test in (b"import { test } from 'vitest'; test.skip('skip',()=>{});\n",
                 b"import { test } from 'vitest'; test.todo('todo');\n",
                 b'export {};\n'):
        changed = {**files, 'tests/add.test.ts': test}
        checked = run_candidate_check(image=image, scope=scope, proposal=candidate,
            source_files=changed, argv=checks[0].argv)
        assert checked.status != 'succeeded' or checked.exit_code != 0
        assert checked.cleaned_up and checked.source_unchanged
