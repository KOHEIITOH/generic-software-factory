"""The File CLI must work while every SQLite connection is forbidden."""
import json
import sqlite3
import sys

import pytest

from sf_factory.cli import main


def _invoke(monkeypatch, root, *args, backend='file'):
    monkeypatch.setattr(
        sys, 'argv', ['sf', 'state', '--backend', backend, '--root', str(root), *args],
    )
    return main()


def test_file_cli_never_connects_to_sqlite(tmp_path, monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        raise AssertionError('File mode must not connect to SQLite')
    monkeypatch.setattr(sqlite3, 'connect', forbidden)
    monkeypatch.chdir(tmp_path)
    root = tmp_path / 'file-state'
    assert _invoke(monkeypatch, root, 'create', 'local task') == 0
    task = json.loads(capsys.readouterr().out)['task_id']
    assert _invoke(monkeypatch, root, 'show', task) == 0
    assert json.loads(capsys.readouterr().out)['task']['prompt'] == 'local task'
    args = ('import', '--provider', 'github', '--instance', 'owner/repo',
            '--external-id', '42', '--prompt', 'imported task')
    assert _invoke(monkeypatch, root, *args) == 0
    imported = json.loads(capsys.readouterr().out)['task_id']
    assert _invoke(monkeypatch, root, *args) == 0
    assert json.loads(capsys.readouterr().out)['task_id'] == imported
    assert len(list(root.rglob('*.json'))) == 2
    assert not list(tmp_path.rglob('*.sqlite3'))
    assert not (tmp_path / '.sf-factory').exists()


def test_sqlite_cli_uses_same_task_contract(tmp_path, monkeypatch, capsys):
    assert _invoke(monkeypatch, tmp_path, 'create', 'sql task', backend='sqlite') == 0
    task = json.loads(capsys.readouterr().out)['task_id']
    assert _invoke(monkeypatch, tmp_path, 'show', task, backend='sqlite') == 0
    assert json.loads(capsys.readouterr().out)['task']['prompt'] == 'sql task'


def test_file_cli_missing_task_returns_error_without_traceback(tmp_path, monkeypatch, capsys):
    assert _invoke(monkeypatch, tmp_path, 'show', 'missing') == 2
    captured = capsys.readouterr()
    assert captured.out == ''
    assert 'task not found' in captured.err


def test_file_cli_refuses_workflow_commands(tmp_path, monkeypatch):
    with pytest.raises(SystemExit) as error:
        _invoke(monkeypatch, tmp_path, 'run', 'task-id')
    assert error.value.code == 2


def test_cli_refuses_silent_backend_switch_in_same_root(tmp_path, monkeypatch, capsys):
    assert _invoke(monkeypatch, tmp_path, 'create', 'file task') == 0
    capsys.readouterr()
    assert _invoke(monkeypatch, tmp_path, 'create', 'sql task', backend='sqlite') == 2
    assert 'separate root' in capsys.readouterr().err
    assert not (tmp_path / 'factory.sqlite3').exists()
