"""Read-only preparation checks. No model inference, credential resolution or writes."""
from __future__ import annotations

import importlib.util
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

from sf_factory import docker_execution
from sf_factory.github_auth import credential_status
from sf_factory.harness_composition import compose_harness
from sf_factory.harness_runs import _revision
from sf_factory.harness_validation import validate_harness
from sf_factory.integration_defaults import DEFAULT_TASK_SOURCE, repository_binding, source_control
from sf_factory.model_provider_status import bedrock_configuration
from sf_factory.web_operator import OperatorProfiles


def diagnose_profile(root: Path, profile_id: str, expected: str, *, check_remote=False) -> dict:
    rows = []
    def add(key, status, detail, remedy=''):
        rows.append({'id': key, 'status': status, 'detail': detail, 'remedy': remedy})
    try:
        _, config = OperatorProfiles(root).get(profile_id, expected)
    except Exception:
        add('configuration', 'blocked', '登録設定が変更・失効、または読み取れません。',
            '同じ保存先を使い、ターミナルで設定を確認して登録し直してください。')
        return {'checked_at': datetime.now(UTC).isoformat(), 'checks': rows, 'can_attempt': False}
    add('configuration', 'ok', '登録設定と保存先の一致を確認しました。')
    add('python_git', 'ok' if sys.version_info >= (3, 11) and shutil.which('git') else 'blocked',
        'Python 3.11以上とGitが必要です。', 'PythonとGitを導入してください。')
    try:
        _revision(config.root)
        repository_binding().verify(provider=DEFAULT_TASK_SOURCE, instance=config.repository,
                                    repository=config.repository, local_path=config.root)
        compose_harness(validate_harness(config.root), target='.', selected=config.selected_harness,
            excluded=config.excluded_harness, project_harness=config.project_harness,
            change_paths=config.allowed_paths)
        add('repository_harness', 'ok',
            'cleanなGit root・origin・Harnessの適用範囲を確認しました。')
    except Exception:
        add('repository_harness', 'blocked', '作業ツリー・origin・Harnessを確認できません。',
            '変更を整理し、対象repoとorigin、Harnessの選択/除外を確認してください。')
    if config.provider == 'bedrock':
        settings = bedrock_configuration()
        add('model_configuration', 'ok' if settings.configured else 'blocked',
            'Bedrock SDK・モデルID・リージョンの設定を確認します。',
            'bedrock extra、SF_BEDROCK_MODEL_ID、SF_BEDROCK_REGIONを確認してください。')
        add('model_authorization', 'unknown', 'AWS認証・モデル利用権限は未確認です。推論しません。',
            'PCのAWS SDK標準認証を設定し、実行時の認証・モデル利用権限を確認してください。')
    else:
        installed = importlib.util.find_spec('copilot') is not None and shutil.which('copilot')
        add('model_configuration', 'ok' if installed else 'blocked',
            'Copilot SDKとCLIの導入を確認します。', 'Copilot SDK/CLIと認証を設定してください。')
        add('model_authorization', 'unknown', 'Copilot認証は未確認です。推論しません。')
    capable = docker_execution.resource_limits_available()
    add('docker_limits', 'ok' if capable else 'blocked',
        '指定したローカルDocker daemonの資源制限能力を確認します。',
        'Dockerを起動し、cgroup v2とCPU・memory・pids制限を有効にしてください。')
    try:
        image = docker_execution._docker(['image', 'inspect', '--format', '{{.Id}}', config.image],
                                         timeout=5)
        present = image.returncode == 0 and image.stdout.strip().startswith('sha256:')
    except Exception:
        present = False
    add('execution_image', 'ok' if present else 'blocked',
        '固定digestの実行imageがローカルdaemonに存在するか確認します。',
        'ターミナルで承認済みの固定digest imageをpullしてください。診断はpullしません。')
    configured = credential_status()['configured']
    add('scm_credentials', 'ok' if configured else 'blocked',
        'Git連携用の環境認証設定の有無を確認します。認証値は表示しません。',
        'SFを起動する環境のGH_TOKENまたはGITHUB_TOKENを設定してください。')
    if check_remote and configured:
        try:
            info = source_control().describe_repository(config.repository)
            add('repository_access', 'ok' if info.capabilities.read else 'blocked',
                'SCM Adapter経由で対象Repositoryの読み取りを確認しました。')
            add('repository_push', 'ok' if info.capabilities.write else 'blocked',
                'Adapterが返すRepositoryのpush権限を確認しました。',
                '対象Repositoryへの書き込み権限を確認してください。')
        except Exception:
            add('repository_access', 'blocked', '対象Repositoryへ接続・認証できません。',
                '認証、Repository権限、ネットワークを確認してください。')
    else:
        add('repository_access', 'unknown', '実サービスへの接続・認証は未確認です。',
            '必要に応じて「GitHub接続・権限を確認」を実行してください。')
    add('issue_pr_write', 'unknown', 'Issue作成・親子関連・PR作成の書き込み権限は未確認です。',
        '対象RepositoryのIssues・Pull requests・Contents権限を確認してください。'
        '診断は変更しません。')
    return {'checked_at': datetime.now(UTC).isoformat(), 'checks': rows,
            'can_attempt': not any(r['status'] == 'blocked' for r in rows),
            'inference_invoked': False, 'remote_checked': bool(check_remote and configured)}
