"""Public setup diagnostics use fixed codes, never exception text or local paths."""
from urllib.error import HTTPError, URLError

from sf_factory.source_control import SourceControlError

_MESSAGES = {
    'canonical repository location required': 'repository_location',
    'repository overlaps Factory storage': 'state_overlap',
    'prepare requires a clean tracked and untracked worktree': 'worktree_dirty',
    'canonical repository outside Factory storage required': 'repository_location',
    'an explicit canonical repository root is required': 'repository_location',
    'repository root mismatch': 'repository_location',
    'could not verify repository revision': 'repository_revision',
    'repositories with configured Git filters are unsupported': 'git_filters',
    'Git origin is not configured': 'repository_origin',
    'Git origin must be a GitHub HTTPS or SSH URL': 'repository_origin',
    'supported GitHub origin required': 'repository_origin',
    'selected GitHub repository does not match Git origin': 'repository_origin',
    'explicit application source paths required; tests remain read-only': 'change_scope',
    'explicit bounded unique change scope required': 'change_scope',
    'supported text provider and digest-pinned image required': 'execution_image',
    'bounded approved behavioral test required': 'behavioral_checks',
    'unresolved validation problem': 'harness_validation',
    'incomplete discovery cannot be composed': 'harness_validation',
    'symlinks and submodules require separate setup': 'source_types',
    'bounded nonempty source tree required': 'source_size',
    'bounded setup name required': 'setup_name',
}


def setup_error(exc: Exception) -> dict[str, str]:
    if isinstance(exc, FileNotFoundError):
        return {'code': 'repository_missing'}
    return {'code': _MESSAGES.get(str(exc), 'setup_invalid')}


def source_setup_error(exc: SourceControlError) -> dict[str, str]:
    """Distinguish actionable failures using allowlisted transport evidence only."""
    cause = exc.__cause__
    if isinstance(cause, HTTPError):
        if cause.code == 429 or (cause.code == 403 and (
                cause.headers.get('X-RateLimit-Remaining') == '0'
                or cause.headers.get('Retry-After') is not None)):
            return {'code': 'scm_rate_limited'}
        if cause.code == 401:
            return {'code': 'scm_credentials_rejected'}
        if cause.code == 404:
            return {'code': 'scm_repository_unavailable'}
    if isinstance(cause, TimeoutError) or (
            isinstance(cause, URLError) and isinstance(cause.reason, TimeoutError)):
        return {'code': 'scm_timeout'}
    known = {
        'Remote source read deadline exceeded': 'scm_source_deadline',
        'Remote source budget exceeded': 'scm_source_limit',
        'Unsupported remote source object': 'scm_source_type',
        'Complete bounded remote tree required': 'scm_source_inventory',
    }
    fallback = {'not_configured': 'scm_credentials_missing',
                'access_denied': 'scm_access_denied', 'unavailable': 'scm_unavailable',
                'invalid_response': 'scm_response_invalid'}
    return {'code': known.get(str(exc), fallback.get(exc.kind, 'scm_unavailable'))}
