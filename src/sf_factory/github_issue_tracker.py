"""GitHub native child Issues behind the existing external Issue contract."""
from __future__ import annotations

import re

from sf_factory.github_source_control import GitHubSourceControl, _base
from sf_factory.source_control import SourceControlError
from sf_factory.task_sources import ExternalIssue

_FIELDS = 'id number title body url repository{nameWithOwner}'


def _number(value: str) -> int:
    if not isinstance(value, str) or not re.fullmatch(r'[1-9][0-9]{0,9}', value):
        raise ValueError('exact external Issue number required')
    return int(value)


def _external(repository: str, value: dict) -> ExternalIssue:
    try:
        number = value['number']
        title, body = value['title'], value['body']
        url = f'https://github.com/{repository}/issues/{number}'
        if (type(number) is not int or number < 1 or not isinstance(title, str)
                or not title.strip() or len(title) > 256 or not isinstance(body, str)
                or len(body) > 65536 or value['url'] != url
                or value['repository']['nameWithOwner'].casefold() != repository.casefold()
                or not isinstance(value['id'], str) or not value['id']):
            raise ValueError('Issue identity or content')
        return ExternalIssue('github', repository, str(number), title + '\n\n' + body, url)
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise SourceControlError('invalid_response', 'Invalid external Issue') from exc


class GitHubIssueTracker(GitHubSourceControl):
    def _issue(self, repository: str, external_id: str) -> dict:
        _base(repository)
        owner, name = repository.split('/')
        data = self._graphql('query($owner:String!,$name:String!,$number:Int!){'
            'repository(owner:$owner,name:$name){issue(number:$number){' + _FIELDS +
            ' parent{id number repository{nameWithOwner}}}}}',
            {'owner': owner, 'name': name, 'number': _number(external_id)})
        value = data.get('repository', {}).get('issue')
        if not isinstance(value, dict) or _external(repository, value).external_id != external_id:
            raise SourceControlError('invalid_response', 'Exact Issue required')
        return value

    def fetch(self, repository: str, external_id: str) -> ExternalIssue:
        return _external(repository, self._issue(repository, external_id))

    def find_issue(self, repository: str, marker: str) -> ExternalIssue | None:
        _base(repository)
        if not re.fullmatch(r'<!-- sf-child:[a-f0-9]{64}:[a-z][a-z0-9-]{0,31} -->', marker):
            raise ValueError('exact Factory child marker required')
        term = marker.removeprefix('<!-- ').removesuffix(' -->')
        data = self._graphql('query($q:String!){search(query:$q,type:ISSUE,first:20){'
            'issueCount pageInfo{hasNextPage}nodes{... on Issue{' + _FIELDS + '}}}}',
            {'q': f'repo:{repository} is:issue in:body "{term}"'})
        try:
            search = data['search']
            if (search['pageInfo']['hasNextPage'] is not False
                    or type(search['issueCount']) is not int or search['issueCount'] > 20
                    or len(search['nodes']) != search['issueCount']):
                raise ValueError('incomplete child search')
            matching = [_external(repository, n) for n in search['nodes']
                        if marker in n['body']]
            if len(matching) > 1:
                raise ValueError('duplicate child marker')
            return matching[0] if matching else None
        except (KeyError, TypeError, ValueError) as exc:
            raise SourceControlError('invalid_response',
                                     'Complete unique child search required') from exc

    def create_issue(self, repository: str, *, title: str, body: str) -> ExternalIssue:
        if (not isinstance(title, str) or not title.strip() or len(title) > 256
                or not isinstance(body, str) or not body.strip() or len(body) > 65536):
            raise ValueError('bounded Issue text required')
        result = self._request(_base(repository) + '/issues', 'POST',
                               {'title': title, 'body': body})
        number = result.get('number')
        if type(number) is not int or number < 1:
            raise SourceControlError('invalid_response', 'Created Issue identity missing')
        # Authoritative readback, including exact content; never trust only POST output.
        value = self._issue(repository, str(number))
        if value['title'] != title or value['body'] != body:
            raise SourceControlError('invalid_response', 'Created Issue content differs')
        return _external(repository, value)

    def child_issues(self, repository: str, parent: str) -> tuple[ExternalIssue, ...]:
        _base(repository)
        owner, name = repository.split('/')
        data = self._graphql('query($owner:String!,$name:String!,$number:Int!){'
            'repository(owner:$owner,name:$name){nameWithOwner issue(number:$number){number '
            'subIssues(first:100){pageInfo{hasNextPage}nodes{' + _FIELDS + '}}}}}',
            {'owner': owner, 'name': name, 'number': _number(parent)})
        try:
            repo = data['repository']
            issue = repo['issue']
            children = issue['subIssues']
            if (repo['nameWithOwner'].casefold() != repository.casefold()
                    or issue['number'] != int(parent)
                    or children['pageInfo']['hasNextPage'] is not False
                    or not isinstance(children['nodes'], list) or len(children['nodes']) > 100):
                raise ValueError('incomplete child list')
            result = tuple(_external(repository, node) for node in children['nodes'])
            if len({i.external_id for i in result}) != len(result):
                raise ValueError('duplicate child')
            return result
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise SourceControlError('invalid_response',
                                     'Complete native child list required') from exc

    def attach_child(self, repository: str, parent: str, child: str) -> None:
        if parent == child:
            raise ValueError('Issue cannot be its own child')
        first, second = self._issue(repository, parent), self._issue(repository, child)
        previous = second.get('parent')
        if previous is not None:
            if (previous['id'] != first['id'] or previous['number'] != int(parent)
                    or previous['repository']['nameWithOwner'].casefold() != repository.casefold()):
                raise SourceControlError('invalid_response', 'Child already has another parent')
            return  # Exact native parent is already authoritative, no mutation required.
        self._graphql('mutation($input:AddSubIssueInput!){addSubIssue(input:$input){'
            'issue{id} subIssue{id}}}', {'input': {'issueId': first['id'],
                'subIssueId': second['id'], 'replaceParent': False}})
        if child not in {i.external_id for i in self.child_issues(repository, parent)}:
            raise SourceControlError('invalid_response', 'Native child link not confirmed')
