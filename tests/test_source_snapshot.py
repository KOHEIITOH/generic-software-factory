"""Reject metadata, path traversal and sensitive snapshot paths."""
import pytest

from sf_factory.source_snapshot import _path


@pytest.mark.parametrize('path', [
    '../outside', '/etc/passwd', 'a/../b', 'a//b', './a', 'a\\b', '.git/config',
    'nested/.GIT/config', '.sf-factory/database', '.env', 'docs/credentials.txt',
    '/'.join(['a'] * 17),
])
def test_unsafe_source_paths_are_rejected(path):
    with pytest.raises(ValueError):
        _path(path)
