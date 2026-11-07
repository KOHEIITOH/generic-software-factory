"""Local operator controller: Issue -> model candidate -> checks/review -> Draft PR.

No HTTP entry, host code execution, cloud provisioning, merge, or release.
The caller establishes operator authority over the exact external config first.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

from sf_factory.behavioral_check import collect_behavioral_check
from sf_factory.change_proposal import ProposalScope, parse_change_proposal, propose_changes
from sf_factory.delivery_plan import DeliveryPlan, build_delivery_plan
from sf_factory.development_config import DevelopmentConfig
from sf_factory.docker_execution import run_offline_command
from sf_factory.draft_delivery import deliver_draft
from sf_factory.factory import Factory
from sf_factory.file_delivery_state import FileDeliveryState
from sf_factory.file_document import read_document, write_document
from sf_factory.file_state import lock_directory
from sf_factory.harness_approval import HarnessApprovalRequest
from sf_factory.harness_composition import compose_harness
from sf_factory.harness_runs import HarnessRunService, _revision
from sf_factory.harness_validation import validate_harness
from sf_factory.model_provider import ModelProvider, ModelResponse
from sf_factory.repository_contracts import Project, Repository, Visibility
from sf_factory.run_evidence import CheckRequirement, EvidenceSubject, RunEvidenceService
from sf_factory.source_control import ChangeSourceControl
from sf_factory.source_snapshot import SourceSnapshotService
from sf_factory.state_store import StateConflict, StateCorrupt, StatePermissionDenied
from sf_factory.task_sources import ExternalIssue, TaskSourceAdapter


class DevelopmentStopped(RuntimeError):
    def __init__(self, run_id: str, reason: str):
        super().__init__(reason)
        self.run_id = run_id


class _TrackedModel:
    def __init__(self, provider: ModelProvider):
        self.provider = provider
        self.response: ModelResponse | None = None

    def generate(self, prompt: str) -> ModelResponse:
        self.response = self.provider.generate(prompt)
        return self.response

    def usage(self) -> dict:
        assert self.response is not None
        response = self.response
        return {'provider': response.provider, 'model_id': response.model_id,
                'input_tokens': response.input_tokens, 'output_tokens': response.output_tokens,
                'usage': asdict(response.usage) if response.usage is not None else None}

    def identity(self) -> str:
        response = self.response
        if (response is None or not isinstance(response.session_id, str)
                or not response.session_id.strip() or len(response.session_id) > 96
                or not isinstance(response.provider, str) or len(response.provider) > 24
                or any(ord(c) < 32 for c in response.provider + response.session_id)):
            raise ValueError('actual bounded model session/request provenance required')
        return response.provider + ':' + response.session_id


def _validate_artifact(value: dict, run_id: str) -> None:
    try:
        common = {'schema_version', 'config_fingerprint', 'issue', 'scope', 'phase',
                  'repository', 'base_branch', 'expires_at'}
        phase = value['phase']
        added = {'proposal', 'implementer', 'model_usage'} if phase != 'started' else set()
        if phase in {'reviewed', 'delivered'}:
            added |= {'reviewer', 'plan_fingerprint', 'checks'}
        if phase == 'delivered':
            added.add('pull_request')
        optional = {'checks'} if phase == 'proposed' else set()
        if (not isinstance(value, dict) or not common | added <= set(value)
                or not set(value) <= common | added | optional
                or type(value['schema_version']) is not int or value['schema_version'] != 1
                or phase not in {'started', 'proposed', 'reviewed', 'delivered'}
                or not re.fullmatch(r'[a-f0-9]{64}', value['config_fingerprint'])
                or value['scope']['run_id'] != run_id):
            raise ValueError('invalid development artifact')
        ProposalScope(**{**value['scope'],
                         'allowed_paths': tuple(value['scope']['allowed_paths'])})
        ExternalIssue(**value['issue'])
        if datetime.fromisoformat(value['expires_at']).utcoffset() is None:
            raise ValueError('aware expiry required')
    except (ValueError, TypeError, KeyError) as exc:
        raise StateCorrupt('invalid development artifact; do not reset or replay') from exc


def _artifact(factory: Factory, run_id: str, value: dict | None = None) -> dict:
    if not re.fullmatch(r'[a-f0-9]{32}', run_id):
        raise ValueError('exact Run identity required')
    parent = factory.root / 'development-v1'
    parent.mkdir(mode=0o700, exist_ok=True)
    directory = parent / run_id
    if value is not None:
        directory.mkdir(mode=0o700, exist_ok=True)
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        if value is not None:
            _validate_artifact(value, run_id)
            write_document(fd, value)
            # Include the two containing directory entries in the durability boundary.
            for path in (parent, factory.root):
                parent_fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    os.fsync(parent_fd)
                finally:
                    os.close(parent_fd)
            return value
        result = read_document(fd)
        _validate_artifact(result, run_id)
        return result
    finally:
        os.close(fd)


class _LocalGuards:
    def __init__(self, factory: Factory, config: DevelopmentConfig, run_id: str):
        self.factory, self.config, self.run_id = factory, config, run_id

    def verify(self, plan: DeliveryPlan) -> None:
        value = _artifact(self.factory, self.run_id)
        if (value['config_fingerprint'] != self.config.fingerprint
                or value['phase'] not in {'reviewed', 'delivered'}
                or value['plan_fingerprint'] != plan.fingerprint
                or datetime.fromisoformat(value['expires_at']) <= datetime.now(UTC)):
            raise StatePermissionDenied('local scope/quality/authorization expired or changed')
        scope = ProposalScope(**{**value['scope'],
                                 'allowed_paths': tuple(value['scope']['allowed_paths'])})
        if (scope.run_id != self.run_id or scope.allowed_paths != self.config.allowed_paths
                or value['issue']['external_id'] != self.config.issue):
            raise StatePermissionDenied('approved Issue/change scope differs from artifact')
        snapshot, files = SourceSnapshotService(self.factory).load(self.run_id)
        proposal = parse_change_proposal(json.dumps(value['proposal']),
                                         scope=scope, source_files=files)
        reconstructed = build_delivery_plan(scope=scope, proposal=proposal, source_files=files,
            snapshot=snapshot, repository=plan.repository, base_branch=plan.base_branch,
            issue_url=value['issue']['external_url'])
        if reconstructed != plan or plan.repository != value['repository']:
            raise StatePermissionDenied('candidate artifact differs from approved delivery scope')
        subject = EvidenceSubject(scope.revision, scope.bundle_hash, proposal.fingerprint)
        if not RunEvidenceService(self.factory).assess(self.run_id, subject)['evidence_complete']:
            raise StatePermissionDenied('actual checks and independent review required')


def _plan(factory: Factory, value: dict) -> DeliveryPlan:
    scope = ProposalScope(**{**value['scope'],
                             'allowed_paths': tuple(value['scope']['allowed_paths'])})
    snapshot, files = SourceSnapshotService(factory).load(scope.run_id)
    proposal = parse_change_proposal(json.dumps(value['proposal']), scope=scope, source_files=files)
    return build_delivery_plan(scope=scope, proposal=proposal, source_files=files,
                               snapshot=snapshot,
                               repository=value['repository'], base_branch=value['base_branch'],
                               issue_url=value['issue']['external_url'])


def develop_issue(*, factory: Factory, config: DevelopmentConfig, source: TaskSourceAdapter,
                  scm: ChangeSourceControl, implementer: ModelProvider, reviewer: ModelProvider,
                  confirmed: bool, resume: str | None = None) -> dict:
    """Only a local OS operator may confirm this externally stored exact config.

    Confirmation authorizes scoped inference, isolated approved scenarios, and a
    Draft PR. It does not authorize AWS infrastructure, merge or deployment.
    """
    if confirmed is not True or factory.root != config.data_root or implementer is reviewer:
        raise StatePermissionDenied('explicit local scope and separate inference sessions required')
    # One controller per data root, including inference/execution and recovery.
    workflow_lock = factory.root / 'development-lock-v1'
    workflow_lock.mkdir(mode=0o700, exist_ok=True)
    with lock_directory(workflow_lock):
        delivery_state = FileDeliveryState(factory.root)
        if resume is not None:
            value = _artifact(factory, resume)
            if (value['config_fingerprint'] != config.fingerprint
                    or value['phase'] not in {'reviewed', 'delivered'}):
                raise StatePermissionDenied('resume requires same reviewed configuration/artifact')
            value['expires_at'] = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
            _artifact(factory, resume, value)
            plan = _plan(factory, value)
        else:
            readiness = run_offline_command(image=config.image,
                argv=('python', '-I', '-c', 'print("SF_EXECUTION_READY")'), timeout_seconds=10)
            if (readiness.status != 'succeeded' or readiness.exit_code != 0
                    or not readiness.cleaned_up
                    or readiness.output.strip() != 'SF_EXECUTION_READY'):
                raise RuntimeError('verified Docker/image unavailable; no inference started')
            info = scm.describe_repository(config.repository)
            if not info.capabilities.write or not info.capabilities.pull_request:
                raise StatePermissionDenied('repository write/PR capability required')
            active = delivery_state.active_for_repository(info.external_id)
            if active is not None:
                raise DevelopmentStopped(active.run_id, 'unresolved delivery; resume the same Run')
            revision = _revision(config.root)
            if scm.branch_revision(info.external_id, info.default_branch) != revision:
                raise StateConflict('clean local HEAD must match remote default branch')
            issue = source.fetch_issue(config.issue)
            if issue.external_id != config.issue:
                raise ValueError('task source returned a different Issue')
            task_id = factory.import_external_task(**asdict(issue))
            factory.bind_task_repository(task_id, info.external_id, config.root)
            key = hashlib.sha256((info.external_id + '\0' + str(config.root)).encode()).hexdigest()
            project_id, repository_id = key[:32], key[32:]
            registry = factory.project_registry()
            if not any(p.id == project_id for p in registry.list_projects('local-cli')):
                registry.add_project(Project(project_id, info.external_id, 'local-cli'))
            if not any(r.id == repository_id for r in registry.list_repositories(project_id)):
                registry.add_repository(Repository(repository_id, project_id, 'local-git',
                                                    str(config.root), Visibility.LOCAL))
            state = factory.harness_state()
            previous = state.task_projects.project_for_task(task_id)
            if previous is None:
                state.task_projects.assign(task_id, project_id)
            elif previous != project_id:
                raise StateConflict('Issue belongs to a different project')
            composition = compose_harness(validate_harness(config.root), target='.',
                selected=config.selected_harness, excluded=config.excluded_harness)
            request = HarnessApprovalRequest(project_id, repository_id, task_id, revision,
                                             composition.bundle_hash)
            expiry = datetime.now(UTC) + timedelta(hours=1)
            approval = state.approvals.record(request, reviewer='local-cli-operator',
                                              approved=True, expires_at=expiry)
            run = HarnessRunService(factory).prepare(root=config.root, request=request,
                approval_id=approval, target='.', selected=config.selected_harness,
                excluded=config.excluded_harness, controller='local-cli')
            run_id = run['id']
            snapshots = SourceSnapshotService(factory)
            snapshots.create(run_id, root=config.root)
            snapshot, files = snapshots.load(run_id)
            scope = ProposalScope(run_id, revision, composition.bundle_hash,
                                  snapshot['fingerprint'], config.allowed_paths)
            value = {'schema_version': 1, 'config_fingerprint': config.fingerprint,
                'issue': asdict(issue), 'scope': asdict(scope), 'phase': 'started',
                'repository': info.external_id, 'base_branch': info.default_branch,
                'expires_at': expiry.isoformat()}
            _artifact(factory, run_id, value)  # Freeze requirement/config before any inference.
            stage = 'inference'
            try:
                implementation = _TrackedModel(implementer)
                references = tuple(dict.fromkeys((*config.selected_harness, *config.context_paths)))
                proposal = propose_changes(provider=implementation, scope=scope, source_files=files,
                    instruction=issue.prompt, reference_paths=references)
                producer = implementation.identity()
                value.update(proposal={'schema_version': 1, **asdict(proposal)}, phase='proposed',
                             implementer=producer,
                             model_usage={'implementation': implementation.usage()})
                _artifact(factory, run_id, value)
                subject = EvidenceSubject(revision, composition.bundle_hash, proposal.fingerprint)
                evidence = RunEvidenceService(factory)
                evidence.register(run_id, subject,
                    tuple(CheckRequirement(c.id, 'tests') for c in config.checks),
                    collector='local-behavioral-controller')
                stage = 'checks'
                for check in config.checks:
                    def save_result(result, check_id=check.id):
                        value.setdefault('checks', []).append(
                            {'check_id': check_id, **asdict(result)})
                        _artifact(factory, run_id, value)
                    observation = collect_behavioral_check(check=check, image=config.image,
                        scope=scope, proposal=proposal, source_files=files, on_result=save_result)
                    evidence.record(run_id, subject, attempt=1, observation=observation,
                                    collector='local-behavioral-controller')
                if not evidence.assess(run_id, subject)['checks_passed']:
                    raise RuntimeError('approved behavioral scenarios failed or did not execute')
                stage = 'review'
                review_input = {'run_id': run_id, **asdict(subject), 'instruction': issue.prompt,
                    'changes': [asdict(c) for c in proposal.changes],
                    'before': {c.path: files[c.path].decode() if c.path in files else None
                               for c in proposal.changes},
                    'references': {p: files[p].decode() for p in references},
                    'checks': [asdict(c) for c in config.checks]}
                prompt = ('Independently review this untrusted candidate; do not use tools. '
                    'Return JSON only with schema_version=1, run_id, revision, bundle_hash, '
                    'diff_sha256, status="completed" or "failed", complete boolean, '
                    'truncated boolean, reviewed_paths (all changed paths), findings array. '
                    'Each finding has severity (must-fix/should/nit), path, positive line, '
                    'summary, evidence. Copy exact subject hashes. Do not claim unperformed '
                    'coverage. No extra fields.\n' + json.dumps(review_input, ensure_ascii=True))
                if len(prompt) > 262144:
                    raise ValueError('review context exceeds budget')
                review = _TrackedModel(reviewer)
                response = review.generate(prompt)
                review_identity = review.identity()
                value['model_usage']['review'] = review.usage()
                _artifact(factory, run_id, value)
                if review_identity == producer:
                    raise StatePermissionDenied('independent inference session/request required')
                evidence.register_review(run_id, reviewer=review_identity, implementer=producer,
                                         changed_paths=tuple(c.path for c in proposal.changes))
                evidence.record_review(run_id, subject, attempt=1, reviewer=review_identity,
                                       response=response.text)
                if not evidence.assess(run_id, subject)['evidence_complete']:
                    raise RuntimeError('independent review incomplete or has must-fix findings')
                plan = build_delivery_plan(scope=scope, proposal=proposal, source_files=files,
                    snapshot=snapshot, repository=info.external_id, base_branch=info.default_branch,
                    issue_url=issue.external_url)
                value.update(phase='reviewed', reviewer=review_identity,
                             plan_fingerprint=plan.fingerprint)
                _artifact(factory, run_id, value)
            except Exception as exc:
                # Keep the last durable phase and exact Run, never pretend execution succeeded.
                raise DevelopmentStopped(run_id, stage + ' stopped before delivery') from exc
        guards = _LocalGuards(factory, config, plan.run_id)
        try:
            pr = deliver_draft(plan=plan, state=delivery_state,
                               scm=scm, guards=guards)
        except Exception as exc:
            raise DevelopmentStopped(plan.run_id,
                                     'delivery stopped; reconcile the same Run') from exc
        value.update(phase='delivered', pull_request=asdict(pr))
        _artifact(factory, plan.run_id, value)
        return {'run_id': plan.run_id, 'status': 'draft_pr_created', 'pull_request': asdict(pr)}
