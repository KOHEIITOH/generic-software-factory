"""One approved behavioral scenario per isolated command, verified by controller."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass

from sf_factory.change_proposal import ChangeProposal, ProposalScope
from sf_factory.run_evidence import CheckObservation, CheckRequirement
from sf_factory.workspace_check import WorkspaceCheckResult, run_candidate_check


@dataclass(frozen=True)
class BehavioralCheck:
    id: str
    argv: tuple[str, ...]
    stdout: str

    def __post_init__(self) -> None:
        CheckRequirement(self.id, 'tests')
        if (not isinstance(self.argv, tuple) or not 1 <= len(self.argv) <= 128
                or any(not isinstance(v, str) or '\x00' in v or len(v) > 65536 for v in self.argv)
                or not self.argv[0] or self.argv[0].startswith('-')
                or not isinstance(self.stdout, str) or len(self.stdout.encode()) > 16384):
            raise ValueError('bounded approved behavioral test required')


def collect_behavioral_check(*, check: BehavioralCheck, image: str, scope: ProposalScope,
                             proposal: ChangeProposal, source_files: Mapping[str, bytes],
                             on_result: Callable[[WorkspaceCheckResult], None] | None = None
                             ) -> CheckObservation:
    """Count one actual scenario invocation, never parse a model's test-count claim.

    The operator approves argv and expected stdout before inference. This is not
    an aggregate unittest/pytest report collector. Skips/timeouts/tampering fail.
    """
    result = run_candidate_check(image=image, scope=scope, proposal=proposal,
                                 source_files=source_files, argv=check.argv)
    if on_result is not None:
        on_result(result)
    digest = hashlib.sha256(json.dumps({'check': asdict(check), 'result': asdict(result)},
        sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    completed = (result.status == 'succeeded' and result.exit_code == 0
                 and result.cleaned_up and result.source_unchanged
                 and result.proposal_fingerprint == proposal.fingerprint)
    if completed and result.output == check.stdout:
        return CheckObservation(check.id, 'completed', 0, digest, 1, scope.run_id)
    # Unexpected stdout with exit zero is an observed test failure, not success.
    if completed or (result.status == 'failed' and result.exit_code not in {None, 0}):
        code = result.exit_code if result.exit_code not in {None, 0} else 1
        return CheckObservation(check.id, 'failed', code, digest, 1, scope.run_id)
    return CheckObservation(check.id, 'error', None, digest, None, scope.run_id)
