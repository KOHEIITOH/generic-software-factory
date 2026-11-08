"""Operator-managed Project common rules, reusable across repositories.

Text context only: no commands, permissions, secret paths or tool grants.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ProjectRule:
    name: str
    text: str

    def __post_init__(self) -> None:
        if (not isinstance(self.name, str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', self.name)
                or not isinstance(self.text, str) or not self.text.strip()
                or len(self.text.encode()) > 8192 or '\x00' in self.text):
            raise ValueError('bounded named Project rule text required')


@dataclass(frozen=True)
class ProjectHarness:
    project: str
    rules: tuple[ProjectRule, ...]

    def __post_init__(self) -> None:
        if (not isinstance(self.project, str)
                or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', self.project)
                or not isinstance(self.rules, tuple) or not 1 <= len(self.rules) <= 16
                or not all(isinstance(rule, ProjectRule) for rule in self.rules)
                or len({rule.name for rule in self.rules}) != len(self.rules)
                or sum(len(rule.text.encode()) for rule in self.rules) > 32768):
            raise ValueError('bounded unique Project Harness required')

    @classmethod
    def from_document(cls, value: dict) -> ProjectHarness:
        if (not isinstance(value, dict) or set(value) != {'project', 'rules'}
                or not isinstance(value['rules'], list)):
            raise ValueError('exact Project Harness schema required')
        return cls(value['project'], tuple(ProjectRule(**rule) for rule in value['rules']))
