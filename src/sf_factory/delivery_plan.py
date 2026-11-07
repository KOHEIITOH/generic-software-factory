"""Bind exact candidate bytes to verified source metadata before SCM delivery.

Pure preparation only: no inference, execution, approval, network or permission.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass

from sf_factory.change_proposal import ChangeProposal, ProposalScope, _source_files, candidate_files
from sf_factory.source_control import CommitChange
from sf_factory.source_snapshot import _fingerprint


def _text(value: str, field: str) -> None:
    if (not isinstance(value, str) or not value.strip() or len(value) > 512
            or any(ord(c) < 32 for c in value)):
        raise ValueError(f'bounded {field} required')


@dataclass(frozen=True)
class DeliveryPlan:
    run_id: str
    repository: str
    base_branch: str
    parent_revision: str
    bundle_hash: str
    source_fingerprint: str
    proposal_fingerprint: str
    changes: tuple[CommitChange, ...]

    @property
    def fingerprint(self) -> str:
        payload = {'run_id': self.run_id, 'repository': self.repository,
            'base_branch': self.base_branch, 'parent_revision': self.parent_revision,
            'bundle_hash': self.bundle_hash, 'source_fingerprint': self.source_fingerprint,
            'proposal_fingerprint': self.proposal_fingerprint,
            'changes': [{'path': c.path, 'before_sha256': hashlib.sha256(c.before).hexdigest()
                         if c.before is not None else None,
                         'after_sha256': hashlib.sha256(c.after).hexdigest(),
                         'executable': c.executable} for c in self.changes]}
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'),
                                         ensure_ascii=True).encode()).hexdigest()

    @property
    def branch(self) -> str:
        return f'sf/run-{self.run_id}-{self.fingerprint[:12]}'

    @property
    def marker(self) -> str:
        return f'<!-- sf-delivery run={self.run_id} plan={self.fingerprint} -->'


def build_delivery_plan(
    *, scope: ProposalScope, proposal: ChangeProposal, source_files: Mapping[str, bytes],
    snapshot: dict, repository: str, base_branch: str,
) -> DeliveryPlan:
    """Require a full matching source inventory, not a model's scope/hash claim.

    Caller must obtain snapshot/files from the trusted SourceSnapshotService and
    separately prove checks, review and exact delivery approval before any write.
    """
    _text(repository, 'repository identity')
    _text(base_branch, 'base branch')
    files = _source_files(source_files)
    candidate = candidate_files(proposal, scope=scope, source_files=files)
    if (not isinstance(snapshot, dict)
            or set(snapshot) != {'snapshot_id', 'fingerprint', 'manifest'}):
        raise ValueError('verified snapshot descriptor required')
    if (not isinstance(snapshot['snapshot_id'], str)
            or not re.fullmatch(r'[a-f0-9]{32}', snapshot['snapshot_id'])):
        raise ValueError('invalid snapshot identity')
    manifest = snapshot['manifest']
    if (not isinstance(manifest, dict) or set(manifest) != {
        'schema_version', 'run_id', 'revision', 'bundle_hash', 'files'
    } or type(manifest['schema_version']) is not int or manifest['schema_version'] != 1
            or manifest['run_id'] != scope.run_id or manifest['revision'] != scope.revision
            or manifest['bundle_hash'] != scope.bundle_hash
            or snapshot['fingerprint'] != scope.source_fingerprint
            or _fingerprint(manifest) != scope.source_fingerprint):
        raise ValueError('source snapshot subject/fingerprint mismatch')
    entries = manifest['files']
    if not isinstance(entries, list) or len(entries) != len(files):
        raise ValueError('complete source inventory required')
    modes = {}
    for entry in entries:
        if (not isinstance(entry, dict) or set(entry) != {'path', 'mode', 'bytes', 'sha256'}
                or not isinstance(entry['path'], str) or entry['path'] in modes
                or entry['path'] not in files or not isinstance(entry['mode'], str)
                or entry['mode'] not in {'100644', '100755'}
                or type(entry['bytes']) is not int or entry['bytes'] != len(files[entry['path']])
                or entry['sha256'] != hashlib.sha256(files[entry['path']]).hexdigest()):
            raise ValueError('source inventory mode/content mismatch')
        modes[entry['path']] = entry['mode']
    return DeliveryPlan(scope.run_id, repository, base_branch, scope.revision, scope.bundle_hash,
        scope.source_fingerprint, proposal.fingerprint,
        tuple(CommitChange(c.path, files.get(c.path), candidate[c.path],
                           modes.get(c.path) == '100755') for c in proposal.changes))
