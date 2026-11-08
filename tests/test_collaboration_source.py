"""Remote revisions, review discussions and atomic ref CAS never trust partial data."""
import base64
import copy
import hashlib

import pytest

from sf_factory.github_source_control import GitHubSourceControl
from sf_factory.source_control import SourceControlError

REV, TREE, NEXT = 'a' * 40, 'b' * 40, 'c' * 40
BODY = b'original source\n'
BLOB = hashlib.sha1(b'blob ' + str(len(BODY)).encode() + b'\0' + BODY).hexdigest()


def pr_data():
    return {'repository': {'nameWithOwner': 'example/repo', 'pullRequest': {
        'number': 1, 'url': 'https://github.com/example/repo/pull/1', 'body': 'factory marker',
        'state': 'OPEN', 'isDraft': True, 'merged': False,
        'headRefName': 'sf/fixture', 'headRefOid': REV, 'baseRefName': 'main', 'baseRefOid': TREE,
        'headRepository': {'nameWithOwner': 'example/repo'},
        'reviews': {'pageInfo': {'hasPreviousPage': False}, 'nodes': [
            {'id': 'review-1', 'author': {'login': 'reviewer'}, 'body': 'Please fix the edge case',
             'state': 'CHANGES_REQUESTED', 'commit': {'oid': REV}}]},
        'reviewThreads': {'pageInfo': {'hasNextPage': False}, 'nodes': [{
            'id': 'thread-1', 'isResolved': False, 'isOutdated': True, 'path': 'app.py',
            'comments': {'pageInfo': {'hasPreviousPage': False}, 'nodes': [{
                'id': 'comment-1', 'author': {'login': 'reviewer'},
                'body': 'Handle zero', 'commit': {'oid': REV}}]}}]}}}}


class SCM(GitHubSourceControl):
    def __init__(self):
        self.calls = []
        self.pr = pr_data()
        self.sha = REV
        self.cas_errors = False
        self.tree = {'sha': TREE, 'truncated': False, 'tree': [
            {'path': 'app.py', 'mode': '100644', 'type': 'blob', 'size': len(BODY), 'sha': BLOB}]}
        self.blob = {'sha': BLOB, 'encoding': 'base64',
                     'content': base64.b64encode(BODY).decode()}

    def _request(self, path, method='GET', payload=None, **kwargs):
        self.calls.append((path, method, copy.deepcopy(payload)))
        if path == '/graphql':
            if 'updateRefs' in payload['query']:
                if self.cas_errors:
                    return {'errors': [{'message': 'beforeOid mismatch'}]}
                self.sha = payload['variables']['input']['refUpdates'][0]['afterOid']
                return {'data': {'updateRefs': {'clientMutationId': None}}}
            return {'data': self.pr}
        if '/git/ref/heads/' in path:
            return {'ref': 'refs/heads/sf/fixture', 'object': {'type': 'commit', 'sha': self.sha}}
        if '/git/commits/' in path:
            return {'sha': REV, 'tree': {'sha': TREE}}
        if '/git/trees/' in path:
            return self.tree
        if '/git/blobs/' in path:
            return self.blob
        return {'node_id': 'repository-node', 'full_name': 'example/repo'}


def test_ref_update_supplies_atomic_before_after_and_never_forces():
    scm = SCM()
    scm.compare_update_branch('example/repo', 'sf/fixture', expected=REV, revision=NEXT)
    mutation = next(payload for path, _, payload in scm.calls if path == '/graphql')
    assert mutation['variables']['input'] == {'repositoryId': 'repository-node', 'refUpdates': [{
        'name': 'refs/heads/sf/fixture', 'beforeOid': REV, 'afterOid': NEXT, 'force': False}]}
    assert scm.calls[-1][0].endswith('/git/ref/heads/sf%2Ffixture')


def test_cas_conflict_never_falls_back_to_rest_force_update():
    scm = SCM()
    scm.cas_errors = True
    with pytest.raises(SourceControlError):
        scm.compare_update_branch('example/repo', 'sf/fixture', expected=REV, revision=NEXT)
    assert scm.sha == REV
    assert not any(method == 'PATCH' for _, method, _ in scm.calls)


def test_read_revision_binds_exact_blob_bytes_and_modes():
    source = SCM().read_revision('example/repo', REV)
    assert source.revision == REV
    assert source.files[0].content == BODY
    assert source.files[0].mode == '100644'
    assert len(source.fingerprint) == 64


@pytest.mark.parametrize('case', ['truncated', 'sensitive', 'symlink', 'duplicate', 'oversize'])
def test_bad_remote_inventory_is_rejected_before_blob_reads(case):
    scm = SCM()
    entry = scm.tree['tree'][0]
    if case == 'truncated':
        scm.tree['truncated'] = True
    elif case == 'sensitive':
        entry['path'] = '.env'
    elif case == 'symlink':
        entry['mode'] = '120000'
    elif case == 'duplicate':
        scm.tree['tree'].append(copy.deepcopy(entry))
    else:
        entry['size'] = 1048577
    with pytest.raises((ValueError, SourceControlError)):
        scm.read_revision('example/repo', REV)
    assert not any('/git/blobs/' in path for path, _, _ in scm.calls)


def test_changed_blob_bytes_fail_hash_validation():
    scm = SCM()
    scm.blob['content'] = base64.b64encode(b'other source').decode()
    with pytest.raises(SourceControlError):
        scm.read_revision('example/repo', REV)


def test_unresolved_outdated_feedback_is_not_silently_dropped():
    result = SCM().pull_request_snapshot('example/repo', '1')
    assert not result.approved
    assert [f.id for f in result.feedback] == ['review-1', 'comment-1']
    assert result.feedback[1].state == 'outdated'
    assert result.decisions[0].state == 'changes_requested'


@pytest.mark.parametrize('case', ['reviews_page', 'threads_page', 'comments_page', 'fork',
                                  'other_revision', 'deleted_author', 'unknown_state'])
def test_incomplete_or_wrong_pr_data_never_looks_reviewed(case):
    scm = SCM()
    pr = scm.pr['repository']['pullRequest']
    if case == 'reviews_page':
        pr['reviews']['pageInfo']['hasPreviousPage'] = True
    elif case == 'threads_page':
        pr['reviewThreads']['pageInfo']['hasNextPage'] = True
    elif case == 'comments_page':
        pr['reviewThreads']['nodes'][0]['comments']['pageInfo']['hasPreviousPage'] = True
    elif case == 'fork':
        pr['headRepository']['nameWithOwner'] = 'other/repo'
    elif case == 'other_revision':
        pr['headRefOid'] = 'wrong'
    elif case == 'deleted_author':
        pr['reviews']['nodes'][0]['author'] = None
    else:
        pr['state'] = 'UNKNOWN'
    with pytest.raises(SourceControlError):
        scm.pull_request_snapshot('example/repo', '1')


def test_approval_is_latest_per_author_and_exact_head_only():
    scm = SCM()
    pr = scm.pr['repository']['pullRequest']
    approval = copy.deepcopy(pr['reviews']['nodes'][0])
    approval.update(id='review-2', state='APPROVED', body='')
    pr['reviews']['nodes'].append(approval)
    assert scm.pull_request_snapshot('example/repo', '1').approved
    approval['commit']['oid'] = NEXT
    assert not scm.pull_request_snapshot('example/repo', '1').approved
