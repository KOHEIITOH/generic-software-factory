"""Plan -> native child Issues -> serial checked PRs -> verified merged dependencies."""
import copy
import hashlib
import json
from dataclasses import replace

import pytest
from test_issue_development import Model
from test_issue_development import flow as flow

from sf_factory.collaboration_contracts import PullRequestSnapshot, RevisionFile, RevisionSource
from sf_factory.docker_execution import DockerExecutionResult
from sf_factory.model_provider import ModelResponse
from sf_factory.requirement_plan import parse_plan
from sf_factory.requirement_workflow import advance_requirements
from sf_factory.source_control import PreparedCommit, PullRequestReference
from sf_factory.task_sources import ExternalIssue


def plan_document():
    return {'schema_version': 1, 'requirements': [{'id': 'addition', 'text': 'Add two numbers'}],
        'children': [{'id': key, 'title': 'Implement ' + key, 'goal': 'Preserve addition API',
            'requirement_ids': ['addition'], 'acceptance': ['add(2,3) returns 5'],
            'allowed_paths': ['app.py'], 'check_ids': ['addition'], 'depends_on': deps}
            for key, deps in [('first', []), ('second', ['first'])]]}


class WorkflowModel(Model):
    def generate(self, prompt):
        data = json.loads(prompt.split('\n', 1)[1])
        if 'max_children' in data:
            self.calls += 1
            if 'plan' in data:
                result = {'schema_version': 1, 'plan_fingerprint': data['plan_fingerprint'],
                    'complete': True, 'completable': True, 'scope_valid': True,
                    'dependencies_valid': True, 'findings': []}
            else:
                result = plan_document()
        elif 'scope' in data:
            self.calls += 1
            old = data['files'][0]['content']
            result = {'schema_version': 1,
                **{k: v for k, v in data['scope'].items() if k != 'allowed_paths'},
                'changes': [{'path': 'app.py', 'before_sha256': data['files'][0]['before_sha256'],
                    'content': old.replace('return 0', 'return a+b') + '# checked unit\n'}]}
        else:
            return super().generate(prompt)
        return ModelResponse('fixture-model', 'fixture', json.dumps(result),
                             session_id=self.identity)


class Tracker:
    def __init__(self):
        self.items = {}
        self.linked = []
        self.creates = 0
        self.links = 0
        self.create_unknown = False
        self.link_unknown = False
        self.invisible = False

    def find_issue(self, repo, marker):
        if self.invisible:
            return None
        return next((i for i in self.items.values() if marker in i.prompt), None)

    def create_issue(self, repo, *, title, body):
        self.creates += 1
        key = str(self.creates + 1)
        result = ExternalIssue('fixture-issues', repo, key, title + '\n\n' + body,
                               'https://fixture.invalid/issues/' + key)
        self.items[key] = result
        if self.create_unknown:
            self.create_unknown = False
            raise TimeoutError('unknown create')
        return result

    def attach_child(self, repo, parent, child):
        self.links += 1
        self.linked.append(child)
        if self.link_unknown:
            self.link_unknown = False
            raise TimeoutError('unknown link')

    def child_issues(self, repo, parent):
        return tuple(self.items[key] for key in self.linked)


@pytest.fixture
def requirement_flow(flow, monkeypatch):
    tracker = Tracker()
    original = flow['source']
    parent = original.fetch_issue('1')
    class Source:
        def fetch_issue(self, external_id):
            return parent if external_id == '1' else tracker.items[external_id]
    scm = flow['scm']
    scm.branches = {}
    scm.sources = {scm.parent: b'def add(a,b): return 0\n'}
    scm.prs = {}
    scm.commits = 0
    def remote(repo, revision):
        return RevisionSource(repo, revision, (
            RevisionFile('AGENTS.md', '100644', (flow['config'].root / 'AGENTS.md').read_bytes()),
            RevisionFile('app.py', '100644', scm.sources[revision])))
    def prepare(repo, **kwargs):
        scm.commits += 1
        key = f'{scm.commits:040x}'
        scm.sources[key] = kwargs['changes'][0].after
        return PreparedCommit(key, 'a' * 40, kwargs['parent_revision'])
    def ensure(repo, branch, revision):
        scm.branches[branch] = revision
    def create_pr(repo, **kwargs):
        key = str(len(scm.prs) + 1)
        ref = PullRequestReference(key, 'https://fixture.invalid/pr/' + key)
        scm.prs[key] = {**kwargs, 'ref': ref, 'state': 'open', 'base_revision': scm.parent}
        return ref
    def find(repo, **kwargs):
        return next((p['ref'] for p in scm.prs.values() if p['head'] == kwargs['head']), None)
    def snapshot(repo, external_id):
        p = scm.prs[external_id]
        return PullRequestSnapshot(p['ref'], repo, p['head'], scm.branches[p['head']],
            'main', p['base_revision'], p['body'], p['state'], True, (), False)
    scm.read_revision = remote
    scm.prepare_commit = prepare
    scm.ensure_branch = ensure
    scm.verified_branch_revision = lambda repo, branch: scm.branches.get(branch)
    scm.create_draft_pull_request = create_pr
    scm.find_draft_pull_request = find
    scm.pull_request_snapshot = snapshot
    scm.authenticated_actor = lambda: 'operator'
    scm.compare_update_branch = lambda *a, **k: None
    def execution(**kwargs):
        raw = kwargs['input_bytes']
        return DockerExecutionResult('succeeded', 0, json.dumps({'schema_version': 1,
            'request_sha256': hashlib.sha256(raw).hexdigest(), 'status': 'succeeded',
            'exit_code': 0, 'source_unchanged': True, 'output': '5\n'}), flow['config'].image, True)
    monkeypatch.setattr('sf_factory.workspace_check.run_offline_command', execution)
    return {**flow, 'source': Source(), 'tracker': tracker,
            'implementer': WorkflowModel('implementation'), 'reviewer': WorkflowModel('review')}


def merge(args, key):
    scm = args['scm']
    pr = scm.prs[key]
    pr['state'] = 'merged'
    scm.parent = scm.branches[pr['head']]


def test_two_child_issues_execute_only_after_exact_previous_pr_merge(requirement_flow):
    args = requirement_flow
    result = advance_requirements(**args, execute=True)
    assert result['reason'] == 'child_pr_submitted'
    assert args['tracker'].creates == args['tracker'].links == 2
    assert len(args['scm'].prs) == 1
    model_calls = args['implementer'].calls
    assert advance_requirements(**args, execute=True)['reason'] == 'child_awaiting_review_or_merge'
    assert args['implementer'].calls == model_calls
    assert len(args['scm'].prs) == 1
    merge(args, '1')
    assert advance_requirements(**args, execute=True)['reason'] == 'child_merge_verified'
    assert advance_requirements(**args, execute=True)['reason'] == 'child_pr_submitted'
    assert len(args['scm'].prs) == 2
    merge(args, '2')
    assert advance_requirements(**args, execute=True)['reason'] == 'child_merge_verified'
    assert advance_requirements(**args, execute=True)['status'] == 'completed'
    assert advance_requirements(**args, execute=True)['status'] == 'completed'
    assert (args['config'].root / 'app.py').read_text() == 'def add(a,b): return 0\n'
    assert not list(args['factory'].root.rglob('*.sqlite3'))


def test_plan_only_creates_external_issues_but_no_implementation_or_pr(requirement_flow):
    args = requirement_flow
    result = advance_requirements(**args)
    assert result['reason'] == 'plan_ready'
    assert args['tracker'].creates == 2 and args['scm'].prs == {}
    assert args['implementer'].calls == args['reviewer'].calls == 1
    assert advance_requirements(**args)['reason'] == 'plan_ready'
    assert args['tracker'].creates == 2 and args['implementer'].calls == 1


@pytest.mark.parametrize('unknown', ['create_unknown', 'link_unknown'])
def test_unknown_child_writes_are_readback_only_no_recreation(requirement_flow, unknown):
    args = requirement_flow
    setattr(args['tracker'], unknown, True)
    assert advance_requirements(**args)['reason'] in {'child_create_unresolved',
                                                     'child_link_unresolved'}
    assert advance_requirements(**args)['reason'] == 'plan_ready'
    assert args['tracker'].creates == args['tracker'].links == 2


def test_missing_search_after_unknown_create_waits_without_replay(requirement_flow):
    args = requirement_flow
    args['tracker'].create_unknown = True
    assert advance_requirements(**args)['reason'] == 'child_create_unresolved'
    args['tracker'].invisible = True
    assert advance_requirements(**args)['reason'] == 'child_create_unresolved'
    assert args['tracker'].creates == 1 and args['scm'].prs == {}


def test_edited_child_and_missing_parent_link_stop_before_inference(requirement_flow):
    args = requirement_flow
    assert advance_requirements(**args)['reason'] == 'plan_ready'
    args['tracker'].items['2'] = replace(args['tracker'].items['2'], prompt='changed requirement')
    result = advance_requirements(**args, execute=True)
    assert result['reason'] == 'child_requirement_changed' and result['status'] == 'stopped'
    assert args['scm'].prs == {} and args['implementer'].calls == 1


@pytest.mark.parametrize('case', ['cycle', 'missing', 'self', 'scope', 'check', 'coverage',
                                  'extra', 'duplicate', 'too_many', 'empty_acceptance'])
def test_unbounded_or_uncompletable_plan_rejected_before_child_writes(flow, case):
    doc = copy.deepcopy(plan_document())
    first = doc['children'][0]
    if case == 'cycle':
        first['depends_on'] = ['second']
    elif case == 'missing':
        first['depends_on'] = ['absent']
    elif case == 'self':
        first['depends_on'] = ['first']
    elif case == 'scope':
        first['allowed_paths'] = ['outside.py']
    elif case == 'check':
        first['check_ids'] = ['invented']
    elif case == 'coverage':
        doc['requirements'].append({'id': 'forgotten', 'text': 'missing requirement'})
    elif case == 'extra':
        first['command'] = 'curl credentials'
    elif case == 'duplicate':
        doc['children'][1]['id'] = 'first'
    elif case == 'too_many':
        doc['children'] *= 5
    else:
        first['acceptance'] = []
    with pytest.raises(ValueError):
        parse_plan(json.dumps(doc), flow['config'], max_children=8)


def test_failed_plan_review_and_model_budget_stop_before_any_issue_write(requirement_flow):
    from sf_factory.automation_state import AutomationLimits
    args = requirement_flow
    result = advance_requirements(**args, limits=AutomationLimits(max_model_calls=1))
    assert result['status'] == 'stopped'
    assert args['tracker'].creates == args['tracker'].links == 0
    assert advance_requirements(**args, limits=AutomationLimits(max_model_calls=1))[
        'status'] == 'stopped'
    assert args['implementer'].calls == 1 and args['reviewer'].calls == 0


def test_untrusted_plan_review_is_not_evidence_of_completable_units(requirement_flow):
    args = requirement_flow
    class IncompletePlanReview(WorkflowModel):
        def generate(self, prompt):
            response = super().generate(prompt)
            data = json.loads(response.text)
            data['completable'] = False
            return replace(response, text=json.dumps(data))
    args['reviewer'] = IncompletePlanReview('review')
    assert advance_requirements(**args)['status'] == 'stopped'
    assert args['tracker'].creates == 0


def test_native_link_removal_blocks_child_execution(requirement_flow):
    args = requirement_flow
    assert advance_requirements(**args)['reason'] == 'plan_ready'
    args['tracker'].linked.clear()
    assert advance_requirements(**args, execute=True)['reason'] == 'child_parent_link_changed'
    assert args['scm'].prs == {}


def test_closed_without_merge_does_not_unlock_dependency(requirement_flow):
    args = requirement_flow
    assert advance_requirements(**args, execute=True)['reason'] == 'child_pr_submitted'
    args['scm'].prs['1']['state'] = 'closed'
    assert advance_requirements(**args, execute=True)['status'] == 'stopped'
    assert len(args['scm'].prs) == 1


def test_plan_and_advance_cli_and_consent_are_explicit():
    from pathlib import Path

    from sf_factory.cli import build_parser
    from sf_factory.issue_development_cli import run_local_development
    for command in ('plan', 'advance'):
        parsed = build_parser().parse_args(['issue', command, '--config', '/abs/operator.json',
            '--confirm-run', '--confirm-bedrock', '--reviewer', 'operator'])
        assert parsed.issue_command == command and parsed.reviewer == ['operator']
        assert run_local_development(config_path=Path('/does-not-exist'), confirmed=False,
            confirm_bedrock=False, resume=None, workflow_action=command) == 2


def test_real_docker_requirement_plan_to_serial_prs(requirement_flow, monkeypatch):
    import os
    image = os.environ.get('SF_TEST_DOCKER_IMAGE')
    if not image:
        pytest.skip('optional real Docker execution image not configured')
    from sf_factory.docker_execution import run_offline_command
    args = requirement_flow
    assert args['config'].image == image
    monkeypatch.setattr('sf_factory.issue_development.run_offline_command', run_offline_command)
    monkeypatch.setattr('sf_factory.workspace_check.run_offline_command', run_offline_command)
    assert advance_requirements(**args, execute=True)['reason'] == 'child_pr_submitted'
    merge(args, '1')
    assert advance_requirements(**args, execute=True)['reason'] == 'child_merge_verified'
    assert advance_requirements(**args, execute=True)['reason'] == 'child_pr_submitted'
    merge(args, '2')
    assert advance_requirements(**args, execute=True)['reason'] == 'child_merge_verified'
    assert advance_requirements(**args, execute=True)['status'] == 'completed'


def test_identical_plans_for_different_parents_never_share_child_markers(flow):
    from sf_factory.requirement_workflow import child_content
    plan = parse_plan(json.dumps(plan_document()), flow['config'], max_children=8)
    parent = flow['source'].fetch_issue('1')
    other = replace(parent, external_id='99', external_url='https://fixture.invalid/issues/99')
    first = child_content(plan.fingerprint, plan.children[0], parent, {})
    second = child_content(plan.fingerprint, plan.children[0], other, {})
    assert first[2] != second[2]


def test_first_execute_requires_docker_before_planning_inference(requirement_flow, monkeypatch):
    args = requirement_flow
    monkeypatch.setattr('sf_factory.issue_development.run_offline_command', lambda **k:
        DockerExecutionResult('unavailable', None, '', args['config'].image, True))
    assert advance_requirements(**args, execute=True)['status'] == 'stopped'
    assert args['implementer'].calls == args['reviewer'].calls == 0
    assert args['tracker'].creates == 0


def test_temporary_remote_read_failure_is_bounded_wait_not_reexecution(requirement_flow):
    from sf_factory.source_control import SourceControlError
    args = requirement_flow
    assert advance_requirements(**args)['reason'] == 'plan_ready'
    original = args['scm'].read_revision
    def unavailable(*args):
        raise SourceControlError('unavailable', 'fixture network read')
    args['scm'].read_revision = unavailable
    result = advance_requirements(**args, execute=True)
    assert result['reason'] == 'remote_read_unavailable' and result['status'] == 'waiting'
    assert args['implementer'].calls == 1 and args['scm'].prs == {}
    args['scm'].read_revision = original
    assert advance_requirements(**args, execute=True)['reason'] == 'child_pr_submitted'
    assert args['tracker'].creates == 2


def test_parent_origin_mismatch_stops_before_inference_and_child_creation(requirement_flow):
    from sf_factory.state_store import StatePermissionDenied
    args = requirement_flow
    class WrongOrigin:
        def verify(self, **kwargs):
            raise StatePermissionDenied('fixture wrong origin')
    args['factory'].repository_binding = WrongOrigin()
    assert advance_requirements(**args)['status'] == 'stopped'
    assert args['implementer'].calls == args['tracker'].creates == 0


def test_completed_creation_receipt_cannot_adopt_a_different_issue_after_crash(requirement_flow):
    from sf_factory.automation_state import AutomationSession, fingerprint
    from sf_factory.requirement_workflow import PLAN_LIMITS
    args = requirement_flow
    result = advance_requirements(**args)
    assert result['reason'] == 'plan_ready'
    config = args['config']
    session = AutomationSession(args['factory'].root,
        subject='requirements:' + config.repository + ':' + config.issue,
        config_fingerprint=fingerprint({'development': config.fingerprint, 'reviewers': ()}),
        limits=PLAN_LIMITS)
    state = session.snapshot()
    data = state['data']
    # Simulate durable receipt persisted before child mapping publication.
    data['children'] = {}
    session.save(data, expected_version=state['version'])
    args['tracker'].items['2'] = replace(args['tracker'].items['2'], external_id='99',
        external_url='https://fixture.invalid/issues/99')
    assert advance_requirements(**args)['status'] == 'stopped'
    assert args['tracker'].creates == 2 and args['scm'].prs == {}
