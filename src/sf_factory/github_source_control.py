"""GitHub REST SourceControl adapter; credentials and payloads stay here."""
from __future__ import annotations

import base64
import json
import os
import re
from pathlib import PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from sf_factory.repository_contracts import RepositoryCapabilities
from sf_factory.source_control import PullRequestReference, RepositoryInfo, SourceControlError

_REPOSITORY = re.compile(r'^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$')


def _base(repository: str) -> str:
    if not _REPOSITORY.fullmatch(repository) or '..' in repository:
        raise ValueError('Invalid repository')
    return '/repos/' + '/'.join(quote(part, safe='') for part in repository.split('/'))


def _branch(branch: str) -> str:
    if (not isinstance(branch, str) or not branch or len(branch) > 255
            or any(c.isspace() or ord(c) < 32 for c in branch)
            or any(c in branch for c in ('..', '@{', '~', '^', ':', '?', '*', '[', '\\'))
            or branch.startswith(('/', '-')) or branch.endswith(('/', '.'))
            or any(not p or p.startswith('.') or p.endswith('.lock') for p in branch.split('/'))):
        raise ValueError('Invalid branch')
    return quote(branch, safe='')


class GitHubSourceControl:
    def _request(self, path: str, method: str = 'GET', payload: dict | None = None) -> dict:
        token = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
        if not token:
            raise SourceControlError('not_configured', 'GitHub credentials are not configured')
        headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
                   'User-Agent': 'generic-software-factory', 'X-GitHub-Api-Version': '2022-11-28'}
        data = json.dumps(payload).encode() if payload is not None else None
        if data is not None:
            headers['Content-Type'] = 'application/json'
        try:
            with urlopen(Request('https://api.github.com' + path, data=data,
                                 headers=headers, method=method), timeout=15) as response:
                raw = response.read(1048577)
                if len(raw) > 1048576:
                    raise SourceControlError('invalid_response', 'GitHub response exceeds limit')
                result = json.loads(raw)
        except HTTPError as exc:
            if exc.code in (401, 403, 404):
                raise SourceControlError(
                    'access_denied', 'GitHub access denied or unavailable',
                ) from exc
            raise SourceControlError('unavailable', 'GitHub request failed') from exc
        except (URLError, TimeoutError) as exc:
            raise SourceControlError('unavailable', 'GitHub unavailable') from exc
        except (ValueError, RecursionError) as exc:
            raise SourceControlError('invalid_response', 'Invalid GitHub response') from exc
        if not isinstance(result, dict):
            raise SourceControlError('invalid_response', 'Unexpected GitHub response')
        return result

    def describe_repository(self, repository: str) -> RepositoryInfo:
        data = self._request(_base(repository))
        name = data.get('full_name')
        if not isinstance(name, str) or name.casefold() != repository.casefold():
            raise SourceControlError('invalid_response', 'Repository identity mismatch')
        default = data.get('default_branch')
        if not isinstance(default, str) or not default:
            raise SourceControlError('invalid_response', 'Default branch unavailable')
        _branch(default)
        permissions = data.get('permissions')
        writable = isinstance(permissions, dict) and permissions.get('push') is True
        return RepositoryInfo(name, default, RepositoryCapabilities(
            read=True, write=writable, pull_request=writable,
        ))

    def branch_revision(self, repository: str, branch: str) -> str:
        data = self._request(_base(repository) + '/git/ref/heads/' + _branch(branch))
        obj = data.get('object')
        sha = obj.get('sha') if isinstance(obj, dict) else None
        if not isinstance(sha, str) or not re.fullmatch(r'[a-f0-9]{40}', sha):
            raise SourceControlError('invalid_response', 'Invalid base branch SHA')
        return sha

    def create_branch(self, repository: str, branch: str, revision: str) -> None:
        _branch(branch)
        if not re.fullmatch(r'[a-f0-9]{40}', revision):
            raise ValueError('Invalid base revision')
        self._request(_base(repository) + '/git/refs', 'POST', {
            'ref': 'refs/heads/' + branch, 'sha': revision,
        })

    def write_file(self, repository: str, *, branch: str, path: str,
                   content: bytes, message: str) -> None:
        _branch(branch)
        relative = PurePosixPath(path)
        if (not relative.parts or relative.is_absolute() or relative.as_posix() != path
                or '..' in relative.parts or '\\' in path or '\x00' in path
                or len(content) > 65536 or not message.strip()):
            raise ValueError('Invalid file write')
        encoded_path = '/'.join(quote(part, safe='') for part in relative.parts)
        self._request(_base(repository) + '/contents/' + encoded_path, 'PUT', {
            'message': message, 'content': base64.b64encode(content).decode(), 'branch': branch,
        })

    def create_draft_pull_request(self, repository: str, *, title: str, head: str,
                                  base: str, body: str) -> PullRequestReference:
        _branch(head)
        _branch(base)
        data = self._request(_base(repository) + '/pulls', 'POST', {
            'title': title, 'head': head, 'base': base, 'draft': True, 'body': body,
        })
        number, url = data.get('number'), data.get('html_url')
        if (type(number) is not int or number < 1 or not isinstance(url, str)
                or url != f'https://github.com/{repository}/pull/{number}'):
            raise SourceControlError('invalid_response', 'Invalid GitHub pull request response')
        return PullRequestReference(str(number), url)
