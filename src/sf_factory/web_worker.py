"""Private finite worker. No HTTP args become commands, paths, or model prompts."""
from __future__ import annotations

import fcntl
import os
import re
import signal
import sys
from collections.abc import Callable
from pathlib import Path

from sf_factory.file_state import lock_directory
from sf_factory.issue_development_cli import execute_local_development
from sf_factory.operation_control import OperationStopped, operation_control
from sf_factory.web_jobs import WebJobs
from sf_factory.web_operator import OperatorProfiles


def public_result(value: dict) -> dict:
    result = {'status': value.get('status', 'stopped')}
    if result['status'] not in {'ready', 'waiting', 'completed', 'stopped', 'candidate_reviewed',
                                'draft_pr_created', 'blocked'}:
        result['status'] = 'stopped'
    for key in ('session_id', 'run_id'):
        if isinstance(value.get(key), str) and re.fullmatch('[a-f0-9]{32}', value[key]):
            result[key] = value[key]
    reason = value.get('reason')
    if isinstance(reason, str) and re.fullmatch('[a-z][a-z0-9_]{0,95}', reason):
        result['reason'] = reason
    return result


def run_job(root: Path, key: str, *, executor: Callable = execute_local_development) -> bool:
    jobs = WebJobs(root)
    lease = jobs.lease(key)
    try:
        try:
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        worker = jobs.root / 'web-worker-v1'
        worker.mkdir(mode=0o700, exist_ok=True)
        with lock_directory(worker, lock_timeout=0.1):
            job = jobs.get(key)
            if job['status'] != 'queued' or job['stop_requested']:
                return False
            jobs.change(key, code='worker_claimed', status='running')
            profiles = OperatorProfiles(root)
            def checkpoint():
                current = jobs.get(key)
                if current['stop_requested']:
                    raise OperationStopped('operator requested stop')
                profiles.get(job['profile_id'], job['config_fingerprint'])
            def deadline(signum, frame):
                raise OperationStopped('finite worker deadline reached')
            previous = signal.signal(signal.SIGALRM, deadline)
            signal.alarm(3600)
            try:
                with operation_control(checkpoint):
                    checkpoint()
                    profile, _ = profiles.get(job['profile_id'], job['config_fingerprint'])
                    result = executor(config_path=Path(profile['path']), confirmed=True,
                        confirm_bedrock=job['confirm_bedrock'],
                        expected_fingerprint=job['config_fingerprint'],
                        workflow_action=job['action'] if job['action'] != 'review' else None,
                        review_run=job['run_id'], trusted_reviewers=tuple(job['reviewers']),
                        require_plan_approval=True, approved_plan=job.get('approved_plan'))
                result = public_result(result)
            except Exception:
                # No SDK exceptions, source, config paths, stdout or secret-bearing logs in HTTP.
                result = {'status': 'stopped', 'reason': 'operator_or_execution_stopped'}
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, previous)
            stopped = jobs.get(key)['stop_requested']
            jobs.change(key, code='worker_step_finished',
                        status='stopped' if stopped else 'finished', result=result)
            return True
    finally:
        os.close(lease)


def main() -> int:
    if len(sys.argv) != 3:
        return 2
    try:
        return 0 if run_job(Path(sys.argv[1]), sys.argv[2]) else 1
    except Exception:
        # If durable state cannot be read/written, leave the job for lease-loss reconciliation.
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
