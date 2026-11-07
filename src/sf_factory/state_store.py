"""External Issue cache boundary, shared by optional persistence adapters.

A cache of externally managed Issues; Run/approval operations use their domain ports.
"""
from __future__ import annotations

from typing import Protocol

from sf_factory.issue_reference import IssueSnapshot


class StateNotFound(ValueError):
    """Requested state does not exist."""


class StateConflict(RuntimeError):
    """An operation conflicts with existing state."""


class StatePermissionDenied(PermissionError):
    """A domain authorization decision, distinct from filesystem access errors."""


class StateUnavailable(RuntimeError):
    """The backend cannot safely complete or confirm the operation."""


class StateCorrupt(StateUnavailable):
    """Stored data cannot be interpreted without losing guarantees."""



class IssueStore(Protocol):
    """Issue operations only. Store errors and records never expose connections.

    Identity is derived from the external provider/instance/external_id tuple.
    Re-observation refreshes the mirror. Existing Runs retain frozen requirements.
    """

    def get_issue(self, issue_key: str) -> IssueSnapshot: ...

    def import_issue(
        self, *, provider: str, instance: str, external_id: str,
        prompt: str, external_url: str | None = None,
    ) -> str: ...
