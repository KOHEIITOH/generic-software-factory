"""Pin approved Harness metadata to a prepared Run without starting any runtime."""
from __future__ import annotations

import json
import subprocess
import uuid
from contextlib import closing
from dataclasses import asdict
from pathlib import Path

from sf_factory.factory import Factory, _now
from sf_factory.harness_approval import HarnessApprovalRequest, HarnessApprovalStore
from sf_factory.harness_composition import compose_harness
from sf_factory.harness_validation import validate_harness
from sf_factory.local_project_registry import LocalProjectRegistry
from sf_factory.local_task_projects import LocalTaskProjects


def _revision(root: Path) -> str:
    if not root.is_absolute() or root != root.resolve(strict=True):
        raise ValueError('an explicit canonical repository root is required')
    base = ['git', '--no-optional-locks', '-c', 'core.fsmonitor=false',
            '-c', 'core.hooksPath=/dev/null', '-C', str(root)]
    try:
        filters = subprocess.run(
            [*base, 'config', '--name-only', '--get-regexp', '^filter\\.'],
            capture_output=True, text=True, check=False, timeout=10,
        )
        if filters.returncode not in (0, 1) or filters.stdout.strip():
            raise ValueError('repositories with configured Git filters are unsupported')
        location = subprocess.run([*base, 'rev-parse', '--show-toplevel'],
                                  capture_output=True, text=True, check=True, timeout=10)
        if Path(location.stdout.strip()) != root:
            raise ValueError('repository root mismatch')
        head = subprocess.run([*base, 'rev-parse', '--verify', 'HEAD^{commit}'],
                              capture_output=True, text=True, check=True, timeout=10)
        status = subprocess.run(
            [*base, 'status', '--porcelain=v1', '--untracked-files=all',
             '--ignore-submodules=none'],
            capture_output=True, text=True, check=True, timeout=10,
        )
        if status.stdout:
            raise ValueError('prepare requires a clean tracked and untracked worktree')
        return head.stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError('could not verify repository revision') from exc


class HarnessRunService:
    """Trusted local controller only; no HTTP approval or execution API.

    Existing Registry identifies the local repository. Prepared metadata is not
    a source snapshot or proof of isolation. Execution must revalidate separately.
    """

    def __init__(self, factory: Factory):
        self.factory = factory
        self.approvals = HarnessApprovalStore(factory.db)
        LocalProjectRegistry(factory.db)
        LocalTaskProjects(factory.db)

    @staticmethod
    def _check_registration(db, request: HarnessApprovalRequest, root: Path) -> None:
        task = db.execute(
            'SELECT t.id,p.project_id FROM tasks t LEFT JOIN task_projects p ON p.task_id=t.id '
            'WHERE t.id=?', (request.task_id,),
        ).fetchone()
        repository = db.execute(
            'SELECT project_id,provider_id,external_id FROM repositories WHERE id=?',
            (request.repository_id,),
        ).fetchone()
        if task is None or task['project_id'] != request.project_id:
            raise ValueError('task must be assigned to the requested project')
        if (repository is None or repository['project_id'] != request.project_id
                or repository['provider_id'] != 'local-git'
                or repository['external_id'] != str(root)):
            raise ValueError('registered local repository does not match requested scope')

    def prepare(
        self, *, root: Path, request: HarnessApprovalRequest, approval_id: str,
        target: str, selected: tuple[str, ...], excluded: tuple[tuple[str, str], ...] = (),
        controller: str,
    ) -> dict:
        """Recompose and atomically consume approval with Run/manifest/audit insertion."""
        with closing(self.factory._connect()) as db:
            self._check_registration(db, request, root)
        before = _revision(root)
        if before != request.revision:
            raise PermissionError('approved revision no longer matches repository HEAD')
        composition = compose_harness(validate_harness(root), target=target,
                                      selected=selected, excluded=excluded)
        if composition.bundle_hash != request.bundle_hash or _revision(root) != before:
            raise PermissionError('approved Harness no longer matches current composition')
        manifest = json.dumps({
            'schema_version': 1, 'request': asdict(request), 'composition': asdict(composition),
        }, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
        run_id = uuid.uuid4().hex
        at = _now()
        with closing(self.factory._connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            self._check_registration(db, request, root)
            self.approvals._consume_in_transaction(db, approval_id, request, controller=controller)
            db.execute(
                'INSERT INTO runs(id,task_id,runtime,status,workspace,started_at) '
                'VALUES (?,?,?,?,?,?)',
                (run_id, request.task_id, 'unassigned', 'prepared', '', at),
            )
            db.execute('INSERT INTO run_harness_manifests(run_id,approval_id,manifest) '
                       'VALUES (?,?,?)',
                       (run_id, approval_id, manifest))
            db.execute('INSERT INTO audit(run_id,task_id,event,at) VALUES (?,?,?,?)',
                       (run_id, request.task_id, 'run.harness_prepared', at))
        return self.factory.show_run(run_id)
