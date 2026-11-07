"""Exact multi-file commit preparation, with no branch/PR writes or live calls."""
import base64
import copy
import hashlib
from dataclasses import replace

import pytest

from sf_factory.github_source_control import GitHubSourceControl
from sf_factory.source_control import CommitChange, SourceControlError

PARENT, TREE, NEW_TREE, COMMIT = ('a' * 40, 'b' * 40, 'c' * 40, 'd' * 40)
CHANGES = (CommitChange('app.py', b'old\n', b'new\n', True),
           CommitChange('src/new.py', None, b'created\n'))


def blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


class FakeGitHub(GitHubSourceControl):
    def __init__(self):
        self.calls = []
        self.parent = {'sha': PARENT, 'tree': {'sha': TREE}}
        self.tree = {'sha': TREE, 'truncated': False, 'tree': [
            {'path': 'app.py', 'mode': '100755', 'type': 'blob', 'sha': blob(b'old\n')},
            {'path': 'untouched.py', 'mode': '100644', 'type': 'blob', 'sha': blob(b'keep')}]}
        self.commit = {'sha': COMMIT, 'tree': {'sha': NEW_TREE}, 'parents': [{'sha': PARENT}]}
        self.bad_blob = False
        self.fail_blob = False

    def _request(self, path, method='GET', payload=None):
        self.calls.append((path, method, copy.deepcopy(payload)))
        if path.endswith('/git/commits/' + PARENT):
            return self.parent
        if path.endswith('?recursive=1'):
            return self.tree
        if path.endswith('/git/blobs'):
            if self.fail_blob:
                raise SourceControlError('unavailable', 'unknown upload outcome')
            return {'sha': 'f' * 40 if self.bad_blob else
                    blob(base64.b64decode(payload['content']))}
        if path.endswith('/git/trees'):
            return {'sha': NEW_TREE}
        if path.endswith('/git/commits'):
            return self.commit
        pytest.fail('unexpected API operation')


def prepare(adapter, **kwargs):
    return adapter.prepare_commit('example/repo', parent_revision=PARENT,
                                  changes=CHANGES, message='approved candidate', **kwargs)


def test_one_commit_preserves_exact_bytes_modes_and_parent_without_publishing():
    adapter = FakeGitHub()
    result = prepare(adapter)
    assert (result.external_id, result.tree_id, result.parent_id) == (COMMIT, NEW_TREE, PARENT)
    posts = [(p, data) for p, method, data in adapter.calls if method == 'POST']
    assert [p.rsplit('/', 1)[-1] for p, _ in posts] == ['blobs', 'blobs', 'trees', 'commits']
    assert base64.b64decode(posts[0][1]['content']) == CHANGES[0].after
    assert posts[2][1] == {'base_tree': TREE, 'tree': [
        {'path': c.path, 'mode': '100755' if c.executable else '100644',
         'type': 'blob', 'sha': blob(c.after)} for c in CHANGES]}
    assert posts[3][1]['parents'] == [PARENT]
    assert not any('/refs' in path or '/pulls' in path for path, _, _ in adapter.calls)


@pytest.mark.parametrize('changes', [(), (CHANGES[0], CHANGES[0]),
    (replace(CHANGES[0], path='../escape'),), (replace(CHANGES[0], path='AGENTS.md'),),
    (replace(CHANGES[0], executable=1),), (replace(CHANGES[0], after=b'old\n'),),
    (CommitChange('x', None, b'x'), CommitChange('x/y', None, b'y'))])
def test_invalid_changes_never_call_network(changes):
    adapter = FakeGitHub()
    with pytest.raises(ValueError):
        adapter.prepare_commit('example/repo', parent_revision=PARENT,
                               changes=changes, message='candidate')
    assert adapter.calls == []


@pytest.mark.parametrize('case', ['parent', 'tree_id', 'truncated', 'duplicate', 'stale',
                                  'mode', 'new_exists', 'parent_file', 'submodule'])
def test_all_preconditions_fail_before_any_post(case):
    adapter = FakeGitHub()
    if case == 'parent':
        adapter.parent['sha'] = 'e' * 40
    elif case == 'tree_id':
        adapter.tree['sha'] = 'e' * 40
    elif case == 'truncated':
        adapter.tree['truncated'] = True
    elif case == 'duplicate':
        adapter.tree['tree'].append(adapter.tree['tree'][0])
    elif case == 'stale':
        adapter.tree['tree'][0]['sha'] = 'e' * 40
    elif case == 'mode':
        adapter.tree['tree'][0]['mode'] = '100644'
    elif case == 'new_exists':
        adapter.tree['tree'].append({'path': 'src/new.py', 'type': 'blob'})
    elif case == 'parent_file':
        adapter.tree['tree'].append({'path': 'src', 'type': 'blob'})
    else:
        adapter.tree['tree'].append({'path': 'src', 'type': 'commit', 'mode': '160000'})
    with pytest.raises(SourceControlError):
        prepare(adapter)
    assert not any(method == 'POST' for _, method, _ in adapter.calls)


def test_unverified_uploaded_bytes_never_reach_tree_or_commit():
    adapter = FakeGitHub()
    adapter.bad_blob = True
    with pytest.raises(SourceControlError, match='byte identity'):
        prepare(adapter)
    assert adapter.calls[-1][0].endswith('/git/blobs')


def test_unknown_mutation_outcome_is_not_retried_or_published():
    adapter = FakeGitHub()
    adapter.fail_blob = True
    with pytest.raises(SourceControlError):
        prepare(adapter)
    assert sum(method == 'POST' for _, method, _ in adapter.calls) == 1


@pytest.mark.parametrize('field,value', [('tree', {'sha': TREE}), ('parents', []),
    ('parents', [{'sha': 'e' * 40}]), ('parents', [{'sha': PARENT}, {'sha': PARENT}]),
    ('sha', None)])
def test_commit_receipt_must_match_candidate_and_single_parent(field, value):
    adapter = FakeGitHub()
    adapter.commit[field] = value
    with pytest.raises(SourceControlError):
        prepare(adapter)
    assert adapter.calls[-1][0].endswith('/git/commits')
