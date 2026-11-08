"""Simulated remote/model, real durable Runs/check evidence and recovery state."""
import hashlib
import json
from dataclasses import replace

import pytest
from test_issue_development import Model
from test_issue_development import flow as flow

from sf_factory.automation_state import AutomationLimits
from sf_factory.collaboration_contracts import (
    PullRequestSnapshot,
    ReviewDecision,
    ReviewFeedback,
    RevisionFile,
    RevisionSource,
)
from sf_factory.docker_execution import DockerExecutionResult
from sf_factory.issue_development import _artifact, _plan, develop_issue
from sf_factory.model_provider import ModelResponse
from sf_factory.review_automation import advance_review
from sf_factory.source_control import PreparedCommit


class RepairModel(Model):
    def generate(self, prompt):
        data = json.loads(prompt.split('\n', 1)[1])
        if 'scope' not in data:
            return super().generate(prompt)
        self.calls += 1
        return ModelResponse('fixture-model', 'fixture', json.dumps({'schema_version': 1,
            **{k: v for k, v in data['scope'].items() if k != 'allowed_paths'},
            'changes': [{'path': 'app.py', 'before_sha256': data['files'][0]['before_sha256'],
                         'content': 'def add(a,b): return a + b\n'}]}),
            session_id='repair-implementation')


@pytest.fixture
def review_flow(flow, monkeypatch):
    initial = develop_issue(**flow)
    scm = flow['scm']
    plan = _plan(flow['factory'], _artifact(flow['factory'], initial['run_id']))
    state = {'head': 'e' * 40, 'status': 'open', 'base': scm.parent,
             'feedback': (ReviewFeedback('comment1', 'operator', 'Preserve API', 'app.py',
                                        'unresolved', 'e' * 40),), 'decisions': (),
             'cas_timeout': False, 'commit_timeout': False, 'cas_calls': 0,
             'remote_calls': 0}
    def snapshot(repo, pr):
        state['remote_calls'] += 1
        return PullRequestSnapshot(scm.pr, repo, plan.branch, state['head'], 'main',
            state['base'], plan.marker, state['status'], True, state['feedback'], False,
            state['decisions'])
    def remote(repo, revision):
        return RevisionSource(repo, revision, (
            RevisionFile('AGENTS.md', '100644', (flow['config'].root / 'AGENTS.md').read_bytes()),
            RevisionFile('app.py', '100644', b'def add(a,b): return a+b\n')))
    def prepare(repo, **kwargs):
        scm.writes += 1
        if state['commit_timeout']:
            raise TimeoutError('unknown fixture commit')
        return PreparedCommit('f' * 40, 'a' * 40, kwargs['parent_revision'])
    def update(repo, branch, *, expected, revision):
        state['cas_calls'] += 1
        assert state['head'] == expected
        state['head'] = revision
        scm.revision = revision
        if state['cas_timeout']:
            raise TimeoutError('unknown fixture CAS')
    def execution(**kwargs):
        raw = kwargs['input_bytes']
        return DockerExecutionResult('succeeded', 0, json.dumps({'schema_version': 1,
            'request_sha256': hashlib.sha256(raw).hexdigest(), 'status': 'succeeded',
            'exit_code': 0, 'source_unchanged': True, 'output': '5\n'}), flow['config'].image, True)
    monkeypatch.setattr('sf_factory.workspace_check.run_offline_command', execution)
    scm.authenticated_actor = lambda: 'operator'
    scm.pull_request_snapshot = snapshot
    scm.read_revision = remote
    scm.prepare_commit = prepare
    scm.compare_update_branch = update
    flow['implementer'] = RepairModel('repair-implementation')
    flow['reviewer'] = Model('repair-review')
    return {**flow, 'initial_run': initial['run_id']}, state


def test_review_fix_appends_same_branch_then_waits_without_duplicate_model_or_write(review_flow):
    args, state = review_flow
    result = advance_review(**args)
    assert result['reason'] == 'repair_submitted'
    assert result['pr']['external_id'] == '7'
    assert state['head'] == 'f' * 40 and state['cas_calls'] == 1
    assert args['implementer'].calls == args['reviewer'].calls == 1
    again = advance_review(**args)
    assert again['reason'] == 'awaiting_review'
    assert state['cas_calls'] == 1 and args['implementer'].calls == 1
    state['feedback'] = ()
    state['decisions'] = (ReviewDecision('approval', 'operator', 'approved', state['head']),)
    assert advance_review(**args)['reason'] == 'awaiting_merge'
    state['status'] = 'merged'
    assert advance_review(**args)['status'] == 'completed'
    calls = state['remote_calls']
    assert advance_review(**args)['status'] == 'completed'
    assert state['remote_calls'] == calls


def test_unknown_branch_write_reconciles_without_replaying(review_flow):
    args, state = review_flow
    state['cas_timeout'] = True
    assert advance_review(**args)['reason'] == 'awaiting_branch_reconciliation'
    assert advance_review(**args)['reason'] == 'repair_reconciled'
    assert state['cas_calls'] == 1 and args['implementer'].calls == 1


@pytest.mark.parametrize('case',
                         ['untrusted', 'no_feedback', 'outside_scope', 'base_move', 'closed'])
def test_feedback_trust_scope_and_waiting_are_explicit(review_flow, case):
    args, state = review_flow
    if case == 'untrusted':
        state['feedback'] = (replace(state['feedback'][0], author='stranger'),)
    elif case == 'no_feedback':
        state['feedback'] = ()
    elif case == 'outside_scope':
        state['feedback'] = (replace(state['feedback'][0], path='secrets.txt'),)
    elif case == 'base_move':
        state['base'] = 'b' * 40
    else:
        state['status'] = 'closed'
    result = advance_review(**args)
    assert result['status'] == ('waiting' if case in {'untrusted', 'no_feedback'} else 'stopped')
    assert args['implementer'].calls == state['cas_calls'] == 0


def test_commit_outcome_unknown_is_terminal_without_replay(review_flow):
    args, state = review_flow
    state['commit_timeout'] = True
    assert advance_review(**args)['status'] == 'stopped'
    calls = args['scm'].writes
    assert advance_review(**args)['status'] == 'stopped'
    assert args['scm'].writes == calls


def test_round_budget_persists_and_repeated_file_candidate_stops(review_flow):
    args, state = review_flow
    first = advance_review(**args, limits=AutomationLimits(max_rounds=1))
    assert first['reason'] == 'repair_submitted'
    state['feedback'] = (replace(state['feedback'][0], id='new-comment'),)
    result = advance_review(**args, limits=AutomationLimits(max_rounds=1))
    assert result['status'] == 'stopped'
    assert advance_review(**args, limits=AutomationLimits(max_rounds=1))['status'] == 'stopped'
    assert args['implementer'].calls == 1


def test_must_fix_independent_review_never_writes_repair(review_flow):
    args, state = review_flow
    args['reviewer'].must_fix = True
    writes = args['scm'].writes
    assert advance_review(**args)['status'] == 'stopped'
    assert state['cas_calls'] == 0 and args['scm'].writes == writes


def test_changed_external_head_never_repaired_or_overwritten(review_flow):
    args, state = review_flow
    state['head'] = 'c' * 40
    assert advance_review(**args)['status'] == 'stopped'
    assert args['implementer'].calls == state['cas_calls'] == 0


def test_repeated_candidate_bytes_stop_even_with_new_run_ids(review_flow):
    args, state = review_flow
    assert advance_review(**args)['reason'] == 'repair_submitted'
    state['feedback'] = (replace(state['feedback'][0], id='second-comment'),)
    assert advance_review(**args)['status'] == 'stopped'
    assert args['implementer'].calls == 2 and state['cas_calls'] == 1


def test_real_docker_same_pr_review_repair(review_flow, monkeypatch):
    import os
    image = os.environ.get('SF_TEST_DOCKER_IMAGE')
    if not image:
        pytest.skip('optional real Docker execution image not configured')
    from sf_factory.docker_execution import run_offline_command
    args, state = review_flow
    assert args['config'].image == image
    monkeypatch.setattr('sf_factory.issue_development.run_offline_command', run_offline_command)
    monkeypatch.setattr('sf_factory.workspace_check.run_offline_command', run_offline_command)
    result = advance_review(**args)
    assert result['reason'] == 'repair_submitted'
    assert state['cas_calls'] == 1


def test_review_cli_parses_original_run_and_explicit_trust():
    from sf_factory.cli import build_parser
    args = build_parser().parse_args(['issue', 'review', '--config', '/tmp/operator.json',
        '--run', 'a' * 32, '--reviewer', 'review-bot', '--confirm-run', '--confirm-bedrock'])
    assert args.issue_command == 'review' and args.run == 'a' * 32
    assert args.reviewer == ['review-bot'] and args.confirm_run and args.confirm_bedrock


def test_temporary_snapshot_read_failure_waits_without_model_or_write(review_flow):
    from sf_factory.source_control import SourceControlError
    args, state = review_flow
    snapshot = args['scm'].pull_request_snapshot
    def unavailable(*args):
        raise SourceControlError('unavailable', 'fixture network read')
    args['scm'].pull_request_snapshot = unavailable
    assert advance_review(**args)['reason'] == 'remote_read_unavailable'
    assert args['implementer'].calls == state['cas_calls'] == 0
    args['scm'].pull_request_snapshot = snapshot
    assert advance_review(**args)['reason'] == 'repair_submitted'
