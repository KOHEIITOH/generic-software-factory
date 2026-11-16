"""Finite autonomous repair inside one approved Issue, never authority or gate changes."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

from sf_factory.automation_state import AutomationLimits, AutomationSession, fingerprint
from sf_factory.budgeted_model import BudgetedModel
from sf_factory.change_proposal import ChangeProposal, ProposalScope, parse_change_proposal
from sf_factory.file_state import lock_directory
from sf_factory.issue_development import DevelopmentStopped, _artifact, develop_issue
from sf_factory.managed_repository import ManagedHarnessChanged, execution_source
from sf_factory.review_automation import _save
from sf_factory.run_evidence import EvidenceSubject
from sf_factory.run_review import parse_review
from sf_factory.source_snapshot import SourceSnapshotService
from sf_factory.state_store import StateConflict, StatePermissionDenied

LIMITS = AutomationLimits(max_rounds=3, max_model_calls=8, max_seconds=3600)


class ImprovementBlocked(StateConflict):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def terminal(session: AutomationSession) -> dict:
    state = session.snapshot()
    return {'session_id': session.id, 'status': state['status'], **state['data'],
            'reason': state['decisions'][-1]['code'] if state['decisions'] else 'stopped'}


def failure_context(factory, config, run_id: str, attempt: int,
                    session: AutomationSession) -> tuple[dict, dict]:
    value = _artifact(factory, run_id)
    if value['phase'] not in {'started', 'proposed'} \
            or value['config_fingerprint'] != config.fingerprint:
        raise ImprovementBlocked('auto_improvement_candidate_unavailable')
    snapshot, files = SourceSnapshotService(factory).load(run_id)
    scope = ProposalScope(**{**value['scope'],
                            'allowed_paths': tuple(value['scope']['allowed_paths'])})
    if snapshot['fingerprint'] != scope.source_fingerprint:
        raise StateConflict('failed candidate source differs')
    if value['phase'] == 'started':
        responses = [a['receipt']['text'] for k, a in session.snapshot()['actions'].items()
                     if k.startswith('model:implementation-' + str(attempt) + ':')
                     and a['status'] == 'completed']
        if len(responses) != 1:
            raise ImprovementBlocked('auto_improvement_candidate_unavailable')
        raw = responses[0]
        try:
            parse_change_proposal(raw, scope=scope, source_files=files)
        except ValueError:
            facts = {'run_id': run_id, 'attempt': attempt, 'kind': 'candidate',
                     'failed_checks': [], 'must_fix': 0}
            context = {'failure': facts, 'previous_response': raw,
                       'correction': 'Return the requested exact JSON schema and original scope.'}
            if len(json.dumps(context).encode()) > 65536:
                raise ImprovementBlocked('auto_improvement_context_limit') from None
            return context, facts
        raise ImprovementBlocked('auto_improvement_candidate_unavailable')
    proposal = parse_change_proposal(json.dumps(value['proposal']), scope=scope, source_files=files)
    rows = value.get('checks', [])
    expected = {c.id: c.stdout for c in config.checks}
    if len(rows) != len(expected) or {c['check_id'] for c in rows} != set(expected):
        raise ImprovementBlocked('auto_improvement_checks_incomplete')
    if any(c['status'] not in {'succeeded', 'failed', 'timed_out', 'output_limit'}
           or not c['cleaned_up'] or not c['source_unchanged'] for c in rows):
        raise ImprovementBlocked('auto_improvement_execution_unavailable')
    failed = [c['check_id'] for c in rows if c['status'] != 'succeeded'
              or c['exit_code'] != 0 or c['output'] != expected[c['check_id']]]
    findings = []
    if not failed:
        raw = value.get('review_report')
        if not isinstance(raw, str):
            raise ImprovementBlocked('auto_improvement_review_unavailable')
        summary = parse_review(raw, run_id=run_id,
            subject=EvidenceSubject(scope.revision, scope.bundle_hash, proposal.fingerprint),
            required_paths=tuple(c.path for c in proposal.changes))
        if summary.status != 'completed' or not summary.complete or summary.truncated:
            raise ImprovementBlocked('auto_improvement_review_unavailable')
        if summary.must_fix == 0:
            raise StateConflict('no known repairable quality failure')
        findings = json.loads(raw)['findings']
    facts = {'run_id': run_id, 'attempt': attempt,
             'kind': 'checks' if failed else 'review', 'failed_checks': failed,
             'must_fix': sum(f['severity'] == 'must-fix' for f in findings)}
    context = {'failure': facts, 'previous_changes': [asdict(c) for c in proposal.changes],
        'checks': [{k: c[k] for k in ('check_id', 'status', 'exit_code', 'reason', 'output')}
                   for c in rows], 'review_findings': findings}
    if len(json.dumps(context).encode()) > 65536:
        raise ImprovementBlocked('auto_improvement_context_limit')
    return context, facts


def improve_issue(*, factory, config, source, scm, implementer, reviewer,
                  confirmed: bool, trusted_reviewers=()) -> dict:
    if (confirmed is not True or not config.auto_improve or implementer is reviewer
            or factory.root != config.data_root):
        raise StatePermissionDenied('explicit bounded improvement scope required')
    session = AutomationSession(factory.root,
        subject='issue-development:' + config.repository + ':' + config.issue,
        config_fingerprint=fingerprint({'development': config.fingerprint,
                                        'reviewers': trusted_reviewers}), limits=LIMITS)
    lock = factory.root / 'issue-controller-v1'
    lock.mkdir(mode=0o700, exist_ok=True)
    with lock_directory(lock):
        from sf_factory.issue_execution import completed_counterpart
        completed = completed_counterpart(factory.root, config, trusted_reviewers)
        if completed is not None:
            return completed
        if session.snapshot()['status'] in {'stopped', 'completed'}:
            return terminal(session)
        data = session.snapshot()['data'] or {'attempts': [], 'attempt': 1}
        if (type(data.get('attempt')) is not int or not 1 <= data['attempt'] <= LIMITS.max_rounds
                or not isinstance(data.get('attempts'), list) or len(data['attempts']) > 3
                or data.get('phase') not in {None, 'starting', 'running', 'repair_ready'}):
            raise StateConflict('invalid automatic improvement journal; do not reset')
        prior = getattr(scm, 'request_guard', None)
        if hasattr(scm, 'request_guard'):
            def guard(method, path):
                session.api_call(method, path)
                if prior is not None:
                    prior(method, path)
            scm.request_guard = guard
        try:
            return _advance(factory, config, source, scm, implementer, reviewer, session, data)
        except ManagedHarnessChanged:
            return _save(session, data, 'managed_harness_review_required')
        except ImprovementBlocked as exc:
            return _save(session, data, exc.code, status='stopped')
        except Exception:
            if session.snapshot()['status'] not in {'stopped', 'completed'}:
                _save(session, data, 'auto_improvement_stopped', status='stopped')
            return terminal(session)
        finally:
            if hasattr(scm, 'request_guard'):
                scm.request_guard = prior


def _advance(factory, config, source, scm, implementer, reviewer, session, data):
    while True:
        attempt = data['attempt']
        action = 'execute:' + str(attempt)
        resume = None
        if data.get('phase') in {'starting', 'running'}:
            run_id = data.get('run_id')
            if (not run_id or _artifact(factory, run_id)['phase'] not in
                    {'reviewed', 'delivered'}):
                return _save(session, data, 'issue_execution_outcome_unknown', status='stopped')
            resume = run_id
        context = None
        if resume is None:
            if data.get('phase') == 'repair_ready':
                context, _ = failure_context(factory, config,
                    data['attempts'][-1]['run_id'], attempt - 1, session)
            session.reserve('round', 'attempt:' + str(attempt), unit='issue')
            data.update(phase='starting')
            data.pop('run_id', None)
            _save(session, data, 'auto_improvement_attempt_started',
                  status='ready', attempt=attempt)

        def prepared(run_id, sources):
            value = _artifact(factory, run_id)
            baseline = {k: value['scope'][k] for k in ('revision', 'bundle_hash')}
            if data.get('baseline') is not None and data['baseline'] != baseline:
                raise ImprovementBlocked('auto_improvement_baseline_changed')
            data['baseline'] = baseline
            session.reserve('write', action)
            data.update(run_id=run_id, phase='running', requirement_sources=sources)
            _save(session, data, 'issue_run_prepared', status='ready', attempt=attempt)

        def candidate(run_id: str, proposal: ChangeProposal):
            digest = fingerprint([(c.path, hashlib.sha256(c.content.encode()).hexdigest())
                                  for c in sorted(proposal.changes, key=lambda c: c.path)])
            session.remember_candidate('issue', digest)

        try:
            remote = execution_source(factory.root, config.root, config.repository, scm) \
                if resume is None else None
            result = develop_issue(factory=factory, config=config, source=source, scm=scm,
                implementer=BudgetedModel(implementer, session,
                    role='implementation-' + str(attempt), max_output_tokens=32768),
                reviewer=BudgetedModel(reviewer, session, role='review-' + str(attempt),
                                      max_output_tokens=32768),
                confirmed=True, resume=resume, on_prepared=prepared, discover_references=True,
                remote_source=remote, repair_context=context, on_candidate=candidate)
            receipt = {'run_id': result['run_id'], 'outcome': 'delivered'}
            existing = session.snapshot()['actions'][action]
            if existing['status'] == 'pending':
                session.complete_action(action, receipt)
            elif existing['receipt'] != receipt:
                raise StateConflict('delivery receipt differs')
            data.update(run_id=result['run_id'], pull_request=result['pull_request'], phase='done')
            return _save(session, data, 'draft_pr_created', status='completed')
        except DevelopmentStopped as exc:
            if session.snapshot()['status'] in {'stopped', 'completed'}:
                return terminal(session)
            value = _artifact(factory, exc.run_id)
            if value['config_fingerprint'] != config.fingerprint:
                raise StateConflict('failed Run configuration differs')
            if value['phase'] in {'reviewed', 'delivered'}:
                return _save(session, data, 'issue_delivery_reconciliation_required')
            if any(a['kind'] == 'model' and a['status'] == 'pending'
                   for a in session.snapshot()['actions'].values()):
                return _save(session, data, 'auto_improvement_unknown_inference', status='stopped')
            try:
                failed_context, facts = failure_context(factory, config, exc.run_id,
                                                       attempt, session)
            except ImprovementBlocked:
                raise
            except (ValueError, KeyError, StateConflict):
                return _save(session, data, 'auto_improvement_not_repairable', status='stopped')
            if facts['kind'] == 'candidate':
                session.remember_candidate('invalid-response',
                                           fingerprint(failed_context['previous_response']))
            session.complete_action(action, {'run_id': exc.run_id, 'outcome': 'quality_failed'})
            data['attempts'].append(facts)
            if attempt >= LIMITS.max_rounds:
                return _save(session, data, 'auto_improvement_exhausted', status='stopped')
            data.update(attempt=attempt + 1, phase='repair_ready')
            _save(session, data, 'auto_improvement_planned', status='ready', **facts)
