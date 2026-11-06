"""Explicit repository rule selection; no implicit policy or command overrides."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath

from sf_factory.harness_discovery import HarnessCandidate
from sf_factory.harness_validation import HarnessValidation, ProfileCandidate


@dataclass(frozen=True)
class HarnessComposition:
    schema_version: int
    target: str
    sources: tuple[HarnessCandidate, ...]
    profile: ProfileCandidate | None
    excluded: tuple[tuple[str, str], ...]
    inventory_hash: str

    @property
    def bundle_hash(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(',', ':'), ensure_ascii=True)
        return hashlib.sha256(payload.encode()).hexdigest()


def _relative(value: str, *, allow_root: bool = False) -> tuple[str, ...]:
    if not isinstance(value, str) or not value or '\\' in value or '\x00' in value:
        raise ValueError('a relative repository path is required')
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or (not allow_root and not path.parts):
        raise ValueError('a relative repository path without parent traversal is required')
    if path.as_posix() != value:
        raise ValueError('canonical relative paths are required')
    return path.parts


def compose_harness(
    validation: HarnessValidation, *, target: str,
    selected: tuple[str, ...], excluded: tuple[tuple[str, str], ...] = (),
) -> HarnessComposition:
    """Select every applicable source explicitly or exclude it with a reason.

    Only multiple-source and explicitly excluded example warnings can be
    resolved here. Syntax, read, snapshot and limit problems remain blockers.
    Caller order is retained as context order, never as permission precedence.
    Factory policy is outside this API and cannot be replaced through selection.
    """
    target_parts = _relative(target, allow_root=True)
    if validation.schema_version != 1 or validation.discovery.schema_version != 1:
        raise ValueError('unsupported inventory version')
    exclusions: dict[str, str] = {}
    for path, reason in excluded:
        _relative(path)
        if (path in exclusions or not isinstance(reason, str)
                or not reason.strip() or len(reason) > 512 or '\x00' in reason):
            raise ValueError('unique exclusions with bounded reasons required')
        exclusions[path] = reason
    if len(selected) != len(set(selected)) or set(selected) & set(exclusions):
        raise ValueError('selection must be unique and disjoint from exclusions')
    inventory = {c.path: c for c in validation.discovery.candidates}
    if len(inventory) != len(validation.discovery.candidates):
        raise ValueError('duplicate inventory paths')
    for issue in validation.discovery.issues:
        if issue.reason != 'multiple_rule_sources_require_validation':
            raise ValueError('incomplete discovery cannot be composed')
    for issue in validation.issues:
        if issue.code == 'multiple_rule_sources_require_validation':
            continue
        if issue.code == 'example_profile_not_active' and issue.path in exclusions:
            continue
        raise ValueError('unresolved validation problem')
    if not validation.discovery.complete and not validation.discovery.issues:
        raise ValueError('inconsistent inventory completeness')
    if not validation.valid and not validation.issues:
        raise ValueError('inconsistent validation status')
    applicable = {}
    for candidate in inventory.values():
        _relative(candidate.path)
        scope = _relative(candidate.scope, allow_root=True)
        if candidate.kind in {'instructions', 'harness', 'profile'}:
            if target_parts[:len(scope)] == scope:
                applicable[candidate.path] = candidate
    if set(selected) | set(exclusions) != set(applicable):
        raise ValueError('every applicable rule source must be selected or explicitly excluded')
    if not selected:
        raise ValueError('at least one applicable rule source must be selected')
    sources = tuple(applicable[path] for path in selected)
    profile_sources = [source for source in sources if source.kind == 'profile']
    if len(profile_sources) > 1:
        raise ValueError('choose one effective profile; command merging is unsupported')
    profiles = {p.path: p for p in validation.profiles}
    profile = None
    if profile_sources:
        source = profile_sources[0]
        profile = profiles.get(source.path)
        if profile is None or profile.sha256 != source.sha256:
            raise ValueError('selected profile has not been validated')
    inventory_payload = {
        'candidates': sorted((asdict(c) for c in inventory.values()), key=lambda c: c['path']),
        'profiles': sorted((asdict(p) for p in validation.profiles), key=lambda p: p['path']),
    }
    inventory_hash = hashlib.sha256(json.dumps(
        inventory_payload, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
    ).encode()).hexdigest()
    return HarnessComposition(1, target, sources, profile, tuple(sorted(exclusions.items())),
                              inventory_hash)
