"""SQLite implementation of atomic Harness operations; no Git/runtime work here."""
from __future__ import annotations

from contextlib import closing
from pathlib import Path

from sf_factory.factory import Factory
from sf_factory.harness_approval import HarnessApprovalRequest, HarnessApprovalStore
from sf_factory.local_project_registry import LocalProjectRegistry
from sf_factory.local_task_projects import LocalTaskProjects


class SqliteHarnessState:
    def __init__(self, factory: Factory):
        self.factory = factory
        self.approvals = HarnessApprovalStore(factory.db)
        LocalProjectRegistry(factory.db)
        self.task_projects = LocalTaskProjects(factory.db)

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

    def check_registration(self, request: HarnessApprovalRequest, root: Path) -> None:
        with closing(self.factory._connect()) as db:
            self._check_registration(db, request, root)

    def commit_prepared_run(
        self, *, root: Path, request: HarnessApprovalRequest, approval_id: str,
        controller: str, run_id: str, manifest: str, at: str,
    ) -> None:
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
