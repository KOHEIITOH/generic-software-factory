"""GitHub REST SourceControl adapter; credentials and payloads stay here."""
from __future__ import annotations

import base64
import hashlib
import json
import re
import time
from collections.abc import Callable
from pathlib import PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
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
    def __init__(self, *, request_guard: Callable[[str, str], None] | None = None):
        self.request_guard = request_guard

    def _request(self, path: str, method: str = 'GET', payload: dict | None = None,
                 *, collection: bool = False, optional: bool = False,
                 response_limit: int = 1048576) -> dict:
        from sf_factory.operation_control import checkpoint
        checkpoint()
        guard = getattr(self, 'request_guard', None)
        if guard is not None:
            guard(method, path)
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
                raw = response.read(response_limit + 1)
                if len(raw) > response_limit:
                    raise SourceControlError('invalid_response', 'GitHub response exceeds limit')
                result = json.loads(raw)
                paginated = bool(response.headers.get('Link')) if collection else False
        except HTTPError as exc:
            if optional and method == 'GET' and exc.code == 404:
                return {'_sf_missing_ref': True}
            if exc.code in (401, 403, 404):
                raise SourceControlError(
                    'access_denied', 'GitHub access denied or unavailable',
                ) from exc
            raise SourceControlError('unavailable', 'GitHub request failed') from exc
        except (URLError, TimeoutError) as exc:
            raise SourceControlError('unavailable', 'GitHub unavailable') from exc
        except (ValueError, RecursionError) as exc:
            raise SourceControlError('invalid_response', 'Invalid GitHub response') from exc
        if collection:
            if not isinstance(result, list) or paginated or len(result) >= 100:
                raise SourceControlError('invalid_response', 'Complete bounded PR list required')
            return {'items': result}
        if not isinstance(result, dict):
            raise SourceControlError('invalid_response', 'Unexpected GitHub response')
        return result

    def _graphql(self, query: str, variables: dict) -> dict:
        result = self._request('/graphql', 'POST', {'query': query, 'variables': variables})
        if result.get('errors') or not isinstance(result.get('data'), dict):
            raise SourceControlError('invalid_response', 'GraphQL operation not confirmed')
        return result['data']

    def repository_choices(self, cursor: str | None = None):
        if cursor is not None and (not isinstance(cursor, str) or not 1 <= len(cursor) <= 512):
            raise ValueError('bounded repository cursor required')
        data = self._graphql("""query($cursor:String){viewer{repositories(first:50,after:$cursor,
          affiliations:[OWNER,COLLABORATOR,ORGANIZATION_MEMBER],
          orderBy:{field:UPDATED_AT,direction:DESC}){
          nodes{nameWithOwner viewerPermission isArchived isDisabled defaultBranchRef{name}}
          pageInfo{hasNextPage endCursor}}}}""", {'cursor': cursor})
        try:
            value = data['viewer']['repositories']
            if not isinstance(value['nodes'], list) or len(value['nodes']) > 50:
                raise ValueError('bounded repository page required')
            choices = []
            for item in value['nodes']:
                if item.get('isArchived') is True or item.get('isDisabled') is True:
                    continue
                name = item['nameWithOwner']
                _base(name)
                branch = item['defaultBranchRef']
                if branch is None:
                    continue
                _branch(branch['name'])
                choices.append(RepositoryInfo(name, branch['name'], RepositoryCapabilities(
                    True, item['viewerPermission'] in {'ADMIN', 'MAINTAIN', 'WRITE'}, True)))
            page = value['pageInfo']
            if type(page['hasNextPage']) is not bool:
                raise ValueError('pagination state required')
            next_cursor = page['endCursor'] if page['hasNextPage'] else None
            if next_cursor is not None and (not isinstance(next_cursor, str) or
                                            not 1 <= len(next_cursor) <= 512):
                raise ValueError('invalid next cursor')
            if page['hasNextPage'] and next_cursor is None:
                raise ValueError('missing next cursor')
            return choices, next_cursor
        except (KeyError, TypeError, AttributeError, ValueError) as exc:
            raise SourceControlError('invalid_response', 'Invalid repository catalog') from exc

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

    def verified_branch_revision(self, repository: str, branch: str) -> str | None:
        data = self._request(_base(repository) + '/git/ref/heads/' + _branch(branch), optional=True)
        if data == {'_sf_missing_ref': True}:
            return None
        obj = data.get('object')
        if (data.get('ref') != 'refs/heads/' + branch or not isinstance(obj, dict)
                or obj.get('type') != 'commit' or not isinstance(obj.get('sha'), str)
                or not re.fullmatch(r'[a-f0-9]{40}', obj['sha'])):
            raise SourceControlError('invalid_response', 'Exact branch commit required')
        return obj['sha']

    def ensure_branch(self, repository: str, branch: str, revision: str) -> None:
        """Create once if absent, or verify exact existing ref. Never force update."""
        _base(repository)
        _branch(branch)
        if not isinstance(revision, str) or not re.fullmatch(r'[a-f0-9]{40}', revision):
            raise ValueError('exact candidate revision required')
        existing = self.verified_branch_revision(repository, branch)
        if existing is None:
            self.create_branch(repository, branch, revision)
            existing = self.verified_branch_revision(repository, branch)
        if existing != revision:
            raise SourceControlError('invalid_response', 'Existing branch differs from candidate')

    def find_draft_pull_request(self, repository: str, *, head: str, base: str,
                                revision: str, marker: str) -> PullRequestReference | None:
        """Read-only reconciliation; closed/changed/ambiguous PRs block delivery."""
        prefix = _base(repository)
        _branch(head)
        _branch(base)
        if (not isinstance(revision, str) or not re.fullmatch(r'[a-f0-9]{40}', revision)
                or not isinstance(marker, str) or not marker.strip() or len(marker) > 512):
            raise ValueError('exact bounded PR reconciliation subject required')
        query = urlencode({'state': 'all', 'head': repository.split('/')[0] + ':' + head,
                           'per_page': 100})
        data = self._request(prefix + '/pulls?' + query, collection=True)
        items = data.get('items')
        if not isinstance(items, list) or len(items) > 1:
            raise SourceControlError('invalid_response', 'Ambiguous candidate pull requests')
        if not items:
            return None
        item = items[0]
        if not isinstance(item, dict):
            raise SourceControlError('invalid_response', 'Invalid pull request identity')
        for field, ref in (('head', head), ('base', base)):
            subject = item.get(field)
            repo = subject.get('repo') if isinstance(subject, dict) else None
            if (not isinstance(subject, dict) or subject.get('ref') != ref
                    or not isinstance(repo, dict) or not isinstance(repo.get('full_name'), str)
                    or repo['full_name'].casefold() != repository.casefold()):
                raise SourceControlError('invalid_response', 'PR repository/branch mismatch')
        number = item.get('number')
        if (type(number) is not int or number < 1
                or item.get('html_url') != f'https://github.com/{repository}/pull/{number}'
                or item['head'].get('sha') != revision or item.get('draft') is not True
                or item.get('state') != 'open' or item.get('merged_at') is not None
                or not isinstance(item.get('body'), str) or marker not in item['body']):
            raise SourceControlError('invalid_response', 'Existing PR differs from delivery intent')
        return PullRequestReference(str(number), item['html_url'])

    def compare_update_branch(self, repository: str, branch: str, *, expected: str,
                              revision: str) -> None:
        """Atomic beforeOid/afterOid CAS; a pre-read plus REST PATCH is insufficient."""
        prefix = _base(repository)
        _branch(branch)
        if any(not isinstance(v, str) or not re.fullmatch(r'[a-f0-9]{40}', v)
               for v in (expected, revision)) or expected == revision:
            raise ValueError('distinct exact ref revisions required')
        info = self._request(prefix)
        node = info.get('node_id')
        if (not isinstance(node, str) or not node
                or not isinstance(info.get('full_name'), str)
                or info['full_name'].casefold() != repository.casefold()):
            raise SourceControlError('invalid_response', 'Repository node identity missing')
        data = self._graphql('''mutation($input:UpdateRefsInput!){
            updateRefs(input:$input){clientMutationId}}''', {'input': {
                'repositoryId': node, 'refUpdates': [{'name': 'refs/heads/' + branch,
                    'beforeOid': expected, 'afterOid': revision, 'force': False}]}})
        if not isinstance(data.get('updateRefs'), dict):
            raise SourceControlError('invalid_response', 'Ref update outcome unknown')
        if self.verified_branch_revision(repository, branch) != revision:
            raise SourceControlError('invalid_response', 'Updated ref outcome unknown')

    def read_revision(self, repository: str, revision: str):
        from sf_factory.collaboration_contracts import RevisionFile, RevisionSource
        if not isinstance(revision, str) or not re.fullmatch(r'[a-f0-9]{40}', revision):
            raise ValueError('exact remote revision required')
        prefix = _base(repository)
        deadline = time.monotonic() + 120
        commit = self._request(prefix + '/git/commits/' + revision)
        if commit.get('sha') != revision or not isinstance(commit.get('tree'), dict):
            raise SourceControlError('invalid_response', 'Remote commit identity mismatch')
        tree_id = commit['tree'].get('sha')
        if not isinstance(tree_id, str) or not re.fullmatch(r'[a-f0-9]{40}', tree_id):
            raise SourceControlError('invalid_response', 'Invalid remote tree identity')
        tree = self._request(prefix + '/git/trees/' + tree_id + '?recursive=1')
        entries = tree.get('tree')
        if (tree.get('sha') != tree_id or tree.get('truncated') is not False
                or not isinstance(entries, list) or len(entries) > 2000):
            raise SourceControlError('invalid_response', 'Complete bounded remote tree required')
        blobs = []
        paths = set()
        from sf_factory.source_snapshot import _path
        # Validate all paths/types/budgets BEFORE downloading any contents.
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get('path'), str):
                raise SourceControlError('invalid_response', 'Invalid tree entry')
            path = entry['path']
            _path(path)
            if path in paths:
                raise SourceControlError('invalid_response', 'Duplicate tree entry')
            paths.add(path)
            if entry.get('type') == 'tree' and entry.get('mode') == '040000':
                continue
            if (entry.get('type') != 'blob' or entry.get('mode') not in {'100644', '100755'}
                    or type(entry.get('size')) is not int or not 0 <= entry['size'] <= 1048576
                    or not isinstance(entry.get('sha'), str)
                    or not re.fullmatch(r'[a-f0-9]{40}', entry['sha'])):
                raise SourceControlError('invalid_response', 'Unsupported remote source object')
            blobs.append(entry)
        if not 1 <= len(blobs) <= 1000 or sum(b['size'] for b in blobs) > 8 * 1024 * 1024:
            raise SourceControlError('invalid_response', 'Remote source budget exceeded')
        files = []
        for entry in blobs:
            if time.monotonic() >= deadline:
                raise SourceControlError('unavailable', 'Remote source read deadline exceeded')
            blob = self._request(prefix + '/git/blobs/' + entry['sha'], response_limit=2097152)
            try:
                if blob.get('encoding') != 'base64' or not isinstance(blob.get('content'), str):
                    raise ValueError('blob encoding')
                content = base64.b64decode(''.join(blob['content'].split()), validate=True)
            except (ValueError, TypeError) as exc:
                raise SourceControlError('invalid_response', 'Invalid remote blob') from exc
            digest = hashlib.sha1(
                b'blob ' + str(len(content)).encode() + b'\0' + content).hexdigest()
            if (blob.get('sha') != entry['sha'] or digest != entry['sha']
                    or len(content) != entry['size']):
                raise SourceControlError('invalid_response', 'Remote blob content mismatch')
            files.append(RevisionFile(entry['path'], entry['mode'], content))
        result = RevisionSource(repository, revision, tuple(files))
        result.validate()
        return result

    def authenticated_actor(self) -> str:
        value = self._request('/user')
        login = value.get('login') if isinstance(value, dict) else None
        if not isinstance(login, str) or not re.fullmatch(r'[A-Za-z0-9_\[\]-]{1,128}', login):
            raise SourceControlError('invalid_response', 'authenticated actor required')
        return login

    def pull_request_snapshot(self, repository: str, external_id: str):
        from sf_factory.collaboration_contracts import (
            PullRequestSnapshot,
            ReviewDecision,
            ReviewFeedback,
        )
        _base(repository)
        if not isinstance(external_id, str) or not re.fullmatch(r'[1-9][0-9]*', external_id):
            raise ValueError('exact PR number required')
        owner, name = repository.split('/')
        data = self._graphql('''query($owner:String!,$name:String!,$number:Int!){
          repository(owner:$owner,name:$name){nameWithOwner pullRequest(number:$number){
            number url body state isDraft merged headRefName headRefOid baseRefName baseRefOid
            headRepository{nameWithOwner}
            reviews(last:100){pageInfo{hasPreviousPage}nodes{
              id author{login} body state commit{oid}}}
            reviewThreads(first:100){pageInfo{hasNextPage}nodes{id isResolved isOutdated path
              comments(last:20){pageInfo{hasPreviousPage}nodes{id author{login}body commit{oid}}}}
          }}}''', {'owner': owner, 'name': name, 'number': int(external_id)})
        try:
            repo = data['repository']
            pr = repo['pullRequest']
            if (repo['nameWithOwner'].casefold() != repository.casefold()
                    or pr['headRepository']['nameWithOwner'].casefold() != repository.casefold()
                    or type(pr['number']) is not int or str(pr['number']) != external_id
                    or pr['url'] != f'https://github.com/{repository}/pull/{external_id}'
                    or type(pr['isDraft']) is not bool or type(pr['merged']) is not bool
                    or pr['state'] not in {'OPEN', 'CLOSED', 'MERGED'}
                    or pr['merged'] != (pr['state'] == 'MERGED')):
                raise ValueError('PR identity/state')
            for key in ('headRefOid', 'baseRefOid'):
                if not isinstance(pr[key], str) or not re.fullmatch(r'[a-f0-9]{40}', pr[key]):
                    raise ValueError('PR revision')
            for key in ('headRefName', 'baseRefName'):
                _branch(pr[key])
            def connection(value, flag):
                if (value['pageInfo'][flag] is not False or not isinstance(value['nodes'], list)
                        or len(value['nodes']) > 100):
                    raise ValueError('incomplete PR discussion')
                return value['nodes']
            def text(value, maximum):
                if not isinstance(value, str) or len(value) > maximum:
                    raise ValueError('unbounded PR text')
                return value
            feedback = []
            latest = {}
            for review in connection(pr['reviews'], 'hasPreviousPage'):
                author = text(review['author']['login'], 128)
                status = review['state']
                if status not in {'APPROVED', 'CHANGES_REQUESTED', 'COMMENTED',
                                  'DISMISSED', 'PENDING'}:
                    raise ValueError('unknown review state')
                revision = text(review['commit']['oid'], 40)
                if not re.fullmatch(r'[a-f0-9]{40}', revision):
                    raise ValueError('review revision')
                if status != 'PENDING':
                    latest[author] = review
            for author, review in latest.items():
                body = text(review['body'], 16384)
                if review['state'] in {'CHANGES_REQUESTED', 'COMMENTED'} and body.strip():
                    feedback.append(ReviewFeedback(text(review['id'], 256), author, body, None,
                                                   review['state'].lower(),
                                                   review['commit']['oid']))
            for thread in connection(pr['reviewThreads'], 'hasNextPage'):
                if type(thread['isResolved']) is not bool or type(thread['isOutdated']) is not bool:
                    raise ValueError('thread flags')
                comments = connection(thread['comments'], 'hasPreviousPage')
                if thread['isResolved']:
                    continue
                path = text(thread['path'], 1024)
                from sf_factory.source_snapshot import _path
                _path(path)
                for comment in comments:
                    revision = comment['commit']['oid']
                    if not isinstance(revision, str) or not re.fullmatch(r'[a-f0-9]{40}', revision):
                        raise ValueError('comment revision')
                    feedback.append(ReviewFeedback(text(comment['id'], 256),
                        text(comment['author']['login'], 128), text(comment['body'], 16384), path,
                        'outdated' if thread['isOutdated'] else 'unresolved', revision))
            if len(feedback) > 100 or sum(len(f.body) for f in feedback) > 131072:
                raise ValueError('feedback budget exceeded')
            approved = any(r['state'] == 'APPROVED' and r['commit']['oid'] == pr['headRefOid']
                           for r in latest.values())
            return PullRequestSnapshot(PullRequestReference(external_id, pr['url']), repository,
                pr['headRefName'], pr['headRefOid'], pr['baseRefName'], pr['baseRefOid'],
                text(pr['body'], 65536), pr['state'].lower(), pr['isDraft'],
                tuple(feedback), approved,
                tuple(ReviewDecision(text(r['id'], 256), a, r['state'].lower(),
                                     r['commit']['oid']) for a, r in latest.items()))
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise SourceControlError('invalid_response',
                                     'Incomplete or inconsistent PR snapshot') from exc
