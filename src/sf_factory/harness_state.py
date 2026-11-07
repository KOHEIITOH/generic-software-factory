"""Domain operations required to preserve exact-scope Harness approval atomicity."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Protocol

from sf_factory.harness_approval import HarnessApprovalRequest


class ApprovalDecisions(Protocol):
    def record(self, request: HarnessApprovalRequest, *, reviewer: str, approved: bool,
               expires_at: datetime) -> str: ...

    def consume(self, approval_id: str, request: HarnessApprovalRequest,
                *, controller: str) -> None: ...

    def revoke(self, approval_id: str, *, reviewer: str) -> None: ...

    def events(self, approval_id: str) -> tuple[dict, ...]: ...


class IssueProjectAssociations(Protocol):
    def assign(self, issue_key: str, project_id: str) -> None: ...

    def project_for_issue(self, issue_key: str) -> str | None: ...

    def issues_for_project(self, project_id: str) -> tuple[str, ...]: ...


class HarnessState(Protocol):
    @property
    def approvals(self) -> ApprovalDecisions: ...

    @property
    def issue_projects(self) -> IssueProjectAssociations: ...

    def check_registration(self, request: HarnessApprovalRequest, root: Path) -> None: ...

    def commit_prepared_run(
        self, *, root: Path, request: HarnessApprovalRequest, approval_id: str,
        controller: str, run_id: str, manifest: str, at: str,
    ) -> None:
        """Check scope and atomically consume approval with Run/manifest/audit.

        Reuse, revocation, scope mismatch and failed writes must not yield a Run.
        Git revalidation belongs to the controller before this bounded operation.
        """
        ...
