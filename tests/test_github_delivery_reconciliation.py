"""Reconcile the exact existing remote artifact without overwriting or duplicating."""
import copy
import io
import json
from urllib.error import HTTPError

import pytest

from sf_factory.github_source_control import GitHubSourceControl
from sf_factory.source_control import SourceControlError

REVISION = 'a' * 40
MARKER = '<!-- sf-delivery exact fixture -->'


def pr():
    return {'number': 7, 'html_url': 'https://github.com/example/repo/pull/7',
        'head': {'ref': 'sf/fixture', 'sha': REVISION, 'repo': {'full_name': 'example/repo'}},
        'base': {'ref': 'main', 'repo': {'full_name': 'example/repo'}},
        'state': 'open', 'draft': True, 'body': 'fixture\n' + MARKER, 'merged_at': None}


class Response(io.BytesIO):
    def __init__(self, data, headers=None):
        super().__init__(json.dumps(data).encode())
        self.headers = headers or {}


class Server:
    def __init__(self):
        self.calls = []
        self.revision = None
        self.items = []
        self.headers = {}
        self.fail_post = False
        self.post_visible = True

    def __call__(self, request, timeout):
        self.calls.append(request)
        if request.method == 'POST':
            if self.fail_post:
                raise TimeoutError('uncertain write')
            assert request.full_url.endswith('/git/refs')
            body = json.loads(request.data)
            assert body == {'ref': 'refs/heads/sf/fixture', 'sha': REVISION}
            if self.post_visible:
                self.revision = body['sha']
            return Response({})
        if '/pulls?' in request.full_url:
            assert 'state=all' in request.full_url
            assert '&base=' not in request.full_url  # A changed base must remain visible.
            return Response(self.items, self.headers)
        if self.revision is None:
            raise HTTPError(request.full_url, 404, 'missing', {}, None)
        return Response({'ref': 'refs/heads/sf/fixture',
                         'object': {'type': 'commit', 'sha': self.revision}})


@pytest.fixture
def server(monkeypatch):
    server = Server()
    monkeypatch.setenv('GH_TOKEN', 'fixture-token')
    monkeypatch.setattr('sf_factory.github_source_control.urlopen', server)
    return server


def find():
    return GitHubSourceControl().find_draft_pull_request('example/repo', head='sf/fixture',
        base='main', revision=REVISION, marker=MARKER)


def test_absent_branch_is_created_once_then_verified(server):
    adapter = GitHubSourceControl()
    adapter.ensure_branch('example/repo', 'sf/fixture', REVISION)
    adapter.ensure_branch('example/repo', 'sf/fixture', REVISION)
    assert sum(r.method == 'POST' for r in server.calls) == 1
    assert server.calls[-1].method == 'GET'


def test_other_commit_is_never_overwritten(server):
    server.revision = 'b' * 40
    with pytest.raises(SourceControlError, match='differs'):
        GitHubSourceControl().ensure_branch('example/repo', 'sf/fixture', REVISION)
    assert all(r.method == 'GET' for r in server.calls)


@pytest.mark.parametrize('uncertain', ['timeout', 'not_visible'])
def test_uncertain_create_never_retries(server, uncertain):
    server.fail_post = uncertain == 'timeout'
    server.post_visible = uncertain != 'not_visible'
    with pytest.raises(SourceControlError):
        GitHubSourceControl().ensure_branch('example/repo', 'sf/fixture', REVISION)
    assert sum(r.method == 'POST' for r in server.calls) == 1


def test_absent_or_exact_draft_lookup_is_read_only(server):
    assert find() is None
    server.items = [pr()]
    assert find().external_id == '7'
    assert all(r.method == 'GET' for r in server.calls)


@pytest.mark.parametrize('field,value', [('draft', False), ('state', 'closed'),
    ('merged_at', '2026-01-01'), ('body', 'different marker'), ('number', True),
    ('html_url', 'https://other.invalid'), ('head', None), ('base', None)])
def test_changed_pr_is_not_reused_or_replaced(server, field, value):
    item = pr()
    item[field] = value
    server.items = [item]
    with pytest.raises(SourceControlError):
        find()
    assert all(r.method == 'GET' for r in server.calls)


@pytest.mark.parametrize('field,key,value', [('head', 'sha', 'b' * 40),
    ('head', 'ref', 'other'), ('base', 'ref', 'release'),
    ('head', 'repo', {'full_name': 'fork/repo'}), ('base', 'repo', None)])
def test_other_revision_repository_or_branch_blocks_reconciliation(server, field, key, value):
    item = pr()
    item[field][key] = value
    server.items = [item]
    with pytest.raises(SourceControlError):
        find()


@pytest.mark.parametrize('case', ['ambiguous', 'full_page', 'pagination', 'malformed'])
def test_incomplete_or_ambiguous_list_cannot_mean_no_pr(server, case):
    if case == 'ambiguous':
        server.items = [pr(), copy.deepcopy(pr())]
    elif case == 'full_page':
        server.items = [pr()] * 100
    elif case == 'pagination':
        server.items = [pr()]
        server.headers = {'Link': '<https://api.github.com/next>; rel="next"'}
    else:
        server.items = {}
    with pytest.raises(SourceControlError):
        find()
