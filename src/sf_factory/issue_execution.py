"""One selected Issue to one Draft PR, with durable finite execution receipts."""
from __future__ import annotations

from sf_factory.automation_state import AutomationSession, fingerprint
from sf_factory.budgeted_model import BudgetedModel
from sf_factory.development_config import DevelopmentConfig
from sf_factory.factory import Factory
from sf_factory.file_state import lock_directory
from sf_factory.issue_development import DevelopmentStopped, _artifact, develop_issue
from sf_factory.managed_repository import ManagedHarnessChanged
from sf_factory.model_provider import ModelProvider
from sf_factory.review_automation import _save
from sf_factory.source_control import ChangeSourceControl
from sf_factory.state_store import StatePermissionDenied
from sf_factory.task_sources import TaskSourceAdapter


def execute_issue(*, factory: Factory, config: DevelopmentConfig, source: TaskSourceAdapter,
                  scm: ChangeSourceControl, implementer: ModelProvider, reviewer: ModelProvider,
                  confirmed: bool, trusted_reviewers: tuple[str, ...] = ()) -> dict:
    if not confirmed or implementer is reviewer or factory.root != config.data_root:
        raise StatePermissionDenied('scoped confirmation and independent providers required')
    session = AutomationSession(factory.root,
        subject='issue-development:' + config.repository + ':' + config.issue,
        config_fingerprint=fingerprint({'development': config.fingerprint,
                                        'reviewers': trusted_reviewers}))
    directory = factory.root / 'issue-controller-v1'
    directory.mkdir(mode=0o700, exist_ok=True)
    with lock_directory(directory):
        state = session.snapshot()
        if state['status'] in {'stopped', 'completed'}:
            return {'session_id': session.id, 'status': state['status'], **state['data']}
        data = state['data']
        prior_guard = getattr(scm, 'request_guard', None)
        if hasattr(scm, 'request_guard'):
            def guard(method, path):
                session.api_call(method, path)
                if prior_guard is not None:
                    prior_guard(method, path)
            setattr(scm, 'request_guard', guard)
        try:
            session.reserve('round', 'attempt:' + str(state['version']), unit='issue')
            resume = None
            if 'execute' in state['actions']:
                # Unknown inference/commit never creates another Run. Reviewed delivery
                # can use the existing readback/reconciliation protocol without inference.
                run_id = data.get('run_id')
                if (run_id is None or
                        _artifact(factory, run_id)['phase'] not in {'reviewed', 'delivered'}):
                    return _save(session, data, 'issue_execution_outcome_unknown', status='stopped')
                resume = run_id
            def prepared(run_id, sources):
                session.reserve('write', 'execute')
                data['run_id'] = run_id
                data['requirement_sources'] = sources
                _save(session, data, 'issue_run_prepared', status='ready')
            from sf_factory.managed_repository import execution_source
            remote = (execution_source(factory.root, config.root, config.repository, scm)
                      if resume is None else None)
            result = develop_issue(factory=factory, config=config, source=source, scm=scm,
                implementer=BudgetedModel(implementer, session, role='implementation',
                                          max_output_tokens=32768),
                reviewer=BudgetedModel(reviewer, session, role='review', max_output_tokens=32768),
                confirmed=True, resume=resume, on_prepared=prepared, discover_references=True,
                remote_source=remote)
            data.update(run_id=result['run_id'], pull_request=result['pull_request'])
            action = session.snapshot()['actions']['execute']
            if action['status'] == 'pending':
                session.complete_action('execute', {'run_id': result['run_id']})
            elif action['receipt'] != {'run_id': result['run_id']}:
                raise StatePermissionDenied('execution receipt differs')
            return _save(session, data, 'draft_pr_created', status='completed')
        except ManagedHarnessChanged:
            return _save(session, data, 'managed_harness_review_required')
        except DevelopmentStopped as exc:
            current = session.snapshot()
            if current['status'] == 'stopped':
                return {'session_id': session.id, 'status': 'stopped', **current['data']}
            artifact = _artifact(factory, exc.run_id)
            if artifact['config_fingerprint'] != config.fingerprint:
                return _save(session, data, 'repository_delivery_blocked')
            data['run_id'] = exc.run_id
            recoverable = artifact['phase'] in {'reviewed', 'delivered'}
            return _save(session, data,
                'issue_delivery_reconciliation_required' if recoverable else 'issue_quality_failed',
                status='waiting' if recoverable else 'stopped')
        except Exception:
            if session.snapshot()['status'] not in {'stopped', 'completed'}:
                if 'execute' not in session.snapshot()['actions']:
                    return _save(session, data, 'issue_prerequisites_unavailable')
                return _save(session, data, 'issue_execution_stopped', status='stopped')
            return {'session_id': session.id, 'status': 'stopped', **session.snapshot()['data']}
        finally:
            if hasattr(scm, 'request_guard'):
                setattr(scm, 'request_guard', prior_guard)
