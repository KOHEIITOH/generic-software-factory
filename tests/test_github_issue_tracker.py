"""Native external Issues only, exact readback, no silent reparenting."""
import copy

import pytest

from sf_factory.github_issue_tracker import GitHubIssueTracker
from sf_factory.source_control import SourceControlError

MARKER = '<!-- sf-child:' + 'a' * 64 + ':first -->'


def issue(number, body='body'):
    return {'id': f'I{number}', 'number': number, 'title': f'Issue {number}', 'body': body,
            'url': f'https://github.com/example/repo/issues/{number}',
            'repository': {'nameWithOwner': 'example/repo'}, 'parent': None}


class Tracker(GitHubIssueTracker):
    def __init__(self):
        self.items = {'1': issue(1), '2': issue(2, MARKER)}
        self.children = []
        self.search = {'issueCount': 1, 'pageInfo': {'hasNextPage': False},
                       'nodes': [self.items['2']]}
        self.calls = []

    def _request(self, path, method='GET', payload=None, **kwargs):
        self.calls.append((path, method, copy.deepcopy(payload)))
        if path.endswith('/issues'):
            self.items['3'] = {**issue(3), **payload}
            return {'number': 3}
        query = payload['query']
        variables = payload['variables']
        if 'search(' in query:
            return {'data': {'search': self.search}}
        if 'addSubIssue' in query:
            self.children.append(self.items['2'])
            self.items['2']['parent'] = {k: self.items['1'][k]
                                        for k in ('id', 'number', 'repository')}
            return {'data': {'addSubIssue': {'issue': {'id': 'I1'}, 'subIssue': {'id': 'I2'}}}}
        if 'subIssues(' in query:
            return {'data': {'repository': {'nameWithOwner': 'example/repo', 'issue': {
                'number': 1, 'subIssues': {'pageInfo': {'hasNextPage': False},
                                        'nodes': self.children}}}}}
        return {'data': {'repository': {'issue': self.items[str(variables['number'])]}}}


def test_native_parent_link_is_verified_and_never_replaced():
    tracker = Tracker()
    tracker.attach_child('example/repo', '1', '2')
    mutations = [p for _, _, p in tracker.calls if 'addSubIssue' in p.get('query', '')]
    assert mutations[0]['variables']['input'] == {
        'issueId': 'I1', 'subIssueId': 'I2', 'replaceParent': False}
    count = len(mutations)
    tracker.attach_child('example/repo', '1', '2')
    assert len([p for _, _, p in tracker.calls if 'addSubIssue' in p.get('query', '')]) == count


def test_existing_other_parent_blocks_without_mutation():
    tracker = Tracker()
    tracker.items['2']['parent'] = {'id': 'other', 'number': 9,
                                  'repository': {'nameWithOwner': 'example/repo'}}
    with pytest.raises(SourceControlError, match='another parent'):
        tracker.attach_child('example/repo', '1', '2')
    assert not any('addSubIssue' in p.get('query', '') for _, _, p in tracker.calls)


def test_issue_creation_checks_authoritative_exact_content():
    result = Tracker().create_issue('example/repo', title='Completable change', body=MARKER)
    assert result.external_id == '3' and MARKER in result.prompt


@pytest.mark.parametrize('case', ['truncated', 'duplicate', 'foreign', 'invalid_number'])
def test_incomplete_ambiguous_or_wrong_repo_search_is_not_absence(case):
    tracker = Tracker()
    if case == 'truncated':
        tracker.search['pageInfo']['hasNextPage'] = True
    elif case == 'duplicate':
        tracker.search['issueCount'] = 2
        tracker.search['nodes'] = [issue(2, MARKER), issue(3, MARKER)]
    elif case == 'foreign':
        tracker.items['2']['repository']['nameWithOwner'] = 'attacker/repo'
    else:
        tracker.items['2']['number'] = True
    with pytest.raises(SourceControlError):
        tracker.find_issue('example/repo', MARKER)


def test_search_and_native_children_return_external_issue_references():
    tracker = Tracker()
    assert tracker.find_issue('example/repo', MARKER).external_id == '2'
    assert tracker.child_issues('example/repo', '1') == ()
    tracker.attach_child('example/repo', '1', '2')
    assert tracker.child_issues('example/repo', '1')[0].provider == 'github'
