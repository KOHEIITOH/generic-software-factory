"""Provider-neutral remote revision, PR review and issue hierarchy contracts."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Protocol

from sf_factory.source_control import ChangeSourceControl, PullRequestReference
from sf_factory.source_snapshot import _path
from sf_factory.task_sources import ExternalIssue


@dataclass(frozen=True)
class RevisionFile:
    path: str
    mode: str
    content: bytes


@dataclass(frozen=True)
class RevisionSource:
    repository: str
    revision: str
    files: tuple[RevisionFile, ...]

    def validate(self) -> None:
        if (not self.repository or not re.fullmatch(r'[a-f0-9]{40}', self.revision)
                or not isinstance(self.files, tuple) or not 1 <= len(self.files) <= 1000):
            raise ValueError('bounded exact remote revision required')
        paths = set()
        total = 0
        for file in self.files:
            _path(file.path)
            if (file.path in paths or file.mode not in {'100644', '100755'}
                    or not isinstance(file.content, bytes) or len(file.content) > 1048576):
                raise ValueError('invalid remote source path/mode/bytes')
            paths.add(file.path)
            total += len(file.content)
        if total > 8 * 1024 * 1024:
            raise ValueError('remote source exceeds candidate byte budget')
        for path in paths:
            if any(path.startswith(other + '/') for other in paths):
                raise ValueError('remote source path collision')

    @property
    def fingerprint(self) -> str:
        from sf_factory.automation_state import fingerprint
        return fingerprint({'repository': self.repository, 'revision': self.revision,
            'files': [(f.path, f.mode, hashlib.sha256(f.content).hexdigest())
                      for f in sorted(self.files, key=lambda item: item.path)]})


@dataclass(frozen=True)
class ReviewFeedback:
    id: str
    author: str
    body: str
    path: str | None
    state: str
    revision: str


@dataclass(frozen=True)
class ReviewDecision:
    id: str
    author: str
    state: str
    revision: str


@dataclass(frozen=True)
class PullRequestSnapshot:
    reference: PullRequestReference
    repository: str
    head_branch: str
    head_revision: str
    base_branch: str
    base_revision: str
    body: str
    state: str  # open, closed, merged
    draft: bool
    feedback: tuple[ReviewFeedback, ...]
    approved: bool
    decisions: tuple[ReviewDecision, ...] = ()


class CollaborationSourceControl(ChangeSourceControl, Protocol):
    def read_revision(self, repository: str, revision: str) -> RevisionSource: ...

    def pull_request_snapshot(self, repository: str, external_id: str) -> PullRequestSnapshot: ...

    def compare_update_branch(self, repository: str, branch: str, *, expected: str,
                              revision: str) -> None: ...


class IssueTracker(Protocol):
    def find_issue(self, repository: str, marker: str) -> ExternalIssue | None: ...

    def create_issue(self, repository: str, *, title: str, body: str) -> ExternalIssue: ...

    def child_issues(self, repository: str, parent: str) -> tuple[ExternalIssue, ...]: ...

    def attach_child(self, repository: str, parent: str, child: str) -> None: ...
