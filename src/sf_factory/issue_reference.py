"""External service identity. There is no separately editable Factory task."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime


@dataclass(frozen=True)
class IssueReference:
    provider: str
    instance: str
    external_id: str

    def __post_init__(self) -> None:
        for value in (self.provider, self.instance, self.external_id):
            if (not isinstance(value, str) or not value.strip() or len(value) > 512
                    or any(ord(c) < 32 for c in value)):
                raise ValueError('bounded external Issue reference required')

    @property
    def key(self) -> str:
        """Storage index derived only from external identity, never a new Task ID."""
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True,
                                         separators=(',', ':')).encode()).hexdigest()


@dataclass(frozen=True)
class IssueSnapshot:
    provider: str
    instance: str
    external_id: str
    prompt: str
    external_url: str | None
    observed_at: str

    def __post_init__(self) -> None:
        IssueReference(self.provider, self.instance, self.external_id)
        if not isinstance(self.prompt, str) or not self.prompt.strip():
            raise ValueError('external Issue content required')
        if self.external_url is not None and (not isinstance(self.external_url, str)
                or not self.external_url.startswith(('https://', 'http://'))):
            raise ValueError('HTTP Issue URL required')
        if datetime.fromisoformat(self.observed_at).utcoffset() is None:
            raise ValueError('aware observation timestamp required')

    @property
    def key(self) -> str:
        return IssueReference(self.provider, self.instance, self.external_id).key

    def public(self) -> dict:
        return {'key': self.key, **asdict(self)}
