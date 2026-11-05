"""Provider-neutral, read-only task source adapter contracts.

Adapters fetch external issue snapshots. The Factory owns persistence, identity
mapping, and execution; adapters never receive the Factory database or run AI.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sf_factory.factory import Factory


@dataclass(frozen=True)
class ExternalIssue:
    provider: str
    instance: str
    external_id: str
    prompt: str
    external_url: str | None = None

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str) and value.strip()
            for value in (self.provider, self.instance, self.external_id, self.prompt)
        ):
            raise ValueError("issue identity and prompt must be non-empty strings")
        if any(
            len(value) > 512
            for value in (self.provider, self.instance, self.external_id)
        ):
            raise ValueError("issue identity field is too long")
        if self.external_url is not None and (
            not isinstance(self.external_url, str)
            or not self.external_url.startswith(("https://", "http://"))
        ):
            raise ValueError("external_url must be an HTTP(S) URL")


class TaskSourceAdapter(Protocol):
    """Fetch one external issue. Authentication stays inside the adapter."""

    def fetch_issue(self, external_id: str) -> ExternalIssue: ...


def import_issue(factory: Factory, adapter: TaskSourceAdapter, external_id: str) -> str:
    """Fetch and atomically upsert the issue identity into the Factory."""
    if not external_id.strip():
        raise ValueError("external_id must not be empty")
    issue = adapter.fetch_issue(external_id)
    if issue.external_id != external_id:
        raise ValueError("adapter returned a different external issue")
    return factory.import_external_task(
        provider=issue.provider,
        instance=issue.instance,
        external_id=issue.external_id,
        prompt=issue.prompt,
        external_url=issue.external_url,
    )
