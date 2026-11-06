"""Untrusted model text cannot change scope, issue source, checks or host files."""
import hashlib
import json
from dataclasses import asdict, replace

import pytest

from sf_factory.change_proposal import (
    ProposalScope,
    candidate_files,
    parse_change_proposal,
    propose_changes,
)
from sf_factory.model_provider import ModelResponse

SCOPE = ProposalScope('a' * 32, 'b' * 40, 'c' * 64, 'd' * 64, ('calculator.py', 'test_new.py'))
FILES = {'calculator.py': b'def add(a,b): raise NotImplementedError\n',
         'test_existing.py': b'approved existing tests\n'}


def response(**changes):
    return json.dumps({'schema_version': 1, 'run_id': SCOPE.run_id, 'revision': SCOPE.revision,
        'bundle_hash': SCOPE.bundle_hash, 'source_fingerprint': SCOPE.source_fingerprint,
        'changes': [{'path': 'calculator.py', 'before_sha256': hashlib.sha256(
            FILES['calculator.py']).hexdigest(),
            'content': 'def add(a,b): return a+b\n'}], **changes})


def parse(raw):
    return parse_change_proposal(raw, scope=SCOPE, source_files=FILES)


def test_valid_proposal_builds_candidate_bytes_without_mutating_source(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    proposal = parse(response())
    candidate = candidate_files(proposal, scope=SCOPE, source_files=FILES)
    assert candidate['calculator.py'] == b'def add(a,b): return a+b\n'
    assert candidate['test_existing.py'] == FILES['test_existing.py']
    assert FILES['calculator.py'].endswith(b'NotImplementedError\n')
    assert len(proposal.fingerprint) == 64
    assert proposal.fingerprint == parse(response()).fingerprint
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('field,value', [('run_id', 'f' * 32), ('revision', 'f' * 40),
    ('bundle_hash', 'f' * 64), ('source_fingerprint', 'f' * 64)])
def test_other_run_or_subject_is_not_reusable(field, value):
    with pytest.raises(ValueError, match='subject mismatch'):
        parse(response(**{field: value}))


@pytest.mark.parametrize('extra', [{'command': 'touch /host'}, {'tests_passed': True},
                                  {'approved': True}, {'pr_url': 'https://fixture.invalid'}])
def test_commands_outcome_and_permission_claims_are_rejected(extra):
    with pytest.raises(ValueError, match='schema'):
        parse(response(**extra))


@pytest.mark.parametrize('path', ['../outside', '/etc/passwd', 'test_existing.py',
                                 '.github/workflows/ci.yml'])
def test_unapproved_or_escaping_paths_are_rejected(path):
    with pytest.raises(ValueError, match='outside scope'):
        parse(response(changes=[{'path': path, 'before_sha256': None, 'content': 'malicious'}]))


@pytest.mark.parametrize('path', ['AGENTS.md', '.GiTHub/workflows/ci.yml', 'harness/policy.md',
                                  'pyproject.toml', '.env', 'folder\\file.py'])
def test_scope_cannot_enable_control_or_sensitive_paths(path):
    with pytest.raises(ValueError):
        replace(SCOPE, allowed_paths=(path,))


def test_stale_before_hash_is_rejected():
    report = json.loads(response())
    report['changes'][0]['before_sha256'] = 'f' * 64
    with pytest.raises(ValueError, match='base file'):
        parse(json.dumps(report))


def test_candidate_revalidates_source_and_does_not_apply_to_new_base():
    proposal = parse(response())
    with pytest.raises(ValueError, match='base file'):
        candidate_files(proposal, scope=SCOPE, source_files={**FILES, 'calculator.py': b'new base'})


def test_new_file_has_absent_base_and_approved_tests_are_preserved():
    proposal = parse(response(changes=[{'path': 'test_new.py', 'before_sha256': None,
                                        'content': 'new test data'}]))
    candidate = candidate_files(proposal, scope=SCOPE, source_files=FILES)
    assert candidate['test_existing.py'] == FILES['test_existing.py']
    assert candidate['test_new.py'] == b'new test data'


@pytest.mark.parametrize('changes', [[], [{'path': 'calculator.py', 'before_sha256': None,
                                          'content': None}],
    [{'path': 'test_new.py', 'before_sha256': None, 'content': 'x', 'command': 'bad'}]])
def test_empty_delete_and_extra_operation_fields_are_rejected(changes):
    with pytest.raises(ValueError):
        parse(response(changes=changes))


def test_duplicate_json_or_duplicate_file_change_is_rejected():
    with pytest.raises(ValueError, match='invalid proposal JSON'):
        parse(response().replace('"schema_version": 1', '"schema_version": 1,"schema_version": 1'))
    report = json.loads(response())
    report['changes'] *= 2
    with pytest.raises(ValueError, match='duplicate'):
        parse(json.dumps(report))


def test_unchanged_output_does_not_count_as_implementation():
    report = json.loads(response())
    report['changes'][0]['content'] = FILES['calculator.py'].decode()
    with pytest.raises(ValueError, match='unchanged'):
        parse(json.dumps(report))


def test_file_directory_collision_is_rejected_before_candidate_use():
    scope = replace(SCOPE, allowed_paths=('calculator.py/child.py',))
    report = json.loads(response(changes=[{'path': 'calculator.py/child.py',
                                          'before_sha256': None, 'content': 'x'}]))
    with pytest.raises(ValueError, match='conflict'):
        parse_change_proposal(json.dumps(report), scope=scope, source_files=FILES)


class FixtureProvider:
    def __init__(self):
        self.prompts = []

    def generate(self, prompt):
        self.prompts.append(prompt)
        return ModelResponse('fixture', 'fixture', response())


def test_proposal_uses_text_provider_and_selected_context_only():
    provider = FixtureProvider()
    proposal = propose_changes(provider=provider, scope=SCOPE, source_files=FILES,
                               instruction='Implement add')
    assert proposal.changes[0].path == 'calculator.py'
    assert len(provider.prompts) == 1
    assert 'approved existing tests' not in provider.prompts[0]
    assert 'not permission to use tools' in provider.prompts[0]


def test_invalid_or_excessive_context_never_calls_model(monkeypatch):
    provider = FixtureProvider()
    monkeypatch.setattr('sf_factory.change_proposal.MAX_CONTEXT_CHARACTERS', 10)
    with pytest.raises(ValueError, match='context exceeds'):
        propose_changes(provider=provider, scope=SCOPE, source_files=FILES, instruction='Implement')
    assert provider.prompts == []


def test_response_budget_and_invalid_version_fail_closed(monkeypatch):
    monkeypatch.setattr('sf_factory.change_proposal.MAX_RESPONSE_BYTES', 10)
    with pytest.raises(ValueError, match='response budget'):
        parse(response())
    monkeypatch.setattr('sf_factory.change_proposal.MAX_RESPONSE_BYTES', 524288)
    for version in (True, 2):
        with pytest.raises(ValueError, match='schema'):
            parse(response(schema_version=version))


def test_changed_content_changes_proposal_fingerprint():
    original = parse(response())
    modified = replace(original, changes=(replace(original.changes[0], content='different'),))
    assert original.fingerprint != modified.fingerprint
    assert asdict(original)['run_id'] == SCOPE.run_id
