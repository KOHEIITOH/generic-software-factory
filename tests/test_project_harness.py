"""Project text is reusable across repos, hash-bound, and never an execution grant."""
import json
from dataclasses import asdict, replace

import pytest
from test_issue_development import Model
from test_issue_development import flow as flow

from sf_factory.issue_development import develop_issue
from sf_factory.project_harness import ProjectHarness, ProjectRule

PROJECT = ProjectHarness('payments', (
    ProjectRule('quality', 'Preserve public API and approved tests.'),))


def test_project_layer_is_bound_to_run_and_same_shared_project(flow):
    flow['config'] = replace(flow['config'], project_harness=PROJECT)
    result = develop_issue(**flow)
    run = flow['factory'].show_run(result['run_id'])
    assert run['harness_manifest']['composition']['project_harness'] == json.loads(
        json.dumps(asdict(PROJECT)))
    assert flow['config'].fingerprint != replace(flow['config'], project_harness=None).fingerprint
    assert len(flow['factory'].project_registry().list_projects('local-cli')) == 1


@pytest.mark.parametrize('document', [
    {'project': 'p', 'rules': [], 'command': 'curl secrets'},
    {'project': 'p', 'rules': [{'name': 'quality', 'text': 'rules', 'approved': True}]},
    {'project': '../outside', 'rules': [{'name': 'quality', 'text': 'rules'}]},
    {'project': 'p', 'rules': [{'name': 'quality', 'text': 'a'}, {'name': 'quality', 'text': 'b'}]},
])
def test_project_rules_cannot_add_tools_commands_or_duplicate_layers(document):
    with pytest.raises((ValueError, TypeError)):
        ProjectHarness.from_document(document)


def test_shared_operator_file_is_loaded_and_repository_copy_is_rejected(flow):
    from sf_factory.issue_development_cli import load_config
    root = flow['config'].root.parent
    shared = root / 'project.json'
    shared.write_text(json.dumps(asdict(PROJECT)))
    config = root / 'operator.json'
    document = json.loads(json.dumps(asdict(flow['config']), default=str))
    document.pop('project_harness')
    document['project_harness_file'] = str(shared)
    config.write_text(json.dumps(document))
    loaded = load_config(config)
    assert loaded.project_harness == PROJECT
    inside = flow['config'].root / 'untrusted-project.json'
    inside.write_text(shared.read_text())
    document['project_harness_file'] = str(inside)
    config.write_text(json.dumps(document))
    with pytest.raises(PermissionError):
        load_config(config)


def test_implementation_and_review_both_receive_project_context(flow):
    class ObservedModel(Model):
        def generate(self, prompt):
            data = json.loads(prompt.split('\n', 1)[1])
            assert data['project_harness']['project'] == 'payments'
            assert data['project_harness']['rules'][0]['text'] == PROJECT.rules[0].text
            return super().generate(prompt)
    flow['config'] = replace(flow['config'], project_harness=PROJECT)
    flow['implementer'] = ObservedModel('implementation')
    flow['reviewer'] = ObservedModel('review')
    assert develop_issue(**flow)['status'] == 'draft_pr_created'


def test_nested_directory_rules_are_required_for_actual_changed_paths(tmp_path):
    from test_harness_runs import commit, git

    from sf_factory.harness_composition import compose_harness
    from sf_factory.harness_validation import validate_harness
    root = tmp_path / 'repo'
    root.mkdir()
    git(root, 'init', '-q')
    (root / 'AGENTS.md').write_text('repository-wide rules')
    (root / 'src').mkdir()
    (root / 'src/AGENTS.md').write_text('source-directory rules')
    commit(root)
    validation = validate_harness(root)
    with pytest.raises(ValueError, match='every applicable'):
        compose_harness(validation, target='.', selected=('AGENTS.md',),
                        change_paths=('src/app.py',), project_harness=PROJECT)
    selected = compose_harness(validation, target='.',
        selected=('AGENTS.md', 'src/AGENTS.md'), change_paths=('src/app.py',),
        project_harness=PROJECT)
    assert [source.path for source in selected.sources] == ['AGENTS.md', 'src/AGENTS.md']
    assert selected.project_harness == PROJECT
    assert selected.change_paths == ('src/app.py',)


def test_project_rule_content_change_changes_exact_bundle(tmp_path):
    from test_harness_runs import commit, git

    from sf_factory.harness_composition import compose_harness
    from sf_factory.harness_validation import validate_harness
    root = tmp_path / 'repo'
    root.mkdir()
    git(root, 'init', '-q')
    (root / 'AGENTS.md').write_text('repository rules')
    commit(root)
    validation = validate_harness(root)
    first = compose_harness(validation, target='.', selected=('AGENTS.md',),
                            project_harness=PROJECT)
    changed = replace(PROJECT, rules=(ProjectRule('quality', 'Different approved rules'),))
    second = compose_harness(validation, target='.', selected=('AGENTS.md',),
                             project_harness=changed)
    assert first.bundle_hash != second.bundle_hash
