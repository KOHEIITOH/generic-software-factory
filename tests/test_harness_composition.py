"""Composition requires complete, explicit, scope-aware choices."""
import json
import sys
from dataclasses import replace

import pytest

from sf_factory.cli import main
from sf_factory.harness_composition import compose_harness
from sf_factory.harness_validation import validate_harness


def setup(tmp_path):
    (tmp_path / '.git').mkdir()
    (tmp_path / 'AGENTS.md').write_text('root instructions')
    (tmp_path / 'harness').mkdir()
    (tmp_path / 'harness/safety.md').write_text('extra rules')
    (tmp_path / 'app').mkdir()
    (tmp_path / 'app/AGENTS.md').write_text('nested rules')
    return tmp_path


def test_order_and_exclusions_are_explicit_and_hashed(tmp_path):
    validation = validate_harness(setup(tmp_path))
    assert not validation.valid
    result = compose_harness(validation, target='app',
                             selected=('AGENTS.md', 'harness/safety.md', 'app/AGENTS.md'))
    assert [c.path for c in result.sources] == ['AGENTS.md', 'harness/safety.md', 'app/AGENTS.md']
    again = compose_harness(validation, target='app',
                            selected=('AGENTS.md', 'harness/safety.md', 'app/AGENTS.md'))
    assert result.bundle_hash == again.bundle_hash
    reordered = compose_harness(validation, target='app',
                                selected=('harness/safety.md', 'AGENTS.md', 'app/AGENTS.md'))
    assert result.bundle_hash != reordered.bundle_hash
    excluded = compose_harness(validation, target='app', selected=('AGENTS.md', 'app/AGENTS.md'),
                               excluded=(('harness/safety.md', 'not adopted for this task'),))
    assert excluded.bundle_hash != result.bundle_hash
    changed_reason = compose_harness(validation, target='app',
                                     selected=('AGENTS.md', 'app/AGENTS.md'),
                                     excluded=(('harness/safety.md', 'different rationale'),))
    assert changed_reason.bundle_hash != excluded.bundle_hash


@pytest.mark.parametrize('selected,excluded', [
    (('AGENTS.md',), ()),
    (('AGENTS.md', 'harness/safety.md', 'AGENTS.md'), ()),
    (('AGENTS.md', 'missing.md'), (('harness/safety.md', 'reason'),)),
    (('AGENTS.md',), (('harness/safety.md', ''),)),
    (('AGENTS.md',), (('AGENTS.md', 'reason'), ('harness/safety.md', 'reason'))),
    ((), (('AGENTS.md', 'reason'), ('harness/safety.md', 'reason'))),
])
def test_ambiguous_or_incomplete_selections_fail(tmp_path, selected, excluded):
    validation = validate_harness(setup(tmp_path))
    with pytest.raises(ValueError):
        compose_harness(validation, target='.', selected=selected, excluded=excluded)


def test_nested_sources_do_not_apply_to_parent_or_sibling(tmp_path):
    validation = validate_harness(setup(tmp_path))
    parent = compose_harness(validation, target='.', selected=('AGENTS.md', 'harness/safety.md'))
    assert all(c.scope == '.' for c in parent.sources)
    with pytest.raises(ValueError):
        compose_harness(validation, target='other',
                        selected=('AGENTS.md', 'harness/safety.md', 'app/AGENTS.md'))


@pytest.mark.parametrize('target', ['../outside', '/tmp', 'app/../app', 'app//nested', './app'])
def test_target_must_be_canonical_relative_scope(tmp_path, target):
    with pytest.raises(ValueError):
        compose_harness(validate_harness(setup(tmp_path)), target=target, selected=('AGENTS.md',))


def test_exclusions_cannot_suppress_syntax_or_read_errors(tmp_path):
    root = setup(tmp_path)
    (root / 'harness/bad.yaml').write_text('bad: [')
    with pytest.raises(ValueError):
        compose_harness(validate_harness(root), target='.',
                        selected=('AGENTS.md', 'harness/safety.md'),
                        excluded=(('harness/bad.yaml', 'ignore invalid rules'),))


def test_changed_inventory_changes_approval_fingerprint(tmp_path):
    root = setup(tmp_path)
    before = compose_harness(validate_harness(root), target='.',
                             selected=('AGENTS.md', 'harness/safety.md'))
    (root / 'harness/safety.md').write_text('changed')
    after = compose_harness(validate_harness(root), target='.',
                            selected=('AGENTS.md', 'harness/safety.md'))
    assert before.bundle_hash != after.bundle_hash


def test_invalid_status_without_evidence_cannot_be_composed(tmp_path):
    validation = validate_harness(setup(tmp_path))
    validation = replace(validation, discovery=replace(validation.discovery, issues=()))
    with pytest.raises(ValueError):
        compose_harness(validation, target='.', selected=('AGENTS.md', 'harness/safety.md'))


def test_cli_emits_composition_without_factory_state(tmp_path, monkeypatch, capsys):
    root = setup(tmp_path)
    monkeypatch.setattr(sys, 'argv', ['sf', 'harness', 'compose', str(root),
                                    '--select', 'AGENTS.md',
                                    '--exclude', 'harness/safety.md', 'not adopted'])
    assert main() == 0
    output = json.loads(capsys.readouterr().out)
    assert len(output['bundle_hash']) == 64
    assert output['sources'][0]['path'] == 'AGENTS.md'
    assert output['excluded'] == [['harness/safety.md', 'not adopted']]
    assert not (root / '.sf-factory').exists()


def test_profiles_require_one_effective_validated_choice(tmp_path):
    (tmp_path / '.git').mkdir()
    (tmp_path / 'config').mkdir()
    profile = '''apiVersion: generic-software-factory/v1alpha1
kind: ProjectProfile
metadata: {name: demo}
spec:
  repositoryRoot: .
  language: python
  commands: {test: pytest}
  definitionOfDone: [Tests pass]
'''
    for name in ['project.yaml', 'project-other.yaml', 'project.example.yaml']:
        (tmp_path / 'config' / name).write_text(profile)
    validation = validate_harness(tmp_path)
    with pytest.raises(ValueError):
        compose_harness(validation, target='.',
                        selected=('config/project.yaml', 'config/project-other.yaml'),
                        excluded=(('config/project.example.yaml', 'template'),))
    with pytest.raises(ValueError):
        compose_harness(validation, target='.', selected=('config/project.example.yaml',),
                        excluded=(('config/project.yaml', 'unused'),
                                  ('config/project-other.yaml', 'unused')))
    result = compose_harness(validation, target='.', selected=('config/project.yaml',),
                             excluded=(('config/project-other.yaml', 'alternate profile'),
                                       ('config/project.example.yaml', 'template')))
    assert result.profile is not None
    assert result.profile.path == 'config/project.yaml'
