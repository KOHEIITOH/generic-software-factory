"""Compose the local operator entry using default integrations and optional AI."""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path

from sf_factory.development_config import DevelopmentConfig
from sf_factory.file_state import _unique_object
from sf_factory.issue_development import DevelopmentStopped, develop_issue
from sf_factory.model_provider import ModelProvider, ModelResponse


class _NoInference:
    def generate(self, prompt: str) -> ModelResponse:
        raise RuntimeError('resume never starts inference')


def operator_document(path: Path) -> dict:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        metadata = os.fstat(stream.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 262144:
            raise ValueError('bounded regular config file required')
        if metadata.st_uid != os.getuid() or metadata.st_mode & 0o022:
            raise PermissionError('config must be operator-owned and not writable by others')
        raw = stream.read(262145)
    if len(raw) > 262144:
        raise ValueError('config exceeds budget')
    document = json.loads(raw, object_pairs_hook=_unique_object)
    if not isinstance(document, dict):
        raise ValueError('operator config object required')
    return document


def load_config(path: Path) -> DevelopmentConfig:
    document = operator_document(path)
    project_file = document.pop('project_harness_file', None)
    if project_file is not None:
        if 'project_harness' in document:
            raise ValueError('choose inline Project Harness or a shared operator file')
        project_path = Path(project_file)
        if (not project_path.is_absolute() or
                project_path.resolve(strict=True).is_relative_to(Path(document['root']))):
            raise PermissionError('Project Harness file must be outside target repository')
        document['project_harness'] = operator_document(project_path)
    config = DevelopmentConfig.from_document(document)
    if path.resolve(strict=True).is_relative_to(config.root):
        raise PermissionError('execution config must be outside the target repository')
    return config


class ConfirmationRequired(ValueError):
    pass


def execute_local_development(*, config_path: Path, confirmed: bool, confirm_bedrock: bool,
                              resume: str | None = None, review_run: str | None = None,
                              trusted_reviewers: tuple[str, ...] = (),
                              workflow_action: str | None = None,
                              expected_fingerprint: str | None = None) -> dict:
    """Trusted local operator entry shared by CLI and the private Web worker."""
    if confirmed is not True:
        raise ConfirmationRequired('--confirm-run')
    config = load_config(config_path)
    if expected_fingerprint is not None and config.fingerprint != expected_fingerprint:
        raise PermissionError('approved execution configuration changed')
    implementation: ModelProvider
    review: ModelProvider
    if resume is not None:
        implementation, review = _NoInference(), _NoInference()
    elif config.provider == 'bedrock':
        if confirm_bedrock is not True:
            raise ConfirmationRequired('--confirm-bedrock')
        from sf_factory.bedrock_provider import BedrockModelProvider
        from sf_factory.model_provider_status import bedrock_configuration

        settings = bedrock_configuration()
        if not settings.configured or not settings.model_id or not settings.region_name:
            raise ValueError('Bedrock SDK, model ID and region must be configured')
        max_tokens = int(os.environ.get('SF_BEDROCK_MAX_TOKENS', '8192'))
        implementation = BedrockModelProvider(settings.model_id, settings.region_name,
                                              max_tokens=max_tokens)
        review = BedrockModelProvider(settings.model_id, settings.region_name,
                                       max_tokens=max_tokens)
    else:
        from sf_factory.copilot_model_provider import CopilotModelProvider

        implementation, review = CopilotModelProvider(), CopilotModelProvider()
    from sf_factory.factory_selection import open_factory
    from sf_factory.integration_defaults import source_control, task_source

    if workflow_action is not None:
        from sf_factory.github_issue_tracker import GitHubIssueTracker
        from sf_factory.requirement_workflow import advance_requirements

        if workflow_action not in {'plan', 'advance'}:
            raise ValueError('known workflow action required')
        adapter = GitHubIssueTracker()
        result = advance_requirements(factory=open_factory(config.data_root), config=config,
            source=task_source(config.repository), scm=adapter, tracker=adapter,
            implementer=implementation, reviewer=review, confirmed=True,
            execute=workflow_action == 'advance', trusted_reviewers=trusted_reviewers)
    elif review_run is not None:
        from sf_factory.github_source_control import GitHubSourceControl
        from sf_factory.review_automation import advance_review

        result = advance_review(factory=open_factory(config.data_root), config=config,
            source=task_source(config.repository), scm=GitHubSourceControl(),
            implementer=implementation, reviewer=review, confirmed=True,
            initial_run=review_run, trusted_reviewers=trusted_reviewers)
    else:
        result = develop_issue(factory=open_factory(config.data_root), config=config,
            source=task_source(config.repository), scm=source_control(),
            implementer=implementation, reviewer=review, confirmed=True, resume=resume)
    return result


def run_local_development(*, config_path: Path, confirmed: bool, confirm_bedrock: bool,
                          resume: str | None, review_run: str | None = None,
                          trusted_reviewers: tuple[str, ...] = (),
                          workflow_action: str | None = None) -> int:
    try:
        result = execute_local_development(config_path=config_path, confirmed=confirmed,
            confirm_bedrock=confirm_bedrock, resume=resume, review_run=review_run,
            trusted_reviewers=trusted_reviewers, workflow_action=workflow_action)
        print(json.dumps(result))
        return 1 if result['status'] == 'stopped' else 0
    except ConfirmationRequired as exc:
        print(json.dumps({'status': 'confirmation_required', 'required': str(exc)}))
        return 2
    except DevelopmentStopped as exc:
        print(json.dumps({'status': 'stopped', 'run_id': exc.run_id, 'reason': str(exc)}))
        return 1
    except Exception:
        print(json.dumps({'status': 'blocked',
                          'reason': 'configuration or prerequisite check failed'}))
        return 2
