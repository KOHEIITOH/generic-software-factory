"""Remote source may change code, never the operator-reviewed Harness inventory."""
from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath

from sf_factory.collaboration_contracts import RevisionSource
from sf_factory.harness_discovery import _IGNORED, _classify
from sf_factory.harness_runs import _revision
from sf_factory.harness_validation import validate_harness
from sf_factory.state_store import StatePermissionDenied


def verify_remote_harness(root: Path, source: RevisionSource) -> None:
    source.validate()
    before = _revision(root)
    validation = validate_harness(root)
    if any(i.reason != 'multiple_rule_sources_require_validation'
           for i in validation.discovery.issues):
        raise ValueError('local Harness inventory incomplete')
    local = {c.path: c.sha256 for c in validation.discovery.candidates}
    remote = {f.path: hashlib.sha256(f.content).hexdigest() for f in source.files
              if not set(PurePosixPath(f.path).parts) & _IGNORED
              and _classify(PurePosixPath(f.path).parts)}
    if local != remote:
        raise StatePermissionDenied('remote Harness inventory changed; no implicit approval')
    hashes = {f.path: hashlib.sha256(f.content).hexdigest() for f in source.files}
    for profile in validation.profiles:
        for path, expected in profile.references:
            if hashes.get(path) != expected:
                raise StatePermissionDenied('remote approved profile reference changed')
    if _revision(root) != before:
        raise StatePermissionDenied('local operator baseline changed during verification')
