"""Bounded requirement references from verified blobs, never executable policy."""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath

from sf_factory.automation_state import fingerprint
from sf_factory.collaboration_contracts import RevisionSource
from sf_factory.harness_discovery import _IGNORED

MAX_DOCUMENTS = 12
MAX_DOCUMENT_BYTES = 24576
MAX_TOTAL_BYTES = 49152
_OMIT = _IGNORED | {'adr', 'decisions', 'archive', 'archives', 'history', 'historical',
                   'examples', 'generated', 'fixtures', 'test', 'tests'}
_GENERAL_ROOTS = {'docs', 'doc', 'documentation'}
_ROOTS = _GENERAL_ROOTS | {'requirements', 'spec', 'specs', 'specifications', '要件', '仕様'}
_TOPIC = re.compile(r'(?:^|[-_. ])(?:requirements?|specs?|specifications?|prd|design|'
                    r'architecture|overview)(?:$|[-_. ])', re.IGNORECASE)


class RequirementSourceError(ValueError):
    def __init__(self, code: str, facts: dict):
        super().__init__(code)
        self.code, self.facts = code, facts


@dataclass(frozen=True)
class RequirementDocument:
    path: str
    sha256: str
    bytes: int
    reason: str


@dataclass(frozen=True)
class RequirementSources:
    schema_version: int
    repository: str
    revision: str
    mode: str
    documents: tuple[RequirementDocument, ...]

    @property
    def fingerprint(self) -> str:
        return fingerprint(asdict(self))

    @property
    def source_ids(self) -> tuple[str, ...]:
        return ('issue', *(d.path for d in self.documents))

    def document(self) -> dict:
        return {**asdict(self), 'fingerprint': self.fingerprint}


def _candidate(path: str) -> str | None:
    parts = PurePosixPath(path).parts
    lower = tuple(p.casefold() for p in parts)
    if len(parts) > 4 or set(lower[:-1]) & _OMIT:
        return None
    file = PurePosixPath(lower[-1])
    if file.suffix not in {'.md', '.markdown', '.rst', '.txt'} and not (
            len(parts) == 1 and file.name == 'readme'):
        return None
    stem = file.stem
    if len(parts) == 1 and re.fullmatch(r'readme(?:[._-][a-z]{2}(?:[-_][a-z]{2})?)?', stem):
        return 'repository_readme'
    topic = bool(_TOPIC.search(stem) or
                 any(word in stem for word in ('要件', '要求', '仕様', '設計')))
    if len(parts) == 1 and topic and lower[-1] != 'requirements.txt':
        return 'root_requirement_document'
    if lower[0] in _ROOTS:
        if (topic or stem == 'readme' or any(p in _ROOTS - _GENERAL_ROOTS for p in lower[:-1])
                or any(_TOPIC.search(p) for p in lower[1:-1])):
            return 'requirement_document_convention'
    return None


def discover_requirement_sources(source: RevisionSource, *, explicit: tuple[str, ...] = (),
                                 reference_slots: int = 32) -> RequirementSources:
    source.validate()
    if type(reference_slots) is not int or not 0 <= reference_slots <= 32:
        raise ValueError('bounded reference slots required')
    files = {f.path: f.content for f in source.files}
    if not isinstance(explicit, tuple) or len(set(explicit)) != len(explicit):
        raise ValueError('unique explicit requirement paths required')
    selected = ([(p, 'operator_context_path') for p in explicit] if explicit else
                sorted((f.path, reason) for f in source.files if (reason := _candidate(f.path))))
    if len(selected) > min(MAX_DOCUMENTS, reference_slots):
        raise RequirementSourceError('requirements_discovery_limit', {
            'candidate_count': len(selected),
            'max_documents': min(MAX_DOCUMENTS, reference_slots)})
    documents = []
    total = 0
    for path, reason in selected:
        body = files.get(path)
        if body is None:
            raise RequirementSourceError('requirements_source_missing', {'path': path})
        if len(body) > MAX_DOCUMENT_BYTES or total + len(body) > MAX_TOTAL_BYTES:
            raise RequirementSourceError('requirements_discovery_limit', {'path': path,
                'max_file_bytes': MAX_DOCUMENT_BYTES, 'max_total_bytes': MAX_TOTAL_BYTES})
        try:
            text = body.decode('utf-8')
            if not text.strip() or '\x00' in text or any(
                    ord(c) < 32 and c not in '\n\r\t' for c in text):
                raise ValueError('invalid requirement text')
        except (UnicodeError, ValueError) as exc:
            raise RequirementSourceError('requirements_source_invalid', {'path': path}) from exc
        total += len(body)
        documents.append(RequirementDocument(path, hashlib.sha256(body).hexdigest(),
                                             len(body), reason))
    return RequirementSources(1, source.repository, source.revision,
        'explicit' if explicit else 'auto' if documents else 'issue_only', tuple(documents))


def verify_requirement_sources(document: dict, source: RevisionSource) -> None:
    """Check the frozen references without rescanning, reinterpreting or granting scope."""
    source.validate()
    original = {k: v for k, v in document.items() if k != 'fingerprint'}
    if (document.get('schema_version') != 1 or document.get('fingerprint') != fingerprint(original)
            or document.get('repository') != source.repository):
        raise RequirementSourceError('requirements_evidence_invalid', {})
    files = {f.path: f.content for f in source.files}
    for row in document['documents']:
        body = files.get(row['path'])
        if (body is None or len(body) != row['bytes']
                or hashlib.sha256(body).hexdigest() != row['sha256']):
            raise RequirementSourceError('requirements_source_changed', {'path': row['path']})
