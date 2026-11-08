"""Explicit/auto references reach planning, independent review and actual checked PRs."""
import json
from dataclasses import asdict, replace

import pytest
from test_harness_runs import commit, git
from test_issue_development import flow as flow
from test_requirement_workflow import WorkflowModel, merge
from test_requirement_workflow import requirement_flow as requirement_flow

from sf_factory.automation_state import AutomationSession, fingerprint
from sf_factory.collaboration_contracts import RevisionFile
from sf_factory.requirement_plan import parse_plan
from sf_factory.requirement_workflow import PLAN_LIMITS, advance_requirements


class ObservedModel(WorkflowModel):
    def __init__(self, identity, *, citation='docs/requirements.md'):
        super().__init__(identity)
        self.citation = citation
        self.inputs = []
        self.review_status = 'ready'
        self.bad_review = None
        self.reject_proposal = None

    def generate(self, prompt):
        data = json.loads(prompt.split('\n', 1)[1])
        self.inputs.append(data)
        response = super().generate(prompt)
        report = json.loads(response.text)
        if 'max_children' in data and 'plan' not in data:
            for row in report['requirements']:
                row['sources'] = [self.citation]
            if self.reject_proposal:
                report = {'schema_version': 1, 'status': self.reject_proposal,
                          'reason': 'Fixture requirements cannot be safely interpreted.'}
        elif 'plan' in data:
            report.update(requirements_status=self.review_status,
                concerns=[] if self.review_status == 'ready' else ['Fixture conflicting inputs'])
            if self.bad_review == 'hash':
                report['sources_fingerprint'] = 'f' * 64
            elif self.bad_review == 'missing':
                report['source_assessments'].pop()
            elif self.bad_review == 'irrelevant':
                for row in report['source_assessments']:
                    row['status'] = 'irrelevant'
            elif self.bad_review == 'uncited':
                for row in report['source_assessments']:
                    row['status'] = 'requirements'
        return replace(response, text=json.dumps(report))


def install_documents(args, files):
    root, scm = args['config'].root, args['scm']
    for path, body in files.items():
        destination = root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(body)
    commit(root)
    previous = scm.parent
    scm.parent = git(root, 'rev-parse', 'HEAD')
    scm.sources[scm.parent] = scm.sources[previous]
    original = scm.read_revision
    def read(repo, revision):
        source = original(repo, revision)
        return replace(source, files=source.files + tuple(
            RevisionFile(path, '100644', body) for path, body in files.items()))
    scm.read_revision = read
    args['implementer'] = ObservedModel('implementation')
    args['reviewer'] = ObservedModel('review')
    return files


def session(args):
    config = args['config']
    return AutomationSession(args['factory'].root,
        subject='requirements:' + config.repository + ':' + config.issue,
        config_fingerprint=fingerprint({'development': config.fingerprint, 'reviewers': ()}),
        limits=PLAN_LIMITS)


def test_auto_sources_are_cited_frozen_and_propagated_to_both_models_and_child_pr(requirement_flow):
    args = requirement_flow
    docs = install_documents(args, {'docs/requirements.md': b'add(a,b) must return their sum.',
                                    'README.md': b'An addition library overview.'})
    result = advance_requirements(**args, execute=True)
    assert result['reason'] == 'child_pr_submitted'
    evidence = result['requirement_sources']
    assert evidence['mode'] == 'auto'
    assert {d['path'] for d in evidence['documents']} == set(docs)
    plan_inputs = args['implementer'].inputs[0]
    assert plan_inputs['repository_context']['docs/requirements.md'] == docs[
        'docs/requirements.md'].decode()
    assert result['plan']['requirements'][0]['sources'] == ('docs/requirements.md',)
    assert result['planning_review']['report']['requirements_status'] == 'ready'
    implementation = next(d for d in args['implementer'].inputs if 'scope' in d)
    review = next(d for d in args['reviewer'].inputs if 'before' in d)
    assert docs['docs/requirements.md'].decode() == next(
        d['content'] for d in implementation['read_only_references']
        if d['path'] == 'docs/requirements.md')
    assert review['references']['docs/requirements.md'] == docs['docs/requirements.md'].decode()
    assert 'Requirement sources: docs/requirements.md' in args['tracker'].items['2'].prompt
    merge(args, '1')
    assert advance_requirements(**args, execute=True)['reason'] == 'child_merge_verified'
    calls = args['implementer'].calls
    docs['docs/requirements.md'] = b'Changed requirements after planning'
    stopped = advance_requirements(**args, execute=True)
    assert stopped['reason'] == 'requirements_source_changed' and stopped['status'] == 'stopped'
    assert args['implementer'].calls == calls and len(args['scm'].prs) == 1


def test_explicit_paths_override_auto_candidates_even_when_readme_conflicts(requirement_flow):
    args = requirement_flow
    install_documents(args, {'docs/requirements.md': b'Correct approved requirements.',
                              'README.md': b'Conflicting unselected text.'})
    args['config'] = replace(args['config'], context_paths=('docs/requirements.md',))
    result = advance_requirements(**args)
    assert result['reason'] == 'plan_ready'
    assert result['requirement_sources']['mode'] == 'explicit'
    assert 'README.md' not in args['implementer'].inputs[0]['repository_context']


@pytest.mark.parametrize('status', ['insufficient', 'conflicting'])
def test_independent_review_stops_without_external_child_or_pr_writes(requirement_flow, status):
    args = requirement_flow
    install_documents(args, {'docs/requirements.md': b'Conflicting or vague requirements.'})
    args['reviewer'].review_status = status
    result = advance_requirements(**args, execute=True)
    assert result['reason'] == 'requirements_' + status and result['status'] == 'stopped'
    assert result['planning_review']['report']['concerns']
    assert args['tracker'].creates == 0 and args['scm'].prs == {}
    calls = args['implementer'].calls
    assert advance_requirements(**args, execute=True)['status'] == 'stopped'
    assert args['implementer'].calls == calls


@pytest.mark.parametrize('status', ['insufficient', 'conflicting'])
def test_planner_can_decline_without_inventing_a_decomposition(requirement_flow, status):
    args = requirement_flow
    install_documents(args, {'docs/requirements.md': b'Incomplete requirements.'})
    args['implementer'].reject_proposal = status
    result = advance_requirements(**args)
    assert result['reason'] == 'requirements_' + status
    assert args['reviewer'].calls == args['tracker'].creates == 0
    assert result['planning_review']['report']['reason']


@pytest.mark.parametrize('kind', ['hash', 'missing', 'irrelevant', 'uncited'])
def test_missing_or_wrong_source_review_is_not_permission_to_create_issues(requirement_flow, kind):
    args = requirement_flow
    install_documents(args, {'docs/requirements.md': b'Requirements', 'README.md': b'Overview'})
    args['reviewer'].bad_review = kind
    assert advance_requirements(**args)['status'] == 'stopped'
    assert args['tracker'].creates == 0


def test_invented_or_missing_citations_are_rejected_before_review_or_write(requirement_flow):
    args = requirement_flow
    install_documents(args, {'docs/requirements.md': b'Known requirements'})
    args['implementer'].citation = 'docs/not-read.md'
    assert advance_requirements(**args)['status'] == 'stopped'
    assert args['reviewer'].calls == args['tracker'].creates == 0


def test_detection_limit_stops_before_any_inference_and_records_a_reason(requirement_flow):
    args = requirement_flow
    install_documents(args, {f'docs/spec/{i}.md': b'requirements' for i in range(13)})
    result = advance_requirements(**args)
    assert result['reason'] == 'requirements_discovery_limit'
    assert args['implementer'].calls == args['tracker'].creates == 0
    assert session(args).snapshot()['decisions'][-1]['facts']['candidate_count'] == 13


def test_existing_plans_without_source_citations_keep_their_fingerprint(flow):
    from test_requirement_workflow import plan_document
    old = plan_document()
    for requirement in old['requirements']:
        requirement.pop('sources')
    parsed = parse_plan(json.dumps(old), flow['config'], max_children=8)
    assert parsed.fingerprint == fingerprint(old)
    assert asdict(parsed)['requirements'][0]['sources'] == ()


def test_real_docker_auto_requirement_discovery_to_draft(requirement_flow, monkeypatch):
    import os
    image = os.environ.get('SF_TEST_DOCKER_IMAGE')
    if not image:
        pytest.skip('optional real Docker execution image not configured')
    from sf_factory.docker_execution import run_offline_command
    args = requirement_flow
    assert args['config'].image == image
    install_documents(args, {'docs/requirements.md': b'add(2,3) must return 5.'})
    monkeypatch.setattr('sf_factory.issue_development.run_offline_command', run_offline_command)
    monkeypatch.setattr('sf_factory.workspace_check.run_offline_command', run_offline_command)
    result = advance_requirements(**args, execute=True)
    assert result['reason'] == 'child_pr_submitted'
    assert result['requirement_sources']['mode'] == 'auto'


def test_web_progress_exposes_only_source_metadata_and_requirement_links(requirement_flow):
    from sf_factory.web_jobs import WebJobs
    from sf_factory.web_operator import OperatorProfiles
    from sf_factory.web_worker import run_job
    args = requirement_flow
    install_documents(args, {'docs/requirements.md': b'PRIVATE_REQUIREMENT_TEXT'})
    path = args['config'].root.parent / 'web-config.json'
    path.write_text(json.dumps(asdict(args['config']), default=str))
    profile = OperatorProfiles(args['factory'].root).register(path, 'Requirement evidence')
    store = WebJobs(args['factory'].root)
    store.enqueue(profile_id=profile['id'], config_fingerprint=profile['fingerprint'],
        action='plan', request_id='a' * 32, confirm_bedrock=True)
    assert run_job(args['factory'].root, 'a' * 32,
                   executor=lambda **kwargs: advance_requirements(**args))
    progress = store.progress('a' * 32)
    evidence = progress['requirement_sources']
    assert evidence['mode'] == 'auto' and evidence['review_status'] == 'ready'
    assert evidence['documents'][0]['path'] == 'docs/requirements.md'
    assert evidence['requirements'][0] == {
        'id': 'addition', 'sources': ['docs/requirements.md'], 'children': ['first', 'second']}
    assert 'PRIVATE_REQUIREMENT_TEXT' not in json.dumps(progress)
    assert 'interpretation' not in json.dumps(progress)


def test_no_documents_and_insufficient_issue_stop_without_inventing_context(requirement_flow):
    args = requirement_flow
    args['implementer'] = ObservedModel('implementation', citation='issue')
    args['reviewer'] = ObservedModel('review', citation='issue')
    args['reviewer'].review_status = 'insufficient'
    result = advance_requirements(**args)
    assert result['reason'] == 'requirements_insufficient'
    assert result['requirement_sources']['mode'] == 'issue_only'
    assert not result['requirement_sources']['documents']
    assert args['tracker'].creates == 0


def test_changed_documents_are_rechecked_before_resuming_unpublished_planning(
        requirement_flow, monkeypatch):
    import sf_factory.requirement_workflow as workflow
    args = requirement_flow
    docs = install_documents(args, {'docs/requirements.md': b'Original requirements'})
    save = workflow._save
    class ProcessLost(BaseException):
        pass
    def crash_after_review(session, data, code, **kwargs):
        result = save(session, data, code, **kwargs)
        if code == 'requirements_interpreted':
            raise ProcessLost()
        return result
    monkeypatch.setattr(workflow, '_save', crash_after_review)
    with pytest.raises(ProcessLost):
        advance_requirements(**args)
    monkeypatch.setattr(workflow, '_save', save)
    assert session(args).snapshot()['data']['phase'] == 'planning'
    scm = args['scm']
    scm.sources['f' * 40] = scm.sources[scm.parent]
    scm.parent = 'f' * 40
    docs['docs/requirements.md'] = b'Changed after process loss'
    calls = args['implementer'].calls
    assert advance_requirements(**args)['reason'] == 'requirements_source_changed'
    assert args['implementer'].calls == calls and args['tracker'].creates == 0


def test_requirement_references_cannot_become_child_write_targets(requirement_flow):
    args = requirement_flow
    install_documents(args, {'docs/requirements.md': b'Fixed requirement source'})
    args['config'] = replace(args['config'], allowed_paths=('app.py', 'docs/requirements.md'))
    class WritesRequirement(ObservedModel):
        def generate(self, prompt):
            response = super().generate(prompt)
            data = json.loads(prompt.split('\n', 1)[1])
            if 'max_children' in data and 'plan' not in data:
                report = json.loads(response.text)
                report['children'][0]['allowed_paths'] = ['docs/requirements.md']
                return replace(response, text=json.dumps(report))
            return response
    args['implementer'] = WritesRequirement('implementation')
    result = advance_requirements(**args)
    assert result['reason'] == 'requirements_reference_write_conflict'
    assert args['reviewer'].calls == args['tracker'].creates == 0
