"""Finite one-step review repair; waiting is a durable result, never a polling loop."""
from __future__ import annotations

import hashlib
from dataclasses import asdict

from sf_factory.automation_state import AutomationLimits, AutomationSession, fingerprint
from sf_factory.budgeted_model import BudgetedModel
from sf_factory.collaboration_contracts import CollaborationSourceControl
from sf_factory.development_config import DevelopmentConfig
from sf_factory.factory import Factory
from sf_factory.file_delivery_state import FileDeliveryState
from sf_factory.file_state import lock_directory
from sf_factory.issue_development import (
    DevelopmentStopped,
    _artifact,
    _LocalGuards,
    _plan,
    develop_issue,
)
from sf_factory.model_provider import ModelProvider
from sf_factory.state_store import StateConflict, StatePermissionDenied
from sf_factory.task_sources import TaskSourceAdapter


def _save(session: AutomationSession, data: dict, code: str, *, status='waiting', **facts) -> dict:
    session.save(data, expected_version=session.snapshot()['version'], status=status,
                 decision=code, facts=facts)
    return {'session_id': session.id, 'status': status, 'reason': code, **data}


def _candidate_hash(plan) -> str:
    # Exclude Run/provenance IDs: identical file changes are stagnation across Runs.
    return fingerprint([(c.path, hashlib.sha256(c.after).hexdigest(), c.executable)
                        for c in plan.changes])


def advance_review(*, factory: Factory, config: DevelopmentConfig,
                   source: TaskSourceAdapter, scm: CollaborationSourceControl,
                   implementer: ModelProvider, reviewer: ModelProvider,
                   initial_run: str, confirmed: bool,
                   trusted_reviewers: tuple[str, ...] = (),
                   limits: AutomationLimits = AutomationLimits()) -> dict:
    if not confirmed or implementer is reviewer or config.data_root != factory.root:
        raise StatePermissionDenied('explicit local scope and independent providers required')
    if (not isinstance(trusted_reviewers, tuple) or len(trusted_reviewers) > 16
            or any(not isinstance(a, str) or not a.strip() or len(a) > 128
                   for a in trusted_reviewers)):
        raise ValueError('bounded trusted reviewer identities required')
    session = AutomationSession(factory.root, subject='review:' + config.repository + ':' +
        initial_run, config_fingerprint=fingerprint({'development': config.fingerprint,
        'reviewers': trusted_reviewers}), limits=limits)
    lock = factory.root / 'automation-controller-v1'
    lock.mkdir(mode=0o700, exist_ok=True)
    with lock_directory(lock):
        state = session.snapshot()
        if state['status'] in {'stopped', 'completed'}:
            return {'session_id': session.id, 'status': state['status'], **state['data']}
        # Adapter transport guard covers every real HTTP request, including pagination.
        prior_guard = getattr(scm, 'request_guard', None)
        if hasattr(scm, 'request_guard'):
            setattr(scm, 'request_guard', session.api_call)
        try:
            return _advance(factory, config, source, scm, implementer, reviewer,
                            initial_run, trusted_reviewers, session)
        except Exception as exc:
            if session.snapshot()['status'] not in {'stopped', 'completed'}:
                data = session.snapshot()['data']
                # Never record SDK exception text, prompts, credentials, or ask to reset limits.
                _save(session, data, 'advance_stopped', status='stopped',
                      error_type=type(exc).__name__)
            final = session.snapshot()
            return {'session_id': session.id, 'status': final['status'],
                    'reason': 'advance_stopped', **final['data']}
        finally:
            if hasattr(scm, 'request_guard'):
                setattr(scm, 'request_guard', prior_guard)


def _advance(factory, config, source, scm, implementer, reviewer, initial_run,
             trusted_reviewers, session):
    data = session.snapshot()['data']
    if not data:
        value = _artifact(factory, initial_run)
        if value['phase'] != 'delivered' or value['config_fingerprint'] != config.fingerprint:
            raise StatePermissionDenied('exact delivered Factory Run required')
        plan = _plan(factory, value)
        receipt = FileDeliveryState(factory.root).get(initial_run)
        if (receipt.stage != 'delivered' or receipt.pull_request is None
                or receipt.commit is None or receipt.fingerprint != plan.fingerprint
                or value['pull_request'] != asdict(receipt.pull_request)):
            raise StateConflict('Factory delivery receipt differs')
        actors = trusted_reviewers or (scm.authenticated_actor(),)
        data = {'initial_run': initial_run, 'run_id': initial_run,
            'head': receipt.commit.external_id, 'branch': plan.branch,
            'base': plan.base_branch, 'base_revision': plan.parent_revision,
            'pr': asdict(receipt.pull_request), 'marker': plan.marker,
            'actors': list(actors), 'handled': [], 'phase': 'observe'}
        _save(session, data, 'review_scope_frozen', status='ready', actors=list(actors))
    if data['phase'] == 'evaluating':
        # A crash before storing the reviewed Run cannot authorize a second inference.
        raise StateConflict('candidate evaluation outcome unknown; no replay')
    snapshot = scm.pull_request_snapshot(config.repository, data['pr']['external_id'])
    if (snapshot.repository != config.repository or asdict(snapshot.reference) != data['pr']
            or snapshot.head_branch != data['branch'] or snapshot.base_branch != data['base']
            or data['marker'] not in snapshot.body):
        raise StateConflict('PR identity/scope changed')
    expected = data.get('commit') if data['phase'] == 'update_pending' else data['head']
    if data['phase'] == 'update_pending':
        # Reconcile only. Never resend an unknown GraphQL mutation.
        if (snapshot.head_revision != expected or
                scm.verified_branch_revision(config.repository, data['branch']) != expected):
            return _save(session, data, 'branch_update_unresolved', status='stopped')
        action = 'update:' + data['run_id']
        session.complete_action(action, {'revision': expected})
        data.update(head=expected, phase='observe')
        return _save(session, data, 'repair_reconciled')
    if snapshot.head_revision != data['head']:
        raise StateConflict('PR head moved outside Factory')
    if snapshot.state == 'merged':
        return _save(session, data, 'pr_merged', status='completed')
    if snapshot.state != 'open':
        return _save(session, data, 'pr_closed_without_merge', status='stopped')
    if snapshot.base_revision != data['base_revision']:
        return _save(session, data, 'base_changed_requires_new_candidate', status='stopped')
    if data['phase'] == 'commit_ready':
        return _update(factory, config, scm, session, data)
    if data['phase'] == 'commit_pending':
        return _save(session, data, 'commit_outcome_unknown', status='stopped')
    trusted = {a.casefold() for a in data['actors']}
    feedback = [f for f in snapshot.feedback if f.author.casefold() in trusted
                and f.id not in data['handled']]
    ignored = [f.id for f in snapshot.feedback if f.author.casefold() not in trusted]
    if not feedback:
        outstanding = any(d.author.casefold() in trusted and d.state == 'changes_requested'
                          for d in snapshot.decisions)
        approved = (not outstanding and any(d.author.casefold() in trusted and
            d.state == 'approved' and d.revision == data['head'] for d in snapshot.decisions))
        return _save(session, data, 'awaiting_merge' if approved else 'awaiting_review',
                     ignored_feedback=ignored)
    if any(f.path is not None and f.path not in config.allowed_paths for f in feedback):
        return _save(session, data, 'feedback_outside_approved_scope', status='stopped')
    unit = data['pr']['external_id']
    event = fingerprint([asdict(f) for f in feedback])
    session.reserve('round', 'review:' + event, unit=unit)
    data.update(phase='evaluating', feedback_ids=[f.id for f in feedback])
    _save(session, data, 'repair_started', status='ready', feedback_ids=data['feedback_ids'],
          ignored_feedback=ignored)
    remote = scm.read_revision(config.repository, data['head'])
    class BudgetedSource:
        def fetch_issue(self, external_id):
            session.api_call()
            return source.fetch_issue(external_id)
    try:
        result = develop_issue(factory=factory, config=config, source=BudgetedSource(), scm=scm,
            implementer=BudgetedModel(implementer, session, role='implementation'),
            reviewer=BudgetedModel(reviewer, session, role='review'), confirmed=True,
            remote_source=remote, evaluate_only=True,
            review_feedback=tuple(asdict(f) for f in feedback))
    except DevelopmentStopped as exc:
        data['failed_run'] = exc.run_id
        _save(session, data, 'candidate_failed', status='stopped', run_id=exc.run_id)
        raise
    data['run_id'] = result['run_id']
    plan = _plan(factory, _artifact(factory, data['run_id']))
    if plan.parent_revision != data['head']:
        raise StateConflict('repair parent differs')
    session.remember_candidate(unit, _candidate_hash(plan))
    data['phase'] = 'commit_pending'
    _save(session, data, 'commit_preparation_reserved', status='ready')
    key = 'commit:' + data['run_id']
    session.reserve('write', key)
    _LocalGuards(factory, config, plan.run_id).verify(plan)
    # Check again after inference. A moving head/base cannot be overwritten.
    current = scm.pull_request_snapshot(config.repository, data['pr']['external_id'])
    if (current.state != 'open' or current.head_revision != data['head']
            or current.base_revision != data['base_revision']):
        raise StateConflict('PR moved during repair')
    commit = scm.prepare_commit(config.repository, parent_revision=data['head'],
        changes=plan.changes, message='Software Factory review: Run ' + plan.run_id)
    if commit.parent_id != data['head']:
        raise StateConflict('prepared commit parent differs')
    session.complete_action(key, asdict(commit))
    data.update(commit=commit.external_id, phase='commit_ready')
    _save(session, data, 'repair_commit_ready', status='ready')
    return _update(factory, config, scm, session, data)


def _update(factory, config, scm, session, data):
    plan = _plan(factory, _artifact(factory, data['run_id']))
    _LocalGuards(factory, config, data['run_id']).verify(plan)
    key = 'update:' + data['run_id']
    session.reserve('write', key)
    data['phase'] = 'update_pending'
    # Save handled IDs before an unknown write; reconciliation cannot repeat a review.
    data['handled'] = list(dict.fromkeys(data['handled'] + data['feedback_ids']))
    _save(session, data, 'branch_cas_reserved', status='ready')
    try:
        scm.compare_update_branch(config.repository, data['branch'], expected=data['head'],
                                  revision=data['commit'])
    except Exception:
        return _save(session, data, 'awaiting_branch_reconciliation')
    if scm.verified_branch_revision(config.repository, data['branch']) != data['commit']:
        return _save(session, data, 'awaiting_branch_reconciliation')
    session.complete_action(key, {'revision': data['commit']})
    data.update(head=data['commit'], phase='observe')
    return _save(session, data, 'repair_submitted')
