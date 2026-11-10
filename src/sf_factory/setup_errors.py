"""Public setup diagnostics use fixed codes, never exception text or local paths."""

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
