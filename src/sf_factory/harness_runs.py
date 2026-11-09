"""Pin approved Harness metadata to a prepared Run without starting any runtime."""
from __future__ import annotations

import json
import subprocess
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

from sf_factory.factory import Factory, _now
from sf_factory.git_environment import git_environment
from sf_factory.harness_approval import HarnessApprovalRequest
from sf_factory.harness_composition import compose_harness
from sf_factory.harness_validation import validate_harness
from sf_factory.project_harness import ProjectHarness

if TYPE_CHECKING:
    from sf_factory.collaboration_contracts import RevisionSource


def _revision(root: Path) -> str:
    if not root.is_absolute() or root != root.resolve(strict=True):
        raise ValueError('an explicit canonical repository root is required')
    base = ['git', '--no-optional-locks', '-c', 'core.fsmonitor=false',
            '-c', 'core.hooksPath=/dev/null', '-C', str(root)]
    try:
        filters = subprocess.run(
            [*base, 'config', '--name-only', '--get-regexp', '^filter\\.'],
            capture_output=True, text=True, check=False, timeout=10, env=git_environment(),
        )
        if filters.returncode not in (0, 1) or filters.stdout.strip():
            raise ValueError('repositories with configured Git filters are unsupported')
        location = subprocess.run([*base, 'rev-parse', '--show-toplevel'],
                                  capture_output=True, text=True, check=True, timeout=10,
                                  env=git_environment())
        if Path(location.stdout.strip()) != root:
            raise ValueError('repository root mismatch')
        head = subprocess.run([*base, 'rev-parse', '--verify', 'HEAD^{commit}'],
                              capture_output=True, text=True, check=True, timeout=10,
                              env=git_environment())
        status = subprocess.run(
            [*base, 'status', '--porcelain=v1', '--untracked-files=all',
             '--ignore-submodules=none'],
            capture_output=True, text=True, check=True, timeout=10, env=git_environment(),
        )
        if status.stdout:
            raise ValueError('prepare requires a clean tracked and untracked worktree')
        return head.stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError('could not verify repository revision') from exc


class HarnessRunService:
    """Trusted local controller only; no HTTP approval or execution API.

    Existing Registry identifies the local repository. Prepared metadata is not
    a source snapshot or proof of isolation. Execution must revalidate separately.
    """

    def __init__(self, factory: Factory):
        self.factory = factory
        self.state = factory.harness_state()
        self.approvals = self.state.approvals

    def prepare(
        self, *, root: Path, request: HarnessApprovalRequest, approval_id: str,
        target: str, selected: tuple[str, ...], excluded: tuple[tuple[str, str], ...] = (),
        controller: str, project_harness: ProjectHarness | None = None,
        change_paths: tuple[str, ...] = (), remote_source: RevisionSource | None = None,
    ) -> dict:
        """Recompose and atomically consume approval with Run/manifest/audit insertion."""
        self.state.check_registration(request, root)
        before = _revision(root)
        if remote_source is None:
            if before != request.revision:
                raise PermissionError('approved revision no longer matches repository HEAD')
        else:
            from sf_factory.remote_harness import verify_remote_harness
            verify_remote_harness(root, remote_source)
            if remote_source.revision != request.revision:
                raise PermissionError('remote source differs from approved revision')
        composition = compose_harness(validate_harness(root), target=target,
                                      selected=selected, excluded=excluded,
                                      project_harness=project_harness, change_paths=change_paths)
        if composition.bundle_hash != request.bundle_hash or _revision(root) != before:
            raise PermissionError('approved Harness no longer matches current composition')
        manifest = json.dumps({
            'schema_version': 1, 'request': asdict(request), 'composition': asdict(composition),
        }, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
        run_id = uuid.uuid4().hex
        at = _now()
        self.state.commit_prepared_run(
            root=root, request=request, approval_id=approval_id, controller=controller,
            run_id=run_id, manifest=manifest, at=at,
        )
        return self.factory.show_run(run_id)
