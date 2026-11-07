"""Atomic delivery intent boundary. State is bookkeeping, never authorization."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from sf_factory.delivery_plan import DeliveryPlan
from sf_factory.source_control import PreparedCommit, PullRequestReference

STAGES = ('claimed', 'commit_ready', 'branch_pending', 'branch_ready', 'pr_pending', 'delivered')


@dataclass(frozen=True)
class DeliveryRecord:
    run_id: str
    fingerprint: str
    repository: str
    branch: str
    base_branch: str
    parent_revision: str
    stage: str = 'claimed'
    commit: PreparedCommit | None = None
    pull_request: PullRequestReference | None = None

    def validate(self) -> None:
        if (not re.fullmatch(r'[a-f0-9]{32}', self.run_id)
                or not re.fullmatch(r'[a-f0-9]{64}', self.fingerprint)
                or not re.fullmatch(r'(?:[a-f0-9]{40}|[a-f0-9]{64})', self.parent_revision)
                or self.stage not in STAGES
                or self.branch != f'sf/run-{self.run_id}-{self.fingerprint[:12]}'):
            raise ValueError('invalid delivery identity/stage')
        for value in (self.repository, self.base_branch):
            if (not isinstance(value, str) or not value.strip() or len(value) > 512
                    or any(ord(c) < 32 for c in value)):
                raise ValueError('invalid delivery destination')
        if (self.stage == 'claimed') != (self.commit is None):
            raise ValueError('commit receipt required after preparation')
        if self.commit is not None:
            for value in (self.commit.external_id, self.commit.tree_id, self.commit.parent_id):
                if not re.fullmatch(r'(?:[a-f0-9]{40}|[a-f0-9]{64})', value):
                    raise ValueError('invalid commit receipt')
            if self.commit.parent_id != self.parent_revision:
                raise ValueError('commit parent mismatch')
        if (self.stage == 'delivered') != (self.pull_request is not None):
            raise ValueError('PR receipt required only after delivery')
        if self.pull_request is not None:
            for value in (self.pull_request.external_id, self.pull_request.url):
                if (not isinstance(value, str) or not value.strip() or len(value) > 2048
                        or any(ord(c) < 32 for c in value)):
                    raise ValueError('invalid pull request receipt')


class DeliveryState(Protocol):
    def claim(self, plan: DeliveryPlan) -> DeliveryRecord:
        """New Run only; serialize unresolved deliveries for one canonical repository."""
        ...

    def get(self, run_id: str) -> DeliveryRecord: ...

    def advance(self, run_id: str, fingerprint: str, *, expected: str, stage: str,
                commit: PreparedCommit | None = None,
                pull_request: PullRequestReference | None = None) -> DeliveryRecord:
        """CAS one forward step. Persist pending intent BEFORE the remote mutation."""
        ...
