"""GitHub REST SourceControl adapter; credentials and payloads stay here."""
from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from sf_factory.change_proposal import _change_path
from sf_factory.github_auth import environment_token
from sf_factory.repository_contracts import RepositoryCapabilities
from sf_factory.source_control import (
    CommitChange,
    PreparedCommit,
    PullRequestReference,
    RepositoryInfo,
    SourceControlError,
)

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
        token = environment_token()
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

    def prepare_commit(self, repository: str, *, parent_revision: str,
                       changes: tuple[CommitChange, ...], message: str) -> PreparedCommit:
        """Create unreferenced Git objects only. Never move a branch or open a PR.

        A failed POST can leave an object behind. Caller must journal intent before
        use; no automatic retry or claim that the whole delivery is transactional.
        """
        base = _base(repository)
        if (not isinstance(parent_revision, str)
                or not re.fullmatch(r'[a-f0-9]{40}', parent_revision)
                or not isinstance(message, str) or not message.strip() or len(message) > 4096
                or not isinstance(changes, tuple) or not 1 <= len(changes) <= 32):
            raise ValueError('bounded exact commit subject required')
        paths: set[str] = set()
        total = 0
        for change in changes:
            if not isinstance(change, CommitChange):
                raise ValueError('typed commit change required')
            _change_path(change.path)
            if (change.path in paths or type(change.executable) is not bool
                    or not isinstance(change.after, bytes) or len(change.after) > 1048576
                    or (change.before is not None and (not isinstance(change.before, bytes)
                        or len(change.before) > 1048576)) or change.before == change.after):
                raise ValueError('bounded unique changed bytes required')
            paths.add(change.path)
            total += len(change.after) + len(change.before or b'')
        if total > 16 * 1024 * 1024:
            raise ValueError('commit byte budget exceeded')
        for path in paths:
            if any(parent.as_posix() in paths for parent in PurePosixPath(path).parents):
                raise ValueError('file/directory collision')

        def sha(value: object) -> str:
            if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{40}', value):
                raise SourceControlError('invalid_response', 'Invalid Git object identity')
            return value

        def blob(data: bytes) -> str:
            return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()

        parent = self._request(base + '/git/commits/' + parent_revision)
        if parent.get('sha') != parent_revision or not isinstance(parent.get('tree'), dict):
            raise SourceControlError('invalid_response', 'Parent commit identity mismatch')
        tree_id = sha(parent['tree'].get('sha'))
        tree = self._request(base + '/git/trees/' + tree_id + '?recursive=1')
        entries = tree.get('tree')
        if (tree.get('sha') != tree_id or tree.get('truncated') is not False
                or not isinstance(entries, list) or len(entries) > 10000):
            raise SourceControlError('invalid_response', 'Complete parent tree required')
        inventory: dict[str, dict] = {}
        for entry in entries:
            if (not isinstance(entry, dict) or not isinstance(entry.get('path'), str)
                    or entry['path'] in inventory):
                raise SourceControlError('invalid_response', 'Invalid parent tree inventory')
            inventory[entry['path']] = entry
        # Validate every precondition before the first POST.
        for change in changes:
            existing = inventory.get(change.path)
            if change.before is None:
                if existing is not None or change.executable:
                    raise SourceControlError('invalid_response', 'New file base/mode mismatch')
                for path, entry in inventory.items():
                    if (path.startswith(change.path + '/') or
                        (change.path.startswith(path + '/') and entry.get('type') != 'tree')):
                        raise SourceControlError('invalid_response', 'Parent path collision')
            elif (existing is None or existing.get('type') != 'blob'
                  or existing.get('sha') != blob(change.before)
                  or existing.get('mode') != ('100755' if change.executable else '100644')):
                raise SourceControlError('invalid_response', 'Changed file base/mode mismatch')
        updates = []
        for change in changes:
            uploaded = self._request(base + '/git/blobs', 'POST', {
                'content': base64.b64encode(change.after).decode(), 'encoding': 'base64'})
            blob_id = sha(uploaded.get('sha'))
            if blob_id != blob(change.after):
                raise SourceControlError('invalid_response', 'Uploaded byte identity mismatch')
            updates.append({'path': change.path,
                            'mode': '100755' if change.executable else '100644',
                            'type': 'blob', 'sha': blob_id})
        created_tree = self._request(base + '/git/trees', 'POST', {
            'base_tree': tree_id, 'tree': updates})
        candidate_tree = sha(created_tree.get('sha'))
        commit = self._request(base + '/git/commits', 'POST', {
            'message': message, 'tree': candidate_tree, 'parents': [parent_revision]})
        commit_id = sha(commit.get('sha'))
        parents = commit.get('parents')
        if (not isinstance(commit.get('tree'), dict)
                or commit['tree'].get('sha') != candidate_tree
                or not isinstance(parents, list) or len(parents) != 1
                or not isinstance(parents[0], dict) or parents[0].get('sha') != parent_revision):
            raise SourceControlError('invalid_response', 'Prepared commit subject mismatch')
        return PreparedCommit(commit_id, candidate_tree, parent_revision)
