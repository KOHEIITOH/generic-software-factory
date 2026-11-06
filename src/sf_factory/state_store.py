"""Minimal task-state boundary, shared by optional persistence adapters.

Run/approval atomic operations will be migrated separately. This contract does
not yet describe a complete alternative backend for every Factory workflow.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class StateNotFound(ValueError):
    """Requested state does not exist."""


class StateConflict(RuntimeError):
    """An operation conflicts with existing state."""


class StateUnavailable(RuntimeError):
    """The backend cannot safely complete or confirm the operation."""


class StateCorrupt(StateUnavailable):
    """Stored data cannot be interpreted without losing guarantees."""


@dataclass(frozen=True)
class TaskRecord:
    id: str
    prompt: str
    created_at: str


def validate_prompt(prompt: str) -> None:
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError('task prompt must not be empty')


def validate_external(provider: str, instance: str, external_id: str, prompt: str) -> None:
    if not all(isinstance(value, str) and value.strip()
               for value in (provider, instance, external_id, prompt)):
        raise ValueError('provider, instance, external_id and prompt are required')
    if any(len(value) > 512 for value in (provider, instance, external_id)):
        raise ValueError('external identity field is too long')


class StateStore(Protocol):
    """Task operations only. Store errors and records never expose connections.

    Import is create-if-absent by the exact provider/instance/external_id tuple;
    repeated imports retain the original task, prompt and event. No network I/O.
    """

    def create_task(self, prompt: str) -> str: ...

    def get_task(self, task_id: str) -> TaskRecord: ...

    def import_external_task(
        self, *, provider: str, instance: str, external_id: str,
        prompt: str, external_url: str | None = None,
    ) -> str: ...
