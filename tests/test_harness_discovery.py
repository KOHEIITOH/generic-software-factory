"""Discovery inventories untrusted files without applying or sending them."""
import hashlib
from dataclasses import asdict
from pathlib import Path

import pytest

from sf_factory.harness_discovery import DiscoveryLimits, discover_harness


def repository(tmp_path):
    (tmp_path / '.git').mkdir()
    return tmp_path


def write(root, path, body='rules'):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body)


def test_inventory_is_deterministic_scoped_and_read_only(tmp_path):
    root = repository(tmp_path)
    for path in ['AGENTS.md', 'app/AGENTS.md', 'app/package.json',
                 'harness/policies/safety.md', 'config/project.example.yaml',
                 '.github/workflows/test.yml', 'notes.md']:
        write(root, path)
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    first = discover_harness(root)
    assert first == discover_harness(root)
    found = {c.path: c for c in first.candidates}
    assert len(found) == 6
    assert found['app/AGENTS.md'].scope == 'app'
    assert found['harness/policies/safety.md'].scope == '.'
    assert found['AGENTS.md'].sha256 == hashlib.sha256(b'rules').hexdigest()
    assert any(i.reason == 'multiple_rule_sources_require_validation' for i in first.issues)
    assert 'rules' not in repr(asdict(first))
    assert before == {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_no_harness_is_complete(tmp_path):
    assert discover_harness(repository(tmp_path)).complete


def test_symlinks_sensitive_and_unknown_formats_are_reported(tmp_path):
    root = repository(tmp_path)
    write(root, 'harness/secret.md', 'private value')
    write(root, 'harness/custom.xyz')
    (root / 'AGENTS.md').symlink_to('/etc/passwd')
    result = discover_harness(root)
    assert not result.complete
    assert not result.candidates
    assert {i.reason for i in result.issues} == {
        'sensitive_name_excluded', 'unsupported_harness_format', 'symlink_excluded'
    }
    assert 'private value' not in repr(result)


@pytest.mark.parametrize('content,reason', [(b'\x00', 'binary_file'), (b'\xff', 'non_utf8_file')])
def test_invalid_text(tmp_path, content, reason):
    root = repository(tmp_path)
    (root / 'AGENTS.md').write_bytes(content)
    assert discover_harness(root).issues[0].reason == reason


@pytest.mark.parametrize('limits,reason', [
    (DiscoveryLimits(file_bytes=2), 'file_size_limit'),
    (DiscoveryLimits(total_bytes=2), 'total_bytes_limit'),
    (DiscoveryLimits(entries=1), 'entry_limit'),
    (DiscoveryLimits(depth=1), 'depth_limit'),
])
def test_limits_never_report_absence_as_complete(tmp_path, limits, reason):
    root = repository(tmp_path)
    write(root, 'AGENTS.md')
    write(root, 'a/b/AGENTS.md')
    result = discover_harness(root, limits=limits)
    assert not result.complete
    assert reason in {i.reason for i in result.issues}


def test_rejects_unsafe_roots_and_invalid_limits(tmp_path):
    repository(tmp_path)
    with pytest.raises(ValueError):
        discover_harness(Path('.'))
    with pytest.raises(ValueError):
        discover_harness(tmp_path / '..' / tmp_path.name)
    (tmp_path / 'alias').symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError):
        discover_harness(tmp_path / 'alias')
    with pytest.raises(ValueError):
        DiscoveryLimits(entries=0)


def test_rejects_symlink_git_metadata(tmp_path):
    (tmp_path / '.git').symlink_to('/tmp', target_is_directory=True)
    with pytest.raises(ValueError):
        discover_harness(tmp_path)


def test_unreadable_candidate_is_incomplete(tmp_path, monkeypatch):
    import sf_factory.harness_discovery as module
    root = repository(tmp_path)
    write(root, 'AGENTS.md')
    original = module.os.open

    def restricted(path, *args, **kwargs):
        if path == 'AGENTS.md':
            raise PermissionError('denied')
        return original(path, *args, **kwargs)

    # Preserve the capability probe when substituting os.open.
    monkeypatch.setattr(module.os, 'supports_dir_fd', module.os.supports_dir_fd | {restricted})
    monkeypatch.setattr(module.os, 'open', restricted)
    result = discover_harness(root)
    assert not result.complete
    assert result.issues[0].reason == 'file_unreadable_or_changed'


def test_file_replaced_during_scan_is_not_accepted(tmp_path, monkeypatch):
    import sf_factory.harness_discovery as module
    root = repository(tmp_path)
    write(root, 'AGENTS.md')
    original = module.os.open

    def replace(path, *args, **kwargs):
        if path == 'AGENTS.md':
            (root / 'AGENTS.md').unlink()
            write(root, 'AGENTS.md', 'replacement')
        return original(path, *args, **kwargs)

    monkeypatch.setattr(module.os, 'supports_dir_fd', module.os.supports_dir_fd | {replace})
    monkeypatch.setattr(module.os, 'open', replace)
    result = discover_harness(root)
    assert not result.complete
    assert not result.candidates
    assert 'file_changed' in {i.reason for i in result.issues}


def test_directory_replacement_is_not_scanned(tmp_path, monkeypatch):
    import sf_factory.harness_discovery as module
    root = repository(tmp_path)
    write(root, 'child/AGENTS.md')
    original = module.os.open

    def replace(path, *args, **kwargs):
        if path == 'child':
            (root / 'child').rename(root / 'old-child')
            write(root, 'child/AGENTS.md', 'replacement')
        return original(path, *args, **kwargs)

    monkeypatch.setattr(module.os, 'supports_dir_fd', module.os.supports_dir_fd | {replace})
    monkeypatch.setattr(module.os, 'open', replace)
    result = discover_harness(root)
    assert not result.candidates
    assert not result.complete
    assert 'directory_changed' in {i.reason for i in result.issues}


def test_ignored_outputs_do_not_become_candidates(tmp_path):
    root = repository(tmp_path)
    write(root, 'node_modules/library/AGENTS.md')
    write(root, '.venv/package/AGENTS.md')
    write(root, 'dist/AGENTS.md')
    result = discover_harness(root)
    assert result.complete
    assert not result.candidates
