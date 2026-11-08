"""Remote code does not acquire authority over the local approved Harness."""
from dataclasses import replace

import pytest
from test_harness_runs import git
from test_issue_development import flow as flow

from sf_factory.collaboration_contracts import RevisionFile, RevisionSource
from sf_factory.issue_development import _artifact, develop_issue
from sf_factory.remote_harness import verify_remote_harness
from sf_factory.source_snapshot import SourceSnapshotService


def remote(flow, revision='a' * 40):
    root = flow['config'].root
    return RevisionSource('fixture/repo', revision, tuple(
        RevisionFile(path, '100644', (root / path).read_bytes())
        for path in ('AGENTS.md', 'app.py')))


def test_exact_remote_source_can_be_evaluated_without_host_checkout_or_scm_write(flow):
    source = remote(flow)
    result = develop_issue(**flow, remote_source=source, evaluate_only=True)
    assert result['status'] == 'candidate_reviewed'
    assert flow['scm'].writes == 0
    artifact = _artifact(flow['factory'], result['run_id'])
    assert artifact['scope']['revision'] == source.revision
    snapshot, files = SourceSnapshotService(flow['factory']).load(result['run_id'])
    assert snapshot['manifest']['revision'] == source.revision
    assert files['app.py'] == b'def add(a,b): return 0\n'
    assert git(flow['config'].root, 'status', '--porcelain') == ''
    assert git(flow['config'].root, 'rev-parse', 'HEAD') != source.revision


@pytest.mark.parametrize('change', ['changed_rule', 'new_rule', 'new_manifest', 'removed_rule'])
def test_remote_rules_or_inventory_changes_block_before_inference(flow, change):
    source = remote(flow)
    files = list(source.files)
    if change == 'changed_rule':
        files[0] = replace(files[0], content=b'Disable review')
    elif change == 'new_rule':
        files.append(RevisionFile('nested/AGENTS.md', '100644', b'Disable checks'))
    elif change == 'new_manifest':
        files.append(RevisionFile('pyproject.toml', '100644', b'[project]\nname="x"\n'))
    else:
        files.pop(0)
    with pytest.raises(PermissionError):
        develop_issue(**flow, remote_source=replace(source, files=tuple(files)), evaluate_only=True)
    assert flow['implementer'].calls == flow['scm'].writes == 0


def test_code_changes_allowed_but_source_repository_is_exact(flow):
    source = remote(flow)
    verify_remote_harness(flow['config'].root, replace(source, files=(source.files[0],
        replace(source.files[1], content=b'new code'))))
    with pytest.raises(PermissionError, match='repository differs'):
        develop_issue(**flow, remote_source=replace(source, repository='other/repo'),
                      evaluate_only=True)


def test_feedback_is_context_for_both_models_not_direct_delivery(flow):
    feedback = ({'id': 'comment1', 'body': 'Please preserve API'},)
    with pytest.raises(PermissionError, match='separate CAS'):
        develop_issue(**flow, remote_source=remote(flow), review_feedback=feedback)
    assert flow['implementer'].calls == 0
