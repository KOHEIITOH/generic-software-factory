"""Trusted-controller delivery orchestration. No model output grants permissions."""
from __future__ import annotations

from typing import Protocol

from sf_factory.delivery_plan import DeliveryPlan
from sf_factory.delivery_state import DeliveryState
from sf_factory.source_control import ChangeSourceControl, PullRequestReference
from sf_factory.state_store import StateConflict, StateNotFound


class DeliveryGuards(Protocol):
    def verify(self, plan: DeliveryPlan) -> None:
        """Revalidate exact artifact, trusted evidence and live scoped authorization.

        Implemented by the authenticated local controller, not a model or HTTP
        caller's dictionary. Raise on missing, stale or incomplete prerequisites.
        """
        ...


def deliver_draft(*, plan: DeliveryPlan, state: DeliveryState,
                  scm: ChangeSourceControl, guards: DeliveryGuards) -> PullRequestReference:
    """Persist before mutation; reconcile pending operations without replay.

    A successful initial return has a read-back-verified Draft PR receipt. A
    commit-preparation outcome unknown remains claimed and requires intervention.
    This function does not authenticate an operator or manufacture quality facts.
    """
    guards.verify(plan)
    info = scm.describe_repository(plan.repository)
    if (info.external_id != plan.repository or not info.capabilities.write
            or not info.capabilities.pull_request):
        raise PermissionError('exact writable repository with PR capability required')
    def current_base() -> None:
        if scm.branch_revision(plan.repository, plan.base_branch) != plan.parent_revision:
            raise StateConflict('base branch changed; new approved implementation required')

    try:
        record = state.get(plan.run_id)
        new = False
    except StateNotFound:
        current_base()
        record = state.claim(plan)
        new = True
    if record.fingerprint != plan.fingerprint:
        raise StateConflict('delivery plan changed')

    def existing_pr() -> PullRequestReference | None:
        assert record.commit is not None
        return scm.find_draft_pull_request(plan.repository, head=plan.branch,
            base=plan.base_branch, revision=record.commit.external_id, marker=plan.marker)

    if record.stage == 'claimed':
        if not new:
            raise StateConflict('commit preparation outcome unknown; do not replay')
        current_base()
        commit = scm.prepare_commit(plan.repository, parent_revision=plan.parent_revision,
            changes=plan.changes, message='Software Factory: Run ' + plan.run_id)
        record = state.advance(plan.run_id, plan.fingerprint, expected='claimed',
                               stage='commit_ready', commit=commit)
    assert record.commit is not None
    revision = record.commit.external_id
    if record.stage == 'commit_ready':
        guards.verify(plan)
        current_base()
        record = state.advance(plan.run_id, plan.fingerprint, expected='commit_ready',
                               stage='branch_pending')
        scm.ensure_branch(plan.repository, plan.branch, revision)
        record = state.advance(plan.run_id, plan.fingerprint, expected='branch_pending',
                               stage='branch_ready')
    elif record.stage == 'branch_pending':
        if scm.verified_branch_revision(plan.repository, plan.branch) != revision:
            raise StateConflict('branch outcome unresolved; do not replay')
        record = state.advance(plan.run_id, plan.fingerprint, expected='branch_pending',
                               stage='branch_ready')
    if record.stage == 'branch_ready':
        guards.verify(plan)
        current_base()
        if scm.verified_branch_revision(plan.repository, plan.branch) != revision:
            raise StateConflict('candidate branch changed')
        prior = existing_pr()  # A prior matching PR can be adopted without a write.
        record = state.advance(plan.run_id, plan.fingerprint, expected='branch_ready',
                               stage='pr_pending')
        if prior is None:
            returned = scm.create_draft_pull_request(plan.repository,
                title='Software Factory: Run ' + plan.run_id, head=plan.branch,
                base=plan.base_branch, body=plan.marker)
            prior = existing_pr()
            if prior != returned:
                raise StateConflict('PR outcome unresolved; do not replay')
        if prior is None:
            raise StateConflict('PR outcome unresolved; do not replay')
        record = state.advance(plan.run_id, plan.fingerprint, expected='pr_pending',
                               stage='delivered', pull_request=prior)
    elif record.stage in {'pr_pending', 'delivered'}:
        # Recovery only reads. An empty list is NOT permission to recreate a PR.
        if scm.verified_branch_revision(plan.repository, plan.branch) != revision:
            raise StateConflict('candidate branch changed')
        prior = existing_pr()
        if prior is None:
            raise StateConflict('PR outcome unresolved; do not replay')
        if record.stage == 'pr_pending':
            record = state.advance(plan.run_id, plan.fingerprint, expected='pr_pending',
                                   stage='delivered', pull_request=prior)
        elif record.pull_request != prior:
            raise StateConflict('stored PR receipt differs from remote')
    assert record.pull_request is not None
    return record.pull_request
