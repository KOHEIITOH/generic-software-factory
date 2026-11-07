"""Standalone task creation and legacy state preview commands are removed."""
import pytest

from sf_factory.cli import build_parser


@pytest.mark.parametrize('args', [['task', 'create', 'standalone'],
    ['task', 'run', 'old-id', '--runtime', 'codex'],
    ['state', '--root', '/unused', 'create', 'standalone']])
def test_removed_task_management_commands_are_rejected(args, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as error:
        build_parser().parse_args(args)
    assert error.value.code == 2
    assert list(tmp_path.iterdir()) == []
