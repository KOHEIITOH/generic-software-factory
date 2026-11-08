"""Durable bounded automation: reservations survive crashes and never reset on resume."""
from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sf_factory.file_document import read_document, write_document
from sf_factory.file_state import lock_directory
from sf_factory.state_store import StateConflict, StateCorrupt


class AutomationStopped(StateConflict):
    """Terminal condition with a recorded decision; not a request for approval."""


@dataclass(frozen=True)
class AutomationLimits:
    max_rounds: int = 3
    max_model_calls: int = 8
    max_tokens: int = 3000000
    max_api_calls: int = 2500
    max_writes: int = 128
    max_seconds: int = 604800
    max_children: int = 8

    def __post_init__(self) -> None:
        bounds = {'max_rounds': 5, 'max_model_calls': 64, 'max_tokens': 10000000,
                  'max_api_calls': 5000, 'max_writes': 256, 'max_seconds': 604800,
                  'max_children': 16}
        for name, maximum in bounds.items():
            if type(getattr(self, name)) is not int or not 1 <= getattr(self, name) <= maximum:
                raise ValueError('bounded integer automation limits required')


def fingerprint(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=True, allow_nan=False).encode()).hexdigest()


class AutomationSession:
    """Local POSIX adapter using existing locking/atomic durable documents.

    No inference or network here. The controller serializes an advance separately.
    Limits bound total consumption across invocations, not just one process loop.
    """
    def __init__(self, root: Path, *, subject: str, config_fingerprint: str,
                 limits: AutomationLimits = AutomationLimits(),
                 clock: Callable[[], datetime] | None = None):
        if (not isinstance(subject, str) or not subject.strip() or len(subject) > 2048
                or not re.fullmatch(r'[a-f0-9]{64}', config_fingerprint)):
            raise ValueError('exact bounded automation subject/config required')
        self.clock = clock or (lambda: datetime.now(UTC))
        self.id = fingerprint({'subject': subject, 'config': config_fingerprint})[:32]
        root = root.expanduser().resolve()
        root.mkdir(mode=0o700, exist_ok=True)
        parent = root / 'automation-v1'
        parent.mkdir(mode=0o700, exist_ok=True)
        self.directory = parent / self.id
        with lock_directory(parent):
            try:
                self.directory.mkdir(mode=0o700)
                created = True
            except FileExistsError:
                created = False
            with lock_directory(self.directory) as directory:
                if created:
                    now = self.clock()
                    if now.utcoffset() is None:
                        raise ValueError('aware automation clock required')
                    state = {'schema_version': 1, 'version': 1, 'subject': subject,
                        'config': config_fingerprint, 'limits': asdict(limits), 'status': 'ready',
                        'expires_at': (now + timedelta(seconds=limits.max_seconds)).isoformat(),
                        'counts': {'model': 0, 'tokens': 0, 'api': 0, 'write': 0}, 'rounds': {},
                        'actions': {}, 'candidates': {}, 'decisions': [], 'data': {}}
                    write_document(directory, state)
                    for path in (parent, root, root.parent):
                        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                        try:
                            os.fsync(fd)
                        finally:
                            os.close(fd)
                state = self._read(directory)
                if (state['subject'] != subject or state['config'] != config_fingerprint
                        or state['limits'] != asdict(limits)):
                    raise StateConflict('automation scope/limits changed')

    @staticmethod
    def _read(directory: int) -> dict:
        state = read_document(directory)
        try:
            if (set(state) != {'schema_version', 'version', 'subject', 'config', 'limits',
                    'status', 'expires_at', 'counts', 'rounds', 'actions', 'candidates',
                    'decisions', 'data'} or type(state['schema_version']) is not int
                    or state['schema_version'] != 1 or type(state['version']) is not int
                    or state['version'] < 1 or state['status'] not in
                    {'ready', 'waiting', 'stopped', 'completed'}):
                raise ValueError('invalid automation document')
            AutomationLimits(**state['limits'])
            if (set(state['counts']) != {'model', 'tokens', 'api', 'write'} or any(
                    type(n) is not int or n < 0 for n in state['counts'].values())
                    or datetime.fromisoformat(state['expires_at']).utcoffset() is None
                    or not all(isinstance(state[k], dict) for k in
                               ('rounds', 'actions', 'candidates', 'data'))
                    or not isinstance(state['decisions'], list)):
                raise ValueError('invalid automation counters/state')
            for unit, count in state['rounds'].items():
                if not isinstance(unit, str) or type(count) is not int or not 0 <= count <= 5:
                    raise ValueError('invalid unit rounds')
            for key, action in state['actions'].items():
                if (not isinstance(key, str) or not key or len(key) > 256
                        or set(action) != {'kind', 'unit', 'status', 'receipt', 'tokens'}
                        or action['kind'] not in {'round', 'model', 'write'}
                        or action['status'] not in {'pending', 'completed'}
                        or type(action['tokens']) is not int or action['tokens'] < 0
                        or (action['status'] == 'pending') != (action['receipt'] is None)
                        or (action['receipt'] is not None
                            and not isinstance(action['receipt'], dict))):
                    raise ValueError('invalid reserved action')
            return state
        except (ValueError, TypeError, KeyError) as exc:
            raise StateCorrupt('invalid automation state; do not reset or replay') from exc

    def snapshot(self) -> dict:
        with lock_directory(self.directory) as directory:
            return self._read(directory)

    def _change(self, change: Callable[[dict], str | None]) -> None:
        with lock_directory(self.directory) as directory:
            state = self._read(directory)
            error = change(state)
            state['version'] += 1
            write_document(directory, state)
        if error:
            raise AutomationStopped(error)

    def _decision(self, state: dict, code: str, facts: dict) -> None:
        if (not re.fullmatch(r'[a-z][a-z0-9_]{0,95}', code)
                or len(json.dumps(facts, allow_nan=False).encode()) > 8192
                or len(state['decisions']) >= 10000):
            raise ValueError('bounded structured decision required')
        state['decisions'].append({'at': self.clock().isoformat(), 'code': code, 'facts': facts})

    def _live(self, state: dict) -> str | None:
        if state['status'] in {'stopped', 'completed'}:
            return 'automation is terminal'
        if self.clock() >= datetime.fromisoformat(state['expires_at']):
            state['status'] = 'stopped'
            self._decision(state, 'deadline_exhausted', {})
            return 'automation deadline exhausted'
        return None

    def reserve(self, kind: str, key: str, *, unit: str = '', tokens: int = 0) -> None:
        if (kind not in {'round', 'model', 'write'} or not isinstance(key, str)
                or not key.strip() or len(key) > 256 or len(unit) > 256
                or type(tokens) is not int or tokens < 0 or (kind != 'model' and tokens)):
            raise ValueError('exact bounded action reservation required')
        def change(state):
            if error := self._live(state):
                return error
            if key in state['actions']:
                raise StateConflict('action already reserved; reconcile instead of replay')
            count = state['rounds'].get(unit, 0) if kind == 'round' else state['counts'][kind]
            maximum = state['limits']['max_rounds' if kind == 'round' else
                                      'max_model_calls' if kind == 'model' else 'max_writes']
            if (count >= maximum
                    or state['counts']['tokens'] + tokens > state['limits']['max_tokens']):
                state['status'] = 'stopped'
                self._decision(state, 'budget_exhausted', {'kind': kind, 'unit': unit})
                return 'automation budget exhausted'
            if kind == 'round':
                state['rounds'][unit] = count + 1
            else:
                state['counts'][kind] = count + 1
            state['counts']['tokens'] += tokens
            state['actions'][key] = {'kind': kind, 'unit': unit, 'status': 'pending',
                                     'receipt': None, 'tokens': tokens}
            self._decision(state, 'action_reserved', {'kind': kind, 'key': key, 'unit': unit})
            return None
        self._change(change)

    def api_call(self, method: str = '', path: str = '') -> None:
        def change(state):
            if error := self._live(state):
                return error
            if state['counts']['api'] >= state['limits']['max_api_calls']:
                state['status'] = 'stopped'
                self._decision(state, 'api_budget_exhausted', {})
                return 'automation API budget exhausted'
            state['counts']['api'] += 1
            return None
        self._change(change)

    def complete_action(self, key: str, receipt: dict) -> None:
        if not isinstance(receipt, dict) or len(json.dumps(receipt).encode()) > 1048576:
            raise ValueError('bounded action receipt required')
        def change(state):
            action = state['actions'].get(key)
            if action is None or action['status'] != 'pending':
                raise StateConflict('action is not pending')
            action.update(status='completed', receipt=receipt)
            self._decision(state, 'action_completed', {'key': key})
        self._change(change)

    def remember_candidate(self, unit: str, candidate: str) -> None:
        if not re.fullmatch(r'[a-f0-9]{64}', candidate):
            raise ValueError('exact candidate fingerprint required')
        def change(state):
            if error := self._live(state):
                return error
            seen = state['candidates'].setdefault(unit, [])
            if candidate in seen:
                state['status'] = 'stopped'
                self._decision(state, 'candidate_repeated', {'unit': unit, 'hash': candidate})
                return 'candidate repeated; no progress'
            if len(seen) >= state['limits']['max_rounds']:
                state['status'] = 'stopped'
                self._decision(state, 'candidate_budget_exhausted', {'unit': unit})
                return 'candidate budget exhausted'
            seen.append(candidate)
            return None
        self._change(change)

    def save(self, data: dict, *, expected_version: int, status: str = 'ready',
             decision: str = 'state_saved', facts: dict | None = None) -> None:
        if not isinstance(data, dict) or status not in {'ready', 'waiting', 'stopped', 'completed'}:
            raise ValueError('typed automation data/status required')
        def change(state):
            if state['version'] != expected_version:
                raise StateConflict('automation state changed')
            if state['status'] in {'stopped', 'completed'}:
                raise AutomationStopped('automation is terminal')
            state.update(data=data, status=status)
            self._decision(state, decision, facts or {})
        self._change(change)
