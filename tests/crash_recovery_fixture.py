"""Trusted test process. File-backed simulated services; never real external writes."""
import json
import os
import signal
import sys
from pathlib import Path

from test_delivery_plan import fixture
from test_draft_delivery import COMMIT, PR, SCM, Guards

from sf_factory.automation_state import AutomationSession
from sf_factory.budgeted_model import BudgetedModel
from sf_factory.delivery_plan import build_delivery_plan
from sf_factory.draft_delivery import deliver_draft
from sf_factory.file_delivery_state import FileDeliveryState
from sf_factory.file_state import lock_directory
from sf_factory.web_worker import run_job


def main():
    root, mode, recover = Path(sys.argv[1]), sys.argv[2], sys.argv[3] == 'recover'
    def effect(kind):
        with (root / 'effects').open('a') as stream:
            stream.write(kind + '\n')
            stream.flush()
            os.fsync(stream.fileno())
    def crashpoint(kind):
        if not recover and mode == kind:
            (root / 'ready').write_text(kind)
            while True:
                signal.pause()
    if mode == 'model':
        session = AutomationSession(root, subject='crash-model', config_fingerprint='f' * 64)
        class Provider:
            def generate(self, prompt):
                effect('model')
                crashpoint('model')
                raise AssertionError('unknown model request must never be replayed')
        def execute(**kwargs):
            BudgetedModel(Provider(), session, role='fixture').generate('frozen prompt')
            return {'status': 'completed'}
        run_job(root, 'b' * 32 if recover else 'a' * 32, executor=execute)
        return
    if mode.startswith('atomic'):
        import sf_factory.file_document as document
        original = document.os.replace
        def replace(*args, **kwargs):
            if mode == 'atomic-before':
                crashpoint(mode)
            original(*args, **kwargs)
            if mode == 'atomic-after':
                crashpoint(mode)
        document.os.replace = replace
        with lock_directory(root / 'atomic') as fd:
            document.write_document(fd, {'generation': 2})
        return
    class Remote(SCM):
        def prepare_commit(self, *a, **k):
            effect('commit')
            crashpoint('commit')
            return COMMIT
        def ensure_branch(self, *a, **k):
            effect('branch')
            crashpoint('branch')
        def verified_branch_revision(self, *a, **k):
            return COMMIT.external_id if 'branch' in (root / 'effects').read_text() else None
        def create_draft_pull_request(self, *a, **k):
            effect('pr')
            crashpoint('pr')
            return PR
        def find_draft_pull_request(self, *a, **k):
            return PR if 'pr' in (root / 'effects').read_text().splitlines() else None
    try:
        deliver_draft(plan=build_delivery_plan(**fixture()), state=FileDeliveryState(root),
                      scm=Remote(), guards=Guards())
        result = 'delivered'
    except Exception:
        result = 'stopped'
    (root / 'outcome').write_text(json.dumps({'status': result}))


if __name__ == '__main__':
    main()
