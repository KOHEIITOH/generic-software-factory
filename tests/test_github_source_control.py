"""GitHub transport/serialization is isolated from the common SCM contract."""
import io
import json
from urllib.error import HTTPError, URLError

import pytest

from sf_factory.github_source_control import GitHubSourceControl
from sf_factory.source_control import SourceControlError


def test_adapter_serializes_github_calls_and_forces_draft(monkeypatch):
    requests = []
    def respond(request, timeout):
        requests.append(request)
        if request.full_url.endswith('/repos/example/repo'):
            data = {'full_name': 'example/repo', 'default_branch': 'feature/base',
                    'permissions': {'push': True}}
        elif '/git/ref/' in request.full_url:
            data = {'object': {'sha': 'a' * 40}}
        elif request.full_url.endswith('/pulls'):
            data = {'number': 7, 'html_url': 'https://github.com/example/repo/pull/7'}
        else:
            data = {}
        return io.BytesIO(json.dumps(data).encode())
    monkeypatch.setenv('GH_TOKEN', 'test-only-token')
    monkeypatch.setattr('sf_factory.github_source_control.urlopen', respond)
    adapter = GitHubSourceControl()
    info = adapter.describe_repository('example/repo')
    assert info.capabilities.write is True
    revision = adapter.branch_revision(info.external_id, info.default_branch)
    adapter.create_branch(info.external_id, 'sf-demo-fixture', revision)
    adapter.write_file(info.external_id, branch='sf-demo-fixture', path='.demo/marker.md',
                       content=b'fixture', message='demo')
    pr = adapter.create_draft_pull_request(info.external_id, title='demo', head='sf-demo-fixture',
                                           base=info.default_branch, body='fixture')
    assert pr.external_id == '7'
    assert requests[1].full_url.endswith('/git/ref/heads/feature%2Fbase')
    assert json.loads(requests[-1].data)['draft'] is True
    assert json.loads(requests[-2].data)['content'] == 'Zml4dHVyZQ=='
    assert all(request.get_header('Authorization') == 'Bearer test-only-token'
               for request in requests)


def test_missing_credentials_never_calls_network(monkeypatch):
    monkeypatch.delenv('GH_TOKEN', raising=False)
    monkeypatch.delenv('GITHUB_TOKEN', raising=False)
    def unexpected(*args, **kwargs):
        pytest.fail('missing credentials must not trigger network')
    monkeypatch.setattr('sf_factory.github_source_control.urlopen', unexpected)
    with pytest.raises(SourceControlError) as error:
        GitHubSourceControl().describe_repository('example/repo')
    assert error.value.kind == 'not_configured'


@pytest.mark.parametrize('failure,kind', [
    (HTTPError('https://api.github.com', 403, 'private detail', {}, None), 'access_denied'),
    (HTTPError('https://api.github.com', 500, 'private detail', {}, None), 'unavailable'),
    (URLError('private detail'), 'unavailable'),
])
def test_transport_errors_are_domain_errors_without_raw_details(monkeypatch, failure, kind):
    monkeypatch.setenv('GH_TOKEN', 'test-only')
    def fail(*args, **kwargs):
        raise failure
    monkeypatch.setattr('sf_factory.github_source_control.urlopen', fail)
    with pytest.raises(SourceControlError) as error:
        GitHubSourceControl().describe_repository('example/repo')
    assert error.value.kind == kind
    assert 'private detail' not in str(error.value)


@pytest.mark.parametrize('payload', [b'[]', b'{', b'x' * 1048577])
def test_invalid_or_excessive_responses_fail_closed(monkeypatch, payload):
    monkeypatch.setenv('GH_TOKEN', 'test-only')
    monkeypatch.setattr('sf_factory.github_source_control.urlopen',
                        lambda *args, **kwargs: io.BytesIO(payload))
    with pytest.raises(SourceControlError) as error:
        GitHubSourceControl().describe_repository('example/repo')
    assert error.value.kind == 'invalid_response'


@pytest.mark.parametrize('repository', ['../bad', 'example/repo/other', 'https://evil.invalid'])
def test_repository_validation_prevents_network(monkeypatch, repository):
    def unexpected(*args, **kwargs):
        pytest.fail('invalid repository must not trigger network')
    monkeypatch.setattr('sf_factory.github_source_control.urlopen', unexpected)
    with pytest.raises(ValueError):
        GitHubSourceControl().describe_repository(repository)
