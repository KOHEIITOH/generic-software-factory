"""SQLite implementation of atomic Harness operations; no Git/runtime work here."""
from __future__ import annotations

import json
from contextlib import closing
from dataclasses import asdict
from pathlib import Path

from sf_factory.factory import Factory
from sf_factory.harness_approval import HarnessApprovalRequest, HarnessApprovalStore
from sf_factory.local_issue_projects import LocalIssueProjects
from sf_factory.local_project_registry import LocalProjectRegistry


class SqliteHarnessState:
    def __init__(self, factory: Factory):
        self.factory = factory
        self.approvals = HarnessApprovalStore(factory.db)
        LocalProjectRegistry(factory.db)
        self.issue_projects = LocalIssueProjects(factory.db)

    @staticmethod
    def _check_registration(db, request: HarnessApprovalRequest, root: Path) -> None:
        issue = db.execute(
            'SELECT t.issue_key,p.project_id FROM issues t LEFT JOIN issue_projects p '
            'ON p.issue_key=t.issue_key '
            'WHERE t.issue_key=?', (request.issue_key,),
        ).fetchone()
        repository = db.execute(
            'SELECT project_id,provider_id,external_id FROM repositories WHERE id=?',
            (request.repository_id,),
        ).fetchone()
        if issue is None or issue['project_id'] != request.project_id:
            raise ValueError('issue must be assigned to the requested project')
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
                'INSERT INTO runs(id,issue_key,issue_snapshot,runtime,status,workspace,started_at) '
                'VALUES (?,?,?,?,?,?,?)',
                (run_id, request.issue_key, json.dumps(asdict(
                    self.factory.issue_store.get_issue(request.issue_key))),
                 'unassigned', 'prepared', '', at),
            )
            db.execute('INSERT INTO run_harness_manifests(run_id,approval_id,manifest) '
                       'VALUES (?,?,?)',
                       (run_id, approval_id, manifest))
            db.execute('INSERT INTO audit(run_id,issue_key,event,at) VALUES (?,?,?,?)',
                       (run_id, request.issue_key, 'run.harness_prepared', at))
