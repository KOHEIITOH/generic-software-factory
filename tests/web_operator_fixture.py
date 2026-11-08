"""Browser-only fixture. Operator API and persistence real; workflow effects simulated."""
import json
import os
import sys
from dataclasses import asdict
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
    auth = WebOperator(f'http://127.0.0.1:{port}')
    (directory / 'operator-link').write_text(auth.origin + '/#operator=' + auth.token)
    leases = []
    def spawn(store, key):
        import fcntl
        store.change(key, code='worker_claimed', status='running')
        lease = store.lease(key)
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        leases.append(lease)
        session = AutomationSession(config.data_root,
            subject='requirements:' + config.repository + ':' + config.issue,
            config_fingerprint=fingerprint({'development': config.fingerprint, 'reviewers': ()}),
            limits=PLAN_LIMITS)
        state = session.snapshot()
        if not state['data']:
            session.reserve('model', 'fixture-plan', tokens=100)
            session.complete_action('fixture-plan', {'fixture': True})
            session.save({'children': {'first': {'status': 'pr_open', 'run_id': 'd' * 32,
                'issue': {'external_id': '2', 'external_url': 'https://github.com/fixture/repo/issues/2'},
                'pull_request': {'url': 'https://github.com/fixture/repo/pull/1'}},
                'second': {'status': 'pending', 'issue': {'external_id': '3'}}}},
                expected_version=session.snapshot()['version'], status='waiting',
                decision='child_pr_submitted')
        if len(leases) > 1:
            store.change(key, code='worker_step_finished', status='finished',
                         result={'status': 'waiting', 'reason': 'child_awaiting_review_or_merge'})
            os.close(lease)
    patch.setattr(WebJobs, 'spawn', spawn)
    # Stop acknowledgement is simulated; no worker/model/SCM/container is started.
    original_stop = WebJobs.stop
    def stop(store, key):
        original_stop(store, key)
        return store.change(key, code='worker_step_finished', status='stopped',
                            result={'status': 'stopped', 'reason': 'operator_or_execution_stopped'})
    patch.setattr(WebJobs, 'stop', stop)
    app = create_app(data_dir=config.data_root,
                     static_dir=Path(__file__).resolve().parents[1] / 'web/dist', operator=auth)
    uvicorn.run(app, host='127.0.0.1', port=port, access_log=False, proxy_headers=False)


if __name__ == '__main__':
    main()
