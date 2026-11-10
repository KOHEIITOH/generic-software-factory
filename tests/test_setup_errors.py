"""Transport diagnostics never expose remote responses, URLs, or credentials."""
from urllib.error import HTTPError, URLError

import pytest

from sf_factory.setup_errors import source_setup_error
from sf_factory.source_control import SourceControlError


@pytest.mark.parametrize('kind,message,cause,code', [
    ('not_configured', 'private', None, 'scm_credentials_missing'),
    ('access_denied', 'private', None, 'scm_access_denied'),
    ('invalid_response', 'private', None, 'scm_response_invalid'),
    ('unavailable', 'private', None, 'scm_unavailable'),
    ('unavailable', 'Remote source read deadline exceeded', None, 'scm_source_deadline'),
    ('invalid_response', 'Remote source budget exceeded', None, 'scm_source_limit'),
    ('invalid_response', 'Unsupported remote source object', None, 'scm_source_type'),
    ('invalid_response', 'Complete bounded remote tree required', None, 'scm_source_inventory'),
    ('unavailable', 'private', TimeoutError('private'), 'scm_timeout'),
    ('unavailable', 'private', URLError(TimeoutError('private')), 'scm_timeout'),
    ('access_denied', 'private', HTTPError('private', 401, 'private', {}, None),
     'scm_credentials_rejected'),
    ('access_denied', 'private', HTTPError('private', 404, 'private', {}, None),
     'scm_repository_unavailable'),
    ('unavailable', 'private', HTTPError('private', 429, 'private', {}, None),
     'scm_rate_limited'),
    ('access_denied', 'private', HTTPError('private', 403, 'private',
     {'X-RateLimit-Remaining': '0'}, None), 'scm_rate_limited'),
    ('access_denied', 'private', HTTPError('private', 403, 'private',
     {'Retry-After': '60'}, None), 'scm_rate_limited'),
    ('access_denied', 'private', HTTPError('private', 403, 'private', {}, None),
     'scm_access_denied'),
])
def test_source_error_codes_are_safe_and_actionable(kind, message, cause, code):
    error = SourceControlError(kind, message)
    error.__cause__ = cause
    assert source_setup_error(error) == {'code': code}
