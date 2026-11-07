"""Select local persistence without migrating or replacing existing user data."""
from __future__ import annotations

import os
from pathlib import Path

from sf_factory.factory import Factory
from sf_factory.state_store import StateConflict


def data_directory(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return explicit
    return Path(os.environ.get('SF_DATA_DIR', '.sf-factory'))


def open_factory(root: Path, *, backend: str | None = None) -> Factory:
    selected = backend if backend is not None else os.environ.get('SF_STATE_BACKEND', 'auto')
    if selected not in {'auto', 'file', 'sqlite'}:
        raise ValueError('SF_STATE_BACKEND must be auto, file or sqlite')
    root = root.expanduser().resolve()
    # Reserve backend initialization across Web workers. Existing callers that
    # construct a Factory/IssueStore directly must still use separate backend roots.
    if os.name == 'posix':
        from sf_factory.file_state import lock_directory

        root.mkdir(mode=0o700, exist_ok=True)
        with lock_directory(root):
            return _open_selected(root, selected)
    return _open_selected(root, selected)


def _open_selected(root: Path, selected: str) -> Factory:
    has_sqlite = os.path.lexists(root / 'factory.sqlite3')
    has_file = any(os.path.lexists(root / name) for name in ('issues-v2', 'dashboard-v2'))
    if has_sqlite and has_file:
        raise StateConflict('Mixed File/SQLite state root; restore or select a separate root')
    if selected == 'auto':
        selected = ('file' if has_file else
                    'sqlite' if has_sqlite or os.name != 'posix' else 'file')
    if selected == 'sqlite':
        if has_file:
            raise StateConflict('File data exists; automatic migration to SQLite is not supported')
        return Factory(root)
    if has_sqlite:
        raise StateConflict('SQLite data exists; automatic migration to File is not supported')
    from sf_factory.file_dashboard import FileDashboardFactory

    return FileDashboardFactory(root)
