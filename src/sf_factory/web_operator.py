"""Local operator capability and allowlisted profiles; never an HTTP path picker."""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time
from collections.abc import Callable
from pathlib import Path
from threading import Lock
from urllib.parse import urlsplit

from fastapi import HTTPException, Request, Response

from sf_factory.file_document import read_document, write_document
from sf_factory.file_state import lock_directory
from sf_factory.issue_development_cli import load_config
from sf_factory.state_store import StateConflict, StatePermissionDenied

COOKIE = 'sf_operator'


class OperatorProfiles:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.directory = self.root / 'web-operator-v1'
        self.root.mkdir(parents=True, mode=0o700, exist_ok=True)
        try:
            self.directory.mkdir(mode=0o700)
            created = True
        except FileExistsError:
            created = False
        with lock_directory(self.directory) as fd:
            if created:
                write_document(fd, {'version': 1, 'profiles': {}})
            self._read(fd)

    @staticmethod
    def _read(fd):
        state = read_document(fd)
        if (set(state) != {'version', 'profiles'} or type(state['version']) is not int
                or state['version'] != 1
                or not isinstance(state['profiles'], dict) or len(state['profiles']) > 32):
            raise StateConflict('invalid operator registry; do not reset')
        for key, p in state['profiles'].items():
            if (not re.fullmatch('[a-f0-9]{32}', key) or set(p) !=
                    {'id', 'name', 'path', 'fingerprint', 'revoked'} or p['id'] != key
                    or type(p['revoked']) is not bool
                    or not re.fullmatch('[a-f0-9]{64}', p['fingerprint'])):
                raise StateConflict('invalid registered profile')
        return state

    def register(self, path: Path, name: str) -> dict:
        if not isinstance(name, str) or not name.strip() or len(name) > 120:
            raise ValueError('bounded profile name required')
        if not path.is_absolute() or path != path.resolve(strict=True):
            raise ValueError('canonical operator config path required')
        config = load_config(path)
        if config.data_root != self.root:
            raise StatePermissionDenied('profile data_root must match the dashboard data root')
        key = hashlib.sha256(str(path).encode()).hexdigest()[:32]
        with lock_directory(self.directory) as fd:
            state = self._read(fd)
            if key not in state['profiles'] and len(state['profiles']) >= 32:
                raise StateConflict('operator profile limit reached')
            value = {'id': key, 'name': name.strip(), 'path': str(path),
                     'fingerprint': config.fingerprint, 'revoked': False}
            state['profiles'][key] = value
            write_document(fd, state)
        return {k: value[k] for k in ('id', 'name', 'fingerprint', 'revoked')}

    def revoke(self, key: str) -> None:
        with lock_directory(self.directory) as fd:
            state = self._read(fd)
            if key not in state['profiles']:
                raise StateConflict('unknown profile')
            state['profiles'][key]['revoked'] = True
            write_document(fd, state)

    def get(self, key: str, expected: str | None = None):
        with lock_directory(self.directory) as fd:
            profile = self._read(fd)['profiles'].get(key)
        if profile is None or profile['revoked']:
            raise StatePermissionDenied('profile is unknown or revoked')
        config = load_config(Path(profile['path']))
        if (config.fingerprint != profile['fingerprint'] or config.data_root != self.root
                or (expected is not None and expected != config.fingerprint)):
            raise StatePermissionDenied(
                'registered configuration changed; register it locally again')
        return profile, config

    def list(self) -> list[dict]:
        with lock_directory(self.directory) as fd:
            profiles = list(self._read(fd)['profiles'].values())
        result = []
        for p in profiles:
            row = {k: p[k] for k in ('id', 'name', 'fingerprint', 'revoked')}
            try:
                _, config = self.get(p['id'])
                row.update(available=True, repository=config.repository, issue=config.issue,
                    provider=config.provider, allowed_paths=list(config.allowed_paths),
                    checks=[c.id for c in config.checks],
                    project=config.project_harness.project if config.project_harness else None)
            except (OSError, ValueError, StateConflict):
                row.update(available=False)
            result.append(row)
        return result


class WebOperator:
    """Per-server root capability exchanged for short-lived HttpOnly cookies.

    No token in HTTP URL, logs, static assets or persistent browser storage.
    A server restart revokes all browser sessions. Not remote/multi-user auth.
    """
    def __init__(self, origin: str, *, clock: Callable[[], float] = time.monotonic):
        parts = urlsplit(origin)
        if (parts.scheme != 'http' or parts.hostname not in {'127.0.0.1', 'localhost', '::1'}
                or parts.username or parts.password or parts.path or parts.query or parts.fragment):
            raise ValueError('exact loopback HTTP origin required')
        self.origin, self.clock = origin, clock
        self.token = secrets.token_urlsafe(32)
        self._sessions: dict[str, float] = {}
        self._failures: list[float] = []
        self._lock = Lock()

    def browser(self, request: Request) -> None:
        if str(request.base_url).rstrip('/') != self.origin:
            raise HTTPException(403, 'Operator host rejected')
        origin = request.headers.get('origin')
        same_origin_read = (request.method == 'GET' and origin is None
                            and request.headers.get('sec-fetch-site') == 'same-origin')
        if ((origin != self.origin and not same_origin_read)
                or request.headers.get('sec-fetch-site') not in {None, 'same-origin'}
                or request.headers.get('x-sf-operator') != '1'):
            raise HTTPException(403, 'Same-origin operator request required')

    def exchange(self, request: Request, response: Response) -> None:
        self.browser(request)
        header = request.headers.get('authorization', '')
        with self._lock:
            now = self.clock()
            self._failures = [n for n in self._failures if n > now - 60]
            if len(self._failures) >= 10:
                raise HTTPException(429, 'Operator authentication rate limited')
            if len(header) > 512 or not hmac.compare_digest(
                    header.encode(), ('Bearer ' + self.token).encode()):
                self._failures.append(now)
                raise HTTPException(403, 'Operator authentication required')
            self._sessions = {k: v for k, v in self._sessions.items() if v > now}
            # Reopening the terminal link rotates this browser's capability.
            self._sessions.pop(request.cookies.get(COOKIE, ''), None)
            if len(self._sessions) >= 16:
                raise HTTPException(429, 'Operator session limit reached')
            session = secrets.token_urlsafe(32)
            self._sessions[session] = now + 28800
        response.set_cookie(COOKIE, session, max_age=28800, httponly=True,
                            samesite='strict', path='/api/operator')
        response.headers['Cache-Control'] = 'no-store'

    def require(self, request: Request) -> None:
        self.browser(request)
        value = request.cookies.get(COOKIE, '')
        with self._lock:
            expires = self._sessions.get(value, 0)
        if not value or expires <= self.clock():
            raise HTTPException(401, 'Open the operator link from the local terminal')

    def logout(self, request: Request, response: Response) -> None:
        self.require(request)
        with self._lock:
            self._sessions.pop(request.cookies.get(COOKIE, ''), None)
        response.delete_cookie(COOKIE, path='/api/operator')
