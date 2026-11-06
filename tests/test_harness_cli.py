"""Exercise the real CLI discovery route without creating Factory state."""
import json
import sys

import pytest

from sf_factory.cli import main


def invoke(monkeypatch, root, *extra):
    monkeypatch.setattr(sys, 'argv', ['sf', 'harness', 'discover', str(root), *extra])
    return main()


def test_discovers_relative_root_without_state_or_content(tmp_path, monkeypatch, capsys):
    (tmp_path / '.git').mkdir()
    (tmp_path / 'AGENTS.md').write_text('do not send this content')
    monkeypatch.chdir(tmp_path.parent)
    assert invoke(monkeypatch, tmp_path.name) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['complete'] is True
    assert result['schema_version'] == 1
    assert result['candidates'][0]['path'] == 'AGENTS.md'
    assert 'do not send this content' not in repr(result)
    assert not (tmp_path / '.sf-factory').exists()


def test_incomplete_inventory_is_json_and_nonzero(tmp_path, monkeypatch, capsys):
    (tmp_path / '.git').mkdir()
    (tmp_path / 'AGENTS.md').write_text('large instructions')
    assert invoke(monkeypatch, tmp_path, '--max-file-bytes', '1') == 1
    result = json.loads(capsys.readouterr().out)
    assert result['complete'] is False
    assert result['issues'][0]['reason'] == 'file_size_limit'


@pytest.mark.parametrize('extra', [[], ['--max-entries', '0']])
def test_invalid_root_or_limits_is_error_without_partial_json(tmp_path, monkeypatch, capsys, extra):
    assert invoke(monkeypatch, tmp_path, *extra) == 2
    output = capsys.readouterr()
    assert output.out == ''
    assert 'Error:' in output.err
    assert not (tmp_path / '.sf-factory').exists()


def test_cli_rejects_symlink_root(tmp_path, monkeypatch, capsys):
    (tmp_path / '.git').mkdir()
    (tmp_path / 'alias').symlink_to(tmp_path, target_is_directory=True)
    assert invoke(monkeypatch, tmp_path / 'alias') == 2
    assert capsys.readouterr().out == ''
