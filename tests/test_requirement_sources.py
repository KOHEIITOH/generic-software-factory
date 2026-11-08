"""Requirement discovery is deterministic, bounded and bound to exact Git blobs."""
import hashlib
import json
from dataclasses import asdict, replace

import pytest
from test_issue_development import flow as flow

from sf_factory.collaboration_contracts import RevisionFile, RevisionSource
from sf_factory.development_config import DevelopmentConfig
from sf_factory.issue_development import develop_issue
from sf_factory.requirement_sources import (
    RequirementSourceError,
    discover_requirement_sources,
    verify_requirement_sources,
)


def source(files):
    return RevisionSource('fixture/repo', 'a' * 40,
        tuple(RevisionFile(p, '100644', body) for p, body in files.items()))


def test_explicit_selection_wins_and_never_adds_other_candidates():
    remote = source({'README.md': b'overview', 'docs/requirements.md': b'current requirements',
                     'custom/input.txt': b'operator selected requirements'})
    selection = discover_requirement_sources(remote, explicit=('custom/input.txt',))
    assert selection.mode == 'explicit'
    assert selection.source_ids == ('issue', 'custom/input.txt')
    assert selection.documents[0].reason == 'operator_context_path'


def test_auto_discovers_localized_readme_requirement_spec_and_design_but_not_history_or_rules():
    remote = source({'README.ja.md': '日本語の概要'.encode(), 'docs/要件定義.md': b'requirements',
        'docs/specifications/payment.md': b'spec', 'docs/architecture.md': b'architecture',
        'AGENTS.md': b'Harness policy', 'docs/decisions/0001.md': b'obsolete decision',
        'docs/archive/requirements.md': b'obsolete requirement', 'docs/install.md': b'install',
        'tests/requirements.md': b'fixture', 'requirements.txt': b'pytest==1.0',
        'node_modules/spec/requirements.md': b'vendored', 'app.py': b'source'})
    selection = discover_requirement_sources(remote)
    assert selection.mode == 'auto'
    assert [d.path for d in selection.documents] == [
        'README.ja.md', 'docs/architecture.md', 'docs/specifications/payment.md',
        'docs/要件定義.md']
    assert selection == discover_requirement_sources(replace(remote, files=tuple(reversed(
        remote.files))))
    assert len(selection.fingerprint) == 64
    assert 'content' not in json.dumps(selection.document())


def test_no_documents_preserves_issue_only_planning_without_inventing_requirements():
    selection = discover_requirement_sources(source({'app.py': b'code'}))
    assert selection.mode == 'issue_only' and selection.source_ids == ('issue',)


@pytest.mark.parametrize('case', ['missing', 'too_many', 'oversize', 'total', 'binary', 'encoding',
                                  'empty', 'slots'])
def test_missing_or_unreadable_or_truncated_context_is_never_silently_accepted(case):
    files = {'README.md': b'requirements'}
    kwargs = {}
    if case == 'missing':
        kwargs['explicit'] = ('nonexistent.md',)
    elif case == 'too_many':
        files = {f'docs/requirements/{i}.md': b'requirements' for i in range(13)}
    elif case == 'oversize':
        files['README.md'] = b'x' * 24577
    elif case == 'total':
        files = {f'docs/requirements/{i}.md': b'x' * 20000 for i in range(3)}
    elif case == 'binary':
        files['README.md'] = b'abc\0def'
    elif case == 'encoding':
        files['README.md'] = b'\xff\xfe'
    elif case == 'empty':
        files['README.md'] = b'  \n'
    else:
        kwargs['reference_slots'] = 0
    with pytest.raises(RequirementSourceError):
        discover_requirement_sources(source(files), **kwargs)


def test_requirements_are_hash_pinned_across_code_changes_and_never_rescanned():
    initial = source({'docs/spec.md': b'approved requirement', 'app.py': b'old code'})
    selected = discover_requirement_sources(initial).document()
    code_change = replace(initial, revision='b' * 40, files=(initial.files[0],
        RevisionFile('app.py', '100644', b'new code')))
    verify_requirement_sources(selected, code_change)
    with pytest.raises(RequirementSourceError, match='requirements_source_changed'):
        verify_requirement_sources(selected, source({'docs/spec.md': b'changed requirement'}))
    selected['mode'] = 'explicit'
    with pytest.raises(RequirementSourceError, match='requirements_evidence_invalid'):
        verify_requirement_sources(selected, initial)


def test_omitted_context_paths_has_same_config_and_fingerprint_as_explicit_empty(flow):
    doc = json.loads(json.dumps(asdict(flow['config']), default=str))
    doc.pop('context_paths')
    config = DevelopmentConfig.from_document(doc)
    assert config == flow['config']
    assert config.fingerprint == flow['config'].fingerprint


def test_content_hash_cannot_grant_a_new_path_or_accept_changed_source(flow):
    config = flow['config']
    with pytest.raises(ValueError, match='within approved'):
        replace(config, context_hashes=(('other.txt', 'a' * 64),))
    wrong = replace(config, context_paths=('AGENTS.md',),
                    context_hashes=(('AGENTS.md', 'f' * 64),))
    with pytest.raises(PermissionError, match='reference content changed'):
        develop_issue(**{**flow, 'config': wrong})
    assert flow['implementer'].calls == flow['scm'].writes == 0
    correct = replace(wrong, context_hashes=(('AGENTS.md', hashlib.sha256(
        (config.root / 'AGENTS.md').read_bytes()).hexdigest()),))
    assert develop_issue(**{**flow, 'config': correct})['status'] == 'draft_pr_created'


def test_extensionless_readme_and_documentation_conventions_are_supported():
    selected = discover_requirement_sources(source({'README': b'project overview',
        'documentation/specification.markdown': b'approved requirements',
        'documentation/install.md': b'not automatically selected'}))
    assert selected.source_ids == ('issue', 'README', 'documentation/specification.markdown')


def test_implementation_cannot_rewrite_a_hash_frozen_reference(flow):
    from sf_factory.issue_development import DevelopmentStopped
    config = flow['config']
    before = (config.root / 'app.py').read_bytes()
    config = replace(config, context_paths=('app.py',),
                     context_hashes=(('app.py', hashlib.sha256(before).hexdigest()),))
    with pytest.raises(DevelopmentStopped):
        develop_issue(**{**flow, 'config': config})
    assert flow['implementer'].calls == 1
    assert flow['reviewer'].calls == flow['scm'].writes == 0
