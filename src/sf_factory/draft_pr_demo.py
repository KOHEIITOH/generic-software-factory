"""Confirmed demo orchestration using SCM contracts, without vendor API types."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from sf_factory.source_control import PullRequestReference, SourceControl, SourceControlError


@dataclass(frozen=True)
class DraftPRDemoResult:
    pull_request: PullRequestReference
    branch: str


def create_draft_pr_demo(source_control: SourceControl, repository: str,
                         *, confirmed: bool) -> DraftPRDemoResult:
    if confirmed is not True:
        raise ValueError('Explicit confirmation required')
    info = source_control.describe_repository(repository)
    if not info.capabilities.write or not info.capabilities.pull_request:
        raise SourceControlError('access_denied', 'Repository write and PR permission required')
    revision = source_control.branch_revision(info.external_id, info.default_branch)
    branch = 'sf-demo-' + uuid4().hex[:12]
    source_control.create_branch(info.external_id, branch, revision)
    source_control.write_file(
        info.external_id, branch=branch, path='.sf-factory-demo/' + branch + '.md',
        content=(b'# Software Factory Draft PR demo\n\n'
                 b'This is a harmless demo marker. No AI or application code was changed.\n'),
        message='docs: add Software Factory demo marker',
    )
    pull_request = source_control.create_draft_pull_request(
        info.external_id, title='docs: Software Factory Draft PR demo', head=branch,
        base=info.default_branch,
        body='Created explicitly from the Software Factory local dashboard. '
             'Demo marker only; no AI execution.',
    )
    return DraftPRDemoResult(pull_request, branch)
