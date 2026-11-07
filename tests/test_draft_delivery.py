"""A controller writes each visible artifact once, or stops with durable intent."""
from dataclasses import replace

import pytest
from test_delivery_plan import fixture

from sf_factory.delivery_plan import build_delivery_plan
from sf_factory.draft_delivery import deliver_draft
from sf_factory.file_delivery_state import FileDeliveryState
from sf_factory.repository_contracts import RepositoryCapabilities
from sf_factory.source_control import PreparedCommit, PullRequestReference, RepositoryInfo
from sf_factory.state_store import StateConflict

COMMIT = PreparedCommit('e' * 40, 'f' * 40, 'b' * 40)
PR = PullRequestReference('7', 'https://fixture.invalid/pr/7')


class Guards:
    def __init__(self):
        self.calls = 0
        self.reject_at = None

    def verify(self, plan):
        self.calls += 1
        if self.calls == self.reject_at:
            raise PermissionError('missing/expired quality or authorization')


class SCM:
    def __init__(self):
        self.commit_calls = self.branch_calls = self.pr_calls = 0
        self.base = 'b' * 40
        self.revision = None
        self.pr = None
        self.fail = None
        self.writable = True

    def describe_repository(self, repository):
        return RepositoryInfo(repository, 'main', RepositoryCapabilities(
            read=True, write=self.writable, pull_request=self.writable))

    def branch_revision(self, repository, branch):
        return self.base

    def prepare_commit(self, repository, **kwargs):
        self.commit_calls += 1
        if self.fail == 'commit':
            raise TimeoutError('commit unknown')
        assert kwargs['parent_revision'] == self.base
        return COMMIT

    def ensure_branch(self, repository, branch, revision):
        self.branch_calls += 1
        self.revision = revision
        if self.fail == 'branch':
            raise TimeoutError('branch unknown')

    def verified_branch_revision(self, repository, branch):
        return self.revision

    def find_draft_pull_request(self, repository, **kwargs):
        assert kwargs['revision'] == COMMIT.external_id
        return self.pr

    def create_draft_pull_request(self, repository, **kwargs):
        self.pr_calls += 1
        assert kwargs['body'].startswith('<!-- sf-delivery run=')
        self.pr = PR
        if self.fail == 'pr':
            raise TimeoutError('PR unknown')
        if self.fail == 'receipt':
            return replace(PR, external_id='8')
        return PR


@pytest.fixture
def flow(tmp_path):
    return dict(plan=build_delivery_plan(**fixture()), state=FileDeliveryState(tmp_path),
                scm=SCM(), guards=Guards())


def test_exact_delivery_is_durable_and_repeated_call_only_reads(flow):
    assert deliver_draft(**flow) == PR
    assert flow['state'].get(flow['plan'].run_id).stage == 'delivered'
    assert deliver_draft(**flow) == PR
    scm = flow['scm']
    assert (scm.commit_calls, scm.branch_calls, scm.pr_calls) == (1, 1, 1)


@pytest.mark.parametrize('point', [1, 2, 3])
def test_missing_or_expired_guard_never_crosses_next_write(flow, point):
    flow['guards'].reject_at = point
    with pytest.raises(PermissionError):
        deliver_draft(**flow)
    scm = flow['scm']
    assert scm.pr_calls == 0
    assert scm.branch_calls == (1 if point == 3 else 0)
    assert scm.commit_calls == (0 if point == 1 else 1)


def test_lost_commit_receipt_does_not_prepare_again(flow):
    flow['scm'].fail = 'commit'
    with pytest.raises(TimeoutError):
        deliver_draft(**flow)
    flow['scm'].fail = None
    with pytest.raises(StateConflict, match='do not replay'):
        deliver_draft(**flow)
    assert flow['scm'].commit_calls == 1
    assert flow['state'].get(flow['plan'].run_id).stage == 'claimed'


@pytest.mark.parametrize('operation', ['branch', 'pr', 'receipt'])
def test_uncertain_visible_write_is_reconciled_without_replay(flow, operation):
    flow['scm'].fail = operation
    with pytest.raises((TimeoutError, StateConflict)):
        deliver_draft(**flow)
    flow['scm'].fail = None
    assert deliver_draft(**flow) == PR
    assert (flow['scm'].commit_calls, flow['scm'].branch_calls, flow['scm'].pr_calls) == (1, 1, 1)


@pytest.mark.parametrize('operation', ['branch', 'pr'])
def test_missing_unknown_remote_result_is_not_recreated(flow, operation):
    scm = flow['scm']
    scm.fail = operation
    with pytest.raises(TimeoutError):
        deliver_draft(**flow)
    scm.revision = None if operation == 'branch' else scm.revision
    scm.pr = None
    with pytest.raises(StateConflict, match='do not replay'):
        deliver_draft(**flow)
    assert scm.branch_calls == 1
    assert scm.pr_calls == (1 if operation == 'pr' else 0)


def test_stale_base_never_prepares_commit(flow):
    flow['scm'].base = '0' * 40
    with pytest.raises(StateConflict, match='base branch'):
        deliver_draft(**flow)
    assert flow['scm'].commit_calls == 0


def test_missing_write_permissions_never_claims_or_writes(flow):
    flow['scm'].writable = False
    with pytest.raises(PermissionError):
        deliver_draft(**flow)
    assert flow['scm'].commit_calls == 0


def test_different_plan_or_changed_remote_branch_is_not_reused(flow):
    deliver_draft(**flow)
    with pytest.raises(StateConflict, match='plan changed'):
        deliver_draft(**{**flow, 'plan': replace(flow['plan'], base_branch='release')})
    flow['scm'].revision = '0' * 40
    with pytest.raises(StateConflict, match='branch changed'):
        deliver_draft(**flow)
