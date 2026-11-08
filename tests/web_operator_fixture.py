"""Browser-only fixture. Operator API and persistence real; workflow effects simulated."""
import hashlib
import json
import os
import sys
from dataclasses import asdict, replace
from pathlib import Path

import pytest
import uvicorn
from test_issue_development import flow

from sf_factory.automation_state import AutomationSession, fingerprint
from sf_factory.requirement_workflow import PLAN_LIMITS
from sf_factory.web_api import create_app
from sf_factory.web_jobs import WebJobs
from sf_factory.web_operator import OperatorProfiles, WebOperator


def main():
    directory, port = Path(sys.argv[1]), int(sys.argv[2])
    patch = pytest.MonkeyPatch()
    args = flow.__wrapped__(directory, patch)
    config = args['config']
    path = directory / 'operator.json'
    path.write_text(json.dumps(asdict(config), default=str))
    OperatorProfiles(config.data_root).register(path, 'Browser fixture')
    patch.setattr('sf_factory.operator_diagnostics.diagnose_profile', lambda *a, **k: {
        'can_attempt': True, 'checked_at': '2026-11-08T00:00:00+00:00', 'checks': [
            {'id': 'configuration', 'status': 'ok', 'detail': '登録設定を確認しました。',
             'remedy': ''},
            {'id': 'model_authorization', 'status': 'unknown',
             'detail': 'AI認証は未確認です。推論しません。',
             'remedy': 'PCの認証を確認してください。'}]})
    patch.setattr('sf_factory.integration_defaults.list_open_issues',
                  lambda repository, page: ([args['source'].fetch_issue('1')], False))
    auth = WebOperator(f'http://127.0.0.1:{port}')
    (directory / 'operator-link').write_text(auth.origin + '/#operator=' + auth.token)
    leases = {}
    advances = []
    def spawn(store, key):
        import fcntl

        from test_requirement_workflow import plan_document

        from sf_factory.plan_preview import approval_fingerprint
        job = store.get(key)
        if job['action'] == 'develop':
            selected = replace(config, issue=job['issue_id'])
            session = AutomationSession(config.data_root,
                subject='issue-development:' + selected.repository + ':' + selected.issue,
                config_fingerprint=fingerprint({'development': selected.fingerprint,
                                                'reviewers': tuple(job['reviewers'])}))
            if session.snapshot()['status'] != 'completed':
                session.save({'run_id': 'e' * 32, 'pull_request': {
                    'external_id': '99', 'url': 'https://github.com/fixture/repo/pull/99'}},
                    expected_version=session.snapshot()['version'], status='completed',
                    decision='draft_pr_created')
            store.change(key, code='worker_step_finished', status='finished',
                         result={'status': 'completed', 'reason': 'draft_pr_created'})
            return
        store.change(key, code='worker_claimed', status='running')
        lease = store.lease(key)
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        leases[key] = lease
        session = AutomationSession(config.data_root,
            subject='requirements:' + config.repository + ':' + config.issue,
            config_fingerprint=fingerprint({'development': config.fingerprint, 'reviewers': ()}),
            limits=PLAN_LIMITS)
        state = session.snapshot()
        if not state['data']:
            plan = plan_document()
            plan['requirements'][0]['sources'] = ['docs/requirements.md']
            session.reserve('model', 'fixture-plan', tokens=100)
            session.complete_action('fixture-plan', {'fixture': True})
            data = {'require_plan_approval': True, 'source_revision': 'b' * 40,
                'source_fingerprint': 'c' * 64, 'local_revision': 'd' * 40,
                'parent': asdict(args['source'].fetch_issue('1')),
                'requirement_sources': {'mode': 'auto', 'revision': 'b' * 40,
                    'fingerprint': 'e' * 64, 'documents': [{'path': 'docs/requirements.md',
                    'sha256': hashlib.sha256(b'PRIVATE_REQUIREMENT_CONTENT').hexdigest(),
                    'bytes': 27, 'reason': 'requirement_document_convention'}]},
                'planning_review': {'report': {'requirements_status': 'ready',
                    'interpretation': '加算APIを維持し、受入条件を確認する2単位に分割します。',
                    'source_assessments': [{'source_id': 'issue', 'status': 'supporting',
                        'reason': 'PRIVATE_REASON'}, {'source_id': 'docs/requirements.md',
                        'status': 'requirements', 'reason': 'PRIVATE_REASON'}]}},
                'plan': plan, 'plan_fingerprint': fingerprint(plan), 'children': {}}
            session.save(data, expected_version=session.snapshot()['version'])
            data['plan_approval'] = {'status': 'pending',
                                    'fingerprint': approval_fingerprint(session.snapshot())}
            session.save(data, expected_version=session.snapshot()['version'], status='waiting',
                         decision='plan_approval_requested')
        data = session.snapshot()['data']
        action = store.get(key)['action']
        reason = 'awaiting_plan_approval'
        if action == 'approve':
            data['plan_approval']['status'] = 'approved'
            data['children'] = {
                'first': {'status': 'pending', 'issue': {'external_id': '2',
                    'external_url': 'https://github.com/fixture/repo/issues/2'}},
                'second': {'status': 'pending', 'issue': {'external_id': '3'}}}
            reason = 'plan_ready'
        elif data['plan_approval']['status'] == 'approved' and action == 'advance':
            advances.append(key)
            data['children']['first'].update(status='pr_open', run_id='d' * 32,
                pull_request={'url': 'https://github.com/fixture/repo/pull/1'})
            reason = ('child_pr_submitted' if len(advances) == 1 else
                      'child_awaiting_review_or_merge')
        session.save(data, expected_version=session.snapshot()['version'], status='waiting',
                     decision=reason)
        if action != 'advance' or not advances or len(advances) > 1:
            store.change(key, code='worker_step_finished', status='finished',
                         result={'status': 'waiting', 'reason': reason})
            os.close(leases.pop(key))
    patch.setattr(WebJobs, 'spawn', spawn)
    original_stop = WebJobs.stop
    def stop(store, key):
        original_stop(store, key)
        if key in leases:
            os.close(leases.pop(key))
        return store.change(key, code='worker_step_finished', status='stopped',
                            result={'status': 'stopped', 'reason': 'operator_or_execution_stopped'})
    patch.setattr(WebJobs, 'stop', stop)
    app = create_app(data_dir=config.data_root,
                     static_dir=Path(__file__).resolve().parents[1] / 'web/dist', operator=auth)
    uvicorn.run(app, host='127.0.0.1', port=port, access_log=False, proxy_headers=False)


if __name__ == '__main__':
    main()
