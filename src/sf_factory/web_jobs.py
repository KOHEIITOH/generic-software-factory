"""Durable single-worker jobs; process leases, not PID guesses or automatic replay."""
from __future__ import annotations

import fcntl
import os
import re
import stat
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from sf_factory.automation_state import AutomationSession, fingerprint
from sf_factory.file_document import read_document, write_document
from sf_factory.file_state import lock_directory
from sf_factory.plan_preview import plan_preview
from sf_factory.source_snapshot import _sync_directory
from sf_factory.state_store import StateConflict, StatePermissionDenied
from sf_factory.web_operator import OperatorProfiles

ACTIVE = {'queued', 'running', 'stopping'}


def now() -> str:
    return datetime.now(UTC).isoformat()


class WebJobs:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.directory = self.root / 'web-jobs-v1'
        try:
            self.directory.mkdir(mode=0o700)
            created = True
        except FileExistsError:
            created = False
        self.leases = self.directory / 'leases'
        self.leases.mkdir(mode=0o700, exist_ok=True)
        with lock_directory(self.directory) as fd:
            if created:
                write_document(fd, {'schema_version': 1, 'jobs': {}})
            self._read(fd)
        if created:
            _sync_directory(self.root)

    @staticmethod
    def _read(fd):
        state = read_document(fd)
        if (set(state) != {'schema_version', 'jobs'} or type(state['schema_version']) is not int
                or state['schema_version'] != 1
                or not isinstance(state['jobs'], dict) or len(state['jobs']) > 500):
            raise StateConflict('invalid Web job journal; do not reset')
        for key, job in state['jobs'].items():
            if (not re.fullmatch('[a-f0-9]{32}', key) or job.get('id') != key
                    or job.get('status') not in ACTIVE | {'finished', 'stopped', 'interrupted'}
                    or not isinstance(job.get('events'), list) or len(job['events']) > 64
                    or not re.fullmatch('[a-f0-9]{32}', job.get('profile_id', ''))
                    or not re.fullmatch('[a-f0-9]{32}', job.get('session_id', ''))
                    or not re.fullmatch('[a-f0-9]{64}', job.get('config_fingerprint', ''))
                    or job.get('action') not in {'plan', 'advance', 'review', 'approve', 'develop'}
                    or ((job.get('action') == 'develop') != (job.get('issue_id') is not None))
                    or (job.get('action') == 'develop' and
                        (not isinstance(job.get('issue_id'), str) or
                         not re.fullmatch('[1-9][0-9]{0,18}', job['issue_id'])))
                    or type(job.get('stop_requested')) is not bool
                    or (job.get('action') == 'approve' and
                        not re.fullmatch('[a-f0-9]{64}', job.get('approved_plan', '')))):
                raise StateConflict('invalid Web job')
        return state

    def lease(self, key: str) -> int:
        if not re.fullmatch('[a-f0-9]{32}', key):
            raise ValueError('exact job identity required')
        directory = os.open(self.leases, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            fd = os.open(key, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                         0o600, dir_fd=directory)
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                os.close(fd)
                raise StateConflict('invalid worker lease')
            return fd
        finally:
            os.close(directory)

    def live(self, key: str) -> bool:
        fd = self.lease(key)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            fcntl.flock(fd, fcntl.LOCK_UN)
            return False
        finally:
            os.close(fd)

    def _reconcile(self, state):
        for job in state['jobs'].values():
            age = (datetime.now(UTC) - datetime.fromisoformat(job['updated_at'])).total_seconds()
            if job['status'] in ACTIVE and age > 10 and not self.live(job['id']):
                job.update(status='interrupted', updated_at=now())
                job['events'].append({'at': now(), 'code': 'worker_lease_lost'})

    def enqueue(self, *, profile_id: str, config_fingerprint: str, action: str,
                request_id: str, confirm_bedrock: bool, run_id: str | None = None,
                reviewers: tuple[str, ...] = (),
                approved_plan: str | None = None,
                issue_id: str | None = None) -> tuple[dict, bool]:
        if (action not in {'plan', 'advance', 'review', 'approve', 'develop'}
                or not re.fullmatch('[a-f0-9]{32}', request_id)
                or (action == 'review') != (run_id is not None)
                or (run_id is not None and not re.fullmatch('[a-f0-9]{32}', run_id))
                or len(reviewers) > 16 or any(not re.fullmatch(r'[A-Za-z0-9_\[\]-]{1,128}', a)
                                            for a in reviewers)):
            raise ValueError('bounded registered workflow action required')
        if ((action == 'develop') != (issue_id is not None)
                or (issue_id is not None and not re.fullmatch('[1-9][0-9]{0,18}', issue_id))):
            raise ValueError('exact selected Issue identity required')
        if ((action == 'approve') != (approved_plan is not None)
                or (approved_plan is not None and not re.fullmatch('[a-f0-9]{64}', approved_plan))):
            raise ValueError('exact plan approval fingerprint required')
        _, config = OperatorProfiles(self.root).get(profile_id, config_fingerprint)
        if config.provider == 'bedrock' and action != 'approve' and confirm_bedrock is not True:
            raise StatePermissionDenied('explicit Bedrock inference consent required')
        command = {'profile_id': profile_id, 'config_fingerprint': config_fingerprint,
                   'action': action, 'run_id': run_id, 'reviewers': list(reviewers),
                   'confirm_bedrock': confirm_bedrock}
        if approved_plan is not None:
            command['approved_plan'] = approved_plan
        if issue_id is not None:
            config = replace(config, issue=issue_id)
            command['issue_id'] = issue_id
        subject = ('review:' + config.repository + ':' + str(run_id) if action == 'review' else
                   'issue-development:' + config.repository + ':' + config.issue
                   if action == 'develop' else
                   'requirements:' + config.repository + ':' + config.issue)
        session_id = fingerprint({'subject': subject, 'config': fingerprint({
            'development': config.fingerprint, 'reviewers': reviewers})})[:32]
        with lock_directory(self.directory) as fd:
            state = self._read(fd)
            self._reconcile(state)
            prior = state['jobs'].get(request_id)
            if prior is not None:
                if any(prior[k] != v for k, v in command.items()):
                    raise StateConflict('request identity already used for another scope')
                return prior, False
            if approved_plan is not None:
                from sf_factory.plan_preview import approval_fingerprint
                path = self.root / 'automation-v1' / session_id
                if not path.is_dir():
                    raise StateConflict('no plan is awaiting approval')
                with lock_directory(path) as document:
                    workflow = AutomationSession._read(document)
                approval = workflow['data'].get('plan_approval')
                if (workflow['status'] in {'completed', 'stopped'} or approval is None
                        or approved_plan != approval['fingerprint']
                        or approved_plan != approval_fingerprint(workflow)):
                    raise StateConflict('plan approval scope changed')
            if any(j['profile_id'] == profile_id and
                   j['config_fingerprint'] == config_fingerprint and
                   j['reviewers'] != list(reviewers) for j in state['jobs'].values()):
                raise StateConflict('reviewer scope is frozen for this registered configuration')
            if any(j['status'] in ACTIVE for j in state['jobs'].values()):
                raise StateConflict('another Web step is active; wait or request stop')
            if len(state['jobs']) >= 500:
                raise StateConflict('Web job history limit reached; retain existing evidence')
            value = {'id': request_id, **command, 'created_at': now(), 'updated_at': now(),
                     'status': 'queued', 'stop_requested': False, 'session_id': session_id,
                     'result': None, 'events': [{'at': now(), 'code': 'operator_step_approved'}]}
            state['jobs'][request_id] = value
            write_document(fd, state)
        return value, True

    def list(self) -> list[dict]:
        with lock_directory(self.directory) as fd:
            state = self._read(fd)
            self._reconcile(state)
            write_document(fd, state)
            return sorted(state['jobs'].values(),
                          key=lambda job: (job['created_at'], job['id']), reverse=True)

    def get(self, key: str) -> dict:
        if not re.fullmatch('[a-f0-9]{32}', key):
            raise ValueError('exact job identity required')
        with lock_directory(self.directory) as fd:
            state = self._read(fd)
            if key not in state['jobs']:
                raise StateConflict('unknown Web job')
            return state['jobs'][key]

    def change(self, key: str, *, code: str, **updates) -> dict:
        with lock_directory(self.directory) as fd:
            state = self._read(fd)
            job = state['jobs'][key]
            job.update(**updates, updated_at=now())
            job['events'].append({'at': now(), 'code': code})
            write_document(fd, state)
            return job

    def stop(self, key: str) -> dict:
        with lock_directory(self.directory) as fd:
            state = self._read(fd)
            job = state['jobs'].get(key)
            if job is None:
                raise StateConflict('unknown Web job')
            if job['status'] not in ACTIVE or job['stop_requested']:
                return job
            job.update(stop_requested=True,
                       status='stopped' if job['status'] == 'queued' else 'stopping',
                       updated_at=now())
            job['events'].append({'at': now(), 'code': 'operator_stop_requested'})
            write_document(fd, state)
            return job

    def spawn(self, key: str) -> None:
        try:
            subprocess.Popen([sys.executable, '-I', '-m', 'sf_factory.web_worker',
                              str(self.root), key], cwd=self.root, start_new_session=True,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, close_fds=True)
        except OSError:
            self.change(key, code='worker_launch_failed', status='interrupted')

    def progress(self, key: str) -> dict | None:
        path = self.root / 'automation-v1' / self.get(key)['session_id']
        if not path.exists():
            return None
        with lock_directory(path) as fd:
            state = AutomationSession._read(fd)
        data = state['data']
        children = []
        for child, value in data.get('children', {}).items():
            children.append({'id': child, 'issue_id': value['issue']['external_id'],
                'issue_url': value['issue'].get('external_url'), 'status': value['status'],
                'run_id': value.get('run_id'),
                'pr_url': value.get('pull_request', {}).get('url')})
        sources = data.get('requirement_sources')
        source_summary = None
        if sources is not None:
            report = data.get('planning_review', {}).get('report', {})
            source_summary = {k: sources[k] for k in
                ('mode', 'revision', 'fingerprint', 'documents')}
            source_summary['review_status'] = report.get(
                'requirements_status', report.get('status'))
            source_summary['assessments'] = [{'source_id': a['source_id'], 'status': a['status']}
                for a in report.get('source_assessments', [])]
            source_summary['requirements'] = [
                {'id': r['id'], 'sources': r.get('sources', []), 'children': [c['id']
                    for c in data.get('plan', {}).get('children', [])
                    if r['id'] in c['requirement_ids']]}
                for r in data.get('plan', {}).get('requirements', [])]
        return {'id': self.get(key)['session_id'], 'status': state['status'],
                'counts': state['counts'], 'limits': state['limits'], 'rounds': state['rounds'],
                'expires_at': state['expires_at'], 'children': children,
                'requirement_sources': source_summary,
                'plan_preview': plan_preview(state),
                'run_id': data.get('run_id'),
                'pr_url': data.get('pull_request', {}).get('url'),
                'decisions': [{'at': d['at'], 'code': d['code']} for d in state['decisions'][-20:]]}
