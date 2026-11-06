"""Reject malformed/changed rules and references without running commands."""
import hashlib
import json
import sys

import pytest

from sf_factory.cli import main
from sf_factory.harness_validation import validate_harness

PROFILE = '''apiVersion: generic-software-factory/v1alpha1
kind: ProjectProfile
metadata:
  name: demo
spec:
  language: python
  definitionOfDone: [Tests pass]
  repositoryRoot: .
  commands:
    test: echo never-executed
  architectureDocs: [docs/design.md]
'''


def setup(tmp_path, profile=PROFILE):
    (tmp_path / '.git').mkdir()
    (tmp_path / 'config').mkdir()
    (tmp_path / 'config/project.yaml').write_text(profile)
    (tmp_path / 'docs').mkdir()
    (tmp_path / 'docs/design.md').write_text('architecture')
    return tmp_path


def test_profile_is_valid_but_no_commands_or_contents_are_returned(tmp_path):
    root = setup(tmp_path)
    result = validate_harness(root)
    assert result.valid
    assert result.profiles[0].command_names == ('test',)
    assert result.profiles[0].references == (
        ('docs/design.md', hashlib.sha256(b'architecture').hexdigest()),
    )
    assert 'never-executed' not in repr(result)
    assert not (root / '.sf-factory').exists()


@pytest.mark.parametrize('old,new', [
    ('v1alpha1', 'v2'),
    ('ProjectProfile', 'Factory'),
    ('name: demo', 'name: 123'),
    ('repositoryRoot: .', 'repositoryRoot: ..'),
    ('test: echo never-executed', 'test: "<configure-test-command>"'),
    ('test: echo never-executed', 'test: [echo]'),
    ('docs/design.md', '../outside.md'),
    ('docs/design.md', '/etc/passwd'),
    ('docs/design.md', '.env'),
    ('docs/design.md', 'docs/secrets.md'),
    ('docs/design.md', 'docs/missing.md'),
])
def test_invalid_profiles_never_pass(tmp_path, old, new):
    result = validate_harness(setup(tmp_path, PROFILE.replace(old, new)))
    assert not result.valid
    assert not result.profiles
    assert result.issues[-1].code == 'invalid_or_changed_candidate'


def test_reference_symlink_rejected(tmp_path):
    root = setup(tmp_path)
    (root / 'docs/design.md').unlink()
    (root / 'docs/design.md').symlink_to('/etc/passwd')
    assert not validate_harness(root).valid


@pytest.mark.parametrize('body', [
    'a: 1\na: 2', 'a: &a [*a]', 'a: !!python/object:builtins.object {}',
    '[' * 40 + '1' + ']' * 40,
])
def test_unsafe_or_ambiguous_yaml_rejected(tmp_path, body):
    root = setup(tmp_path, body)
    assert not validate_harness(root).valid


@pytest.mark.parametrize('name,body', [
    ('package.json', '{"a":1,"a":2}'),
    ('package.json', '{"a":NaN}'),
    ('package.json', '[]'),
    ('pyproject.toml', 'invalid toml'),
])
def test_invalid_manifests_rejected(tmp_path, name, body):
    root = setup(tmp_path)
    (root / name).write_text(body)
    result = validate_harness(root)
    assert any(i.path == name and i.code == 'invalid_or_changed_candidate' for i in result.issues)


def test_competing_sources_and_examples_are_not_activated(tmp_path):
    root = setup(tmp_path)
    (root / 'AGENTS.md').write_text('instructions')
    (root / 'config/project.example.yaml').write_text(PROFILE)
    result = validate_harness(root)
    assert not result.valid
    assert len(result.profiles) == 1
    assert 'example_profile_not_active' in {i.code for i in result.issues}
    assert 'multiple_rule_sources_require_validation' in {i.code for i in result.issues}


def test_cli_validation_returns_json_and_status(tmp_path, monkeypatch, capsys):
    root = setup(tmp_path)
    monkeypatch.setattr(sys, 'argv', ['sf', 'harness', 'validate', str(root)])
    assert main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result['valid'] is True
    assert not (root / '.sf-factory').exists()


def test_candidate_changed_after_discovery_is_rejected(tmp_path, monkeypatch):
    import sf_factory.harness_validation as module
    root = setup(tmp_path)
    original = module.discover_harness

    def changed(path):
        result = original(path)
        (root / 'config/project.yaml').write_text(PROFILE.replace('name: demo', 'name: changed'))
        return result

    monkeypatch.setattr(module, 'discover_harness', changed)
    result = validate_harness(root)
    assert not result.valid
    assert not result.profiles


def test_invalid_utf8_reads_still_consume_shared_budget(tmp_path):
    import os

    from sf_factory.harness_validation import _read
    (tmp_path / 'invalid.md').write_bytes(b'\xff' * 8)
    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    budget = [10]
    try:
        with pytest.raises(UnicodeError):
            _read(fd, 'invalid.md', budget)
        assert budget == [2]
        with pytest.raises(ValueError):
            _read(fd, 'invalid.md', budget)
    finally:
        os.close(fd)
