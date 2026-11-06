"""Harness decisions and prepared Runs in a single locked File document."""
from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from sf_factory.harness_approval import HarnessApprovalRequest, HarnessApprovalStore, _utc
from sf_factory.state_store import StateConflict, StatePermissionDenied

if TYPE_CHECKING:
    from sf_factory.file_dashboard import FileDashboardFactory


def empty_harness() -> dict:
    return {'approvals': {}, 'approval_events': {}, 'task_projects': {}, 'manifests': {}}


def validate_harness_state(state: dict) -> None:
    """Reject unknown structure and inconsistent decision/Run relationships."""
    harness = state['harness']
    if set(harness) != set(empty_harness()) or not all(isinstance(v, dict)
                                                     for v in harness.values()):
        raise ValueError('invalid Harness collections')
    for task, project in harness['task_projects'].items():
        if not isinstance(task, str) or not task or project not in state['projects']:
            raise ValueError('invalid Task/Project association')
    if set(harness['approvals']) != set(harness['approval_events']):
        raise ValueError('missing approval audit')
    for key, row in harness['approvals'].items():
        if (uuid.UUID(hex=key).hex != key or set(row) != {
            'request', 'reviewer', 'approved', 'created_at', 'expires_at', 'revoked', 'consumed'
        } or any(type(row[k]) is not bool for k in ('approved', 'revoked', 'consumed'))):
            raise ValueError('invalid approval record')
        request = HarnessApprovalRequest(**json.loads(row['request']))
        if row['request'] != HarnessApprovalStore._request(request):
            raise ValueError('noncanonical approval request')
        HarnessApprovalStore._actor(row['reviewer'])
        created = _utc(datetime.fromisoformat(row['created_at']))
        expires = _utc(datetime.fromisoformat(row['expires_at']))
        if not created < expires <= created + timedelta(hours=24):
            raise ValueError('invalid decision lifetime')
        events = harness['approval_events'][key]
        expected = 'approved' if row['approved'] else 'rejected'
        if (not isinstance(events, list) or not events or events[0] != {
            'event': expected, 'actor': row['reviewer'], 'at': row['created_at']
        }):
            raise ValueError('invalid initial approval event')
        for event in events:
            if set(event) != {'event', 'actor', 'at'}:
                raise ValueError('invalid approval event')
            HarnessApprovalStore._actor(event['actor'])
            _utc(datetime.fromisoformat(event['at']))
        names = [event['event'] for event in events]
        if (names.count('consumed') != int(row['consumed'])
                or names.count('revoked') != int(row['revoked'])
                or any(name not in {expected, 'consumed', 'revoked'} for name in names)
                or names.count(expected) != 1 or (row['consumed'] and not row['approved'])):
            raise ValueError('inconsistent decision audit')
    used = set()
    for run_id, entry in harness['manifests'].items():
        if set(entry) != {'approval_id', 'manifest'}:
            raise ValueError('invalid Run manifest entry')
        approval = entry['approval_id']
        row = harness['approvals'][approval]
        manifest = json.loads(entry['manifest'])
        run = state['runs'][run_id]
        composition = json.dumps(manifest['composition'], sort_keys=True,
                                 separators=(',', ':'), ensure_ascii=True)
        request = json.loads(row['request'])
        if (approval in used or not row['consumed'] or manifest['schema_version'] != 1
                or manifest['request'] != request or run['task_id'] != request['task_id']
                or hashlib.sha256(composition.encode()).hexdigest() != request['bundle_hash']):
            raise ValueError('inconsistent approved Run manifest')
        used.add(approval)
    for run_id, run in state['runs'].items():
        if run['status'] == 'prepared' and run_id not in harness['manifests']:
            raise ValueError('prepared Run requires an approved manifest')


class FileApprovalDecisions:
    def __init__(self, factory: FileDashboardFactory,
                 *, clock: Callable[[], datetime] | None = None):
        self.factory = factory
        self.clock = clock or (lambda: datetime.now(UTC))

    def record(self, request: HarnessApprovalRequest, *, reviewer: str, approved: bool,
               expires_at: datetime) -> str:
        HarnessApprovalStore._actor(reviewer)
        if type(approved) is not bool:
            raise ValueError('explicit boolean decision required')
        now, expiry = _utc(self.clock()), _utc(expires_at)
        if not now < expiry <= now + timedelta(hours=24):
            raise ValueError('expiry must be in the next 24 hours')
        approval = uuid.uuid4().hex
        with self.factory._document(edit=True) as state:
            harness = state['harness']
            if approval in harness['approvals']:
                raise StateConflict('approval identity already exists')
            harness['approvals'][approval] = {
                'request': HarnessApprovalStore._request(request), 'reviewer': reviewer,
                'approved': approved, 'created_at': now.isoformat(),
                'expires_at': expiry.isoformat(), 'revoked': False, 'consumed': False,
            }
            harness['approval_events'][approval] = [{
                'event': 'approved' if approved else 'rejected', 'actor': reviewer,
                'at': now.isoformat(),
            }]
        return approval

    def _consume(self, state: dict, approval_id: str, request: HarnessApprovalRequest,
                 *, controller: str) -> None:
        HarnessApprovalStore._actor(controller)
        now = _utc(self.clock())
        row = state['harness']['approvals'].get(approval_id)
        if (row is None or row['request'] != HarnessApprovalStore._request(request)
                or not row['approved'] or row['revoked'] or row['consumed']
                or datetime.fromisoformat(row['expires_at']) <= now
                or datetime.fromisoformat(row['created_at']) > now):
            raise StatePermissionDenied('no matching active Harness approval')
        row['consumed'] = True
        state['harness']['approval_events'][approval_id].append({
            'event': 'consumed', 'actor': controller, 'at': now.isoformat(),
        })

    def consume(self, approval_id: str, request: HarnessApprovalRequest,
                *, controller: str) -> None:
        with self.factory._document(edit=True) as state:
            self._consume(state, approval_id, request, controller=controller)

    def revoke(self, approval_id: str, *, reviewer: str) -> None:
        HarnessApprovalStore._actor(reviewer)
        with self.factory._document(edit=True) as state:
            row = state['harness']['approvals'].get(approval_id)
            if row is None or row['revoked']:
                raise ValueError('active approval not found')
            row['revoked'] = True
            state['harness']['approval_events'][approval_id].append({
                'event': 'revoked', 'actor': reviewer, 'at': _utc(self.clock()).isoformat(),
            })

    def events(self, approval_id: str) -> tuple[dict, ...]:
        with self.factory._document() as state:
            return tuple(state['harness']['approval_events'].get(approval_id, []))


class FileTaskProjects:
    def __init__(self, factory: FileDashboardFactory):
        self.factory = factory

    def assign(self, task_id: str, project_id: str) -> None:
        self.factory.task_store.get_task(task_id)
        with self.factory._document(edit=True) as state:
            if project_id not in state['projects']:
                raise ValueError('project not found')
            if task_id in state['harness']['task_projects']:
                raise StateConflict('Task is already assigned')
            state['harness']['task_projects'][task_id] = project_id

    def project_for_task(self, task_id: str) -> str | None:
        with self.factory._document() as state:
            return state['harness']['task_projects'].get(task_id)

    def tasks_for_project(self, project_id: str) -> tuple[str, ...]:
        with self.factory._document() as state:
            return tuple(sorted(task for task, project in state['harness']['task_projects'].items()
                                if project == project_id))


class FileHarnessState:
    def __init__(self, factory: FileDashboardFactory):
        self.factory = factory
        self.approvals = FileApprovalDecisions(factory)
        self.task_projects = FileTaskProjects(factory)

    @staticmethod
    def _check(state: dict, request: HarnessApprovalRequest, root: Path) -> None:
        if state['harness']['task_projects'].get(request.task_id) != request.project_id:
            raise ValueError('task must be assigned to the requested project')
        repository = state['repositories'].get(request.repository_id)
        if (repository is None or repository['project_id'] != request.project_id
                or repository['provider_id'] != 'local-git'
                or repository['external_id'] != str(root)):
            raise ValueError('registered local repository does not match requested scope')

    def check_registration(self, request: HarnessApprovalRequest, root: Path) -> None:
        self.factory.task_store.get_task(request.task_id)
        with self.factory._document() as state:
            self._check(state, request, root)

    def commit_prepared_run(
        self, *, root: Path, request: HarnessApprovalRequest, approval_id: str,
        controller: str, run_id: str, manifest: str, at: str,
    ) -> None:
        self.factory.task_store.get_task(request.task_id)
        with self.factory._document(edit=True) as state:
            self._check(state, request, root)
            self.approvals._consume(state, approval_id, request, controller=controller)
            if run_id in state['runs']:
                raise StateConflict('Run identity already exists')
            state['runs'][run_id] = {
                'id': run_id, 'task_id': request.task_id, 'runtime': 'unassigned',
                'status': 'prepared', 'workspace': '', 'started_at': at, 'ended_at': None,
                'output': None, 'error_kind': None, 'error_message': None, 'exit_code': None,
            }
            state['harness']['manifests'][run_id] = {
                'approval_id': approval_id, 'manifest': manifest,
            }
            state['events'].append({'run_id': run_id, 'task_id': request.task_id,
                                    'event': 'run.harness_prepared', 'at': at})
