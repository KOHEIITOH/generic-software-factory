"""Explicit operator-owned local execution scope. No repository-provided commands."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from sf_factory.behavioral_check import BehavioralCheck
from sf_factory.change_proposal import ProposalScope
from sf_factory.project_harness import ProjectHarness
from sf_factory.source_snapshot import _path


@dataclass(frozen=True)
class DevelopmentConfig:
    repository: str
    issue: str
    root: Path
    data_root: Path
    provider: str
    image: str
    allowed_paths: tuple[str, ...]
    selected_harness: tuple[str, ...]
    context_paths: tuple[str, ...]
    checks: tuple[BehavioralCheck, ...]
    excluded_harness: tuple[tuple[str, str], ...] = ()
    project_harness: ProjectHarness | None = None

    def __post_init__(self) -> None:
        for value in (self.repository, self.issue):
            if (not isinstance(value, str) or not value.strip() or len(value) > 512
                    or any(ord(c) < 32 for c in value)):
                raise ValueError('bounded repository/issue identity required')
        if (not self.root.is_absolute() or not self.root.is_dir()
                or self.root != self.root.resolve(strict=True)
                or not self.data_root.is_absolute() or self.data_root != self.data_root.resolve()
                or self.data_root.is_relative_to(self.root)
                or self.root.is_relative_to(self.data_root)):
            raise ValueError('canonical repository and separate durable data root required')
        if (self.provider not in {'bedrock', 'copilot'} or not isinstance(self.image, str)
                or not re.fullmatch(r'[a-z0-9./:_-]+@sha256:[a-f0-9]{64}',
                                    self.image)):
            raise ValueError('supported text provider and digest-pinned image required')
        if (self.project_harness is not None
                and not isinstance(self.project_harness, ProjectHarness)):
            raise ValueError('typed Project Harness required')
        ProposalScope('a' * 32, 'b' * 40, 'c' * 64, 'd' * 64, self.allowed_paths)
        if (not isinstance(self.selected_harness, tuple) or not self.selected_harness
                or not isinstance(self.context_paths, tuple)
                or len(self.selected_harness) + len(self.context_paths) > 32):
            raise ValueError('explicit bounded Harness/reference scope required')
        for path in (*self.selected_harness, *self.context_paths):
            _path(path)
        if (not isinstance(self.checks, tuple) or not 1 <= len(self.checks) <= 16
                or not all(isinstance(c, BehavioralCheck) for c in self.checks)
                or len({c.id for c in self.checks}) != len(self.checks)):
            raise ValueError('unique approved behavioral tests required')
        if (not isinstance(self.excluded_harness, tuple) or len(self.excluded_harness) > 32
                or any(not isinstance(p, str) or not isinstance(r, str) or not r.strip()
                       for p, r in self.excluded_harness)):
            raise ValueError('explicit Harness exclusion reasons required')

    @property
    def fingerprint(self) -> str:
        data = asdict(self)
        if self.project_harness is None:
            data.pop('project_harness')
        return hashlib.sha256(json.dumps(data, default=str, sort_keys=True,
                                         separators=(',', ':')).encode()).hexdigest()

    @classmethod
    def from_document(cls, value: dict) -> DevelopmentConfig:
        required = {'repository', 'issue', 'root', 'data_root', 'provider', 'image',
                    'allowed_paths', 'selected_harness', 'context_paths', 'checks'}
        if (not isinstance(value, dict) or not required <= set(value)
                or not set(value) <= required | {'excluded_harness', 'project_harness'}
                or any(not isinstance(value[k], list) for k in (
                    'allowed_paths', 'selected_harness', 'context_paths', 'checks'))):
            raise ValueError('exact development config schema required')
        return cls(**{**value, 'root': Path(value['root']), 'data_root': Path(value['data_root']),
            'allowed_paths': tuple(value['allowed_paths']),
            'selected_harness': tuple(value['selected_harness']),
            'context_paths': tuple(value['context_paths']),
            'excluded_harness': tuple(tuple(pair) for pair in value.get('excluded_harness', [])),
            'project_harness': ProjectHarness.from_document(value['project_harness'])
                if value.get('project_harness') is not None else None,
            'checks': tuple(BehavioralCheck(**{**item, 'argv': tuple(item['argv'])})
                            for item in value['checks'])})
