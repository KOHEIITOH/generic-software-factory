"""Bounded external-Issue plan, serial execution and verified merge progression."""
from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import PurePosixPath

from sf_factory.automation_state import AutomationLimits, AutomationSession, fingerprint
from sf_factory.budgeted_model import BudgetedModel
from sf_factory.collaboration_contracts import CollaborationSourceControl, IssueTracker
from sf_factory.development_config import DevelopmentConfig
from sf_factory.factory import Factory
from sf_factory.file_state import lock_directory
from sf_factory.harness_validation import validate_harness
from sf_factory.issue_development import (
    DevelopmentStopped,
    _artifact,
    develop_issue,
    execution_readiness,
)
from sf_factory.model_provider import ModelProvider
from sf_factory.requirement_plan import (
    PlanChild,
    RequirementPlanningError,
    parse_plan,
    propose_plan,
)
from sf_factory.requirement_sources import (
    RequirementSourceError,
    discover_requirement_sources,
    verify_requirement_sources,
)
from sf_factory.review_automation import _save, advance_review
from sf_factory.source_control import SourceControlError
from sf_factory.state_store import StateConflict, StatePermissionDenied
from sf_factory.task_sources import ExternalIssue, TaskSourceAdapter

# One-level plan, <=8 units by default. Shared total covers plan, implementation
# and subsequent review repairs; no recursive splitting or dynamic budget increase.
PLAN_LIMITS = AutomationLimits(max_model_calls=32, max_tokens=6000000)


def child_scope(config: DevelopmentConfig, child: PlanChild, external_id: str,
                requirement_sources: dict | None = None) -> DevelopmentConfig:
    validation = validate_harness(config.root)
    applicable = set()
    for candidate in validation.discovery.candidates:
        scope = PurePosixPath(candidate.scope).parts
        if any(PurePosixPath(path).parts[:len(scope)] == scope for path in child.allowed_paths):
            applicable.add(candidate.path)
    paths = (tuple(d['path'] for d in requirement_sources['documents'])
             if requirement_sources else ())
    pins = dict(config.context_hashes)
    if requirement_sources:
        pins.update((d['path'], d['sha256']) for d in requirement_sources['documents'])
    return replace(config, issue=external_id, allowed_paths=child.allowed_paths,
        context_paths=tuple(dict.fromkeys((*config.context_paths, *paths))),
        context_hashes=tuple(pins.items()),
        checks=tuple(c for c in config.checks if c.id in child.check_ids),
        selected_harness=tuple(p for p in config.selected_harness if p in applicable),
        excluded_harness=tuple((p, r) for p, r in config.excluded_harness if p in applicable))


def child_content(plan_hash: str, child: PlanChild, parent: ExternalIssue,
                  children: dict, requirement_sources: dict | None = None,
                  requirements: tuple = ()) -> tuple[str, str, str]:
    marker_subject = {'plan': plan_hash, 'parent': asdict(parent)}
    if requirement_sources is not None:
        marker_subject['sources_fingerprint'] = requirement_sources['fingerprint']
    marker_scope = fingerprint(marker_subject)
    marker = '<!-- sf-child:' + marker_scope + ':' + child.id + ' -->'
    dependencies = [children[key]['issue']['external_url'] for key in child.depends_on]
    body = marker + '\n\nParent: ' + (parent.external_url or parent.external_id)
    body += '\n\n' + child.goal + '\n\nAcceptance criteria:\n'
    body += '\n'.join('- ' + c for c in child.acceptance)
    body += '\n\nRequirement IDs: ' + ', '.join(child.requirement_ids)
    body += '\nApproved paths: ' + ', '.join(child.allowed_paths)
    body += '\nApproved checks: ' + ', '.join(child.check_ids)
    if requirement_sources is not None:
        cited = sorted({p for r in requirements if r.id in child.requirement_ids
                        for p in r.sources})
        body += '\nRequirement sources: ' + ', '.join(cited)
        body += '\nSource revision: ' + requirement_sources['revision']
        body += '\nSources fingerprint: ' + requirement_sources['fingerprint']
    if dependencies:
        body += '\nDepends on merged PRs for:\n' + '\n'.join('- ' + d for d in dependencies)
    return child.title, body, marker


def advance_requirements(*, factory: Factory, config: DevelopmentConfig,
                         source: TaskSourceAdapter, scm: CollaborationSourceControl,
                         tracker: IssueTracker, implementer: ModelProvider,
                         reviewer: ModelProvider, confirmed: bool, execute: bool = False,
                         trusted_reviewers: tuple[str, ...] = (),
                         limits: AutomationLimits = PLAN_LIMITS) -> dict:
    if not confirmed or config.data_root != factory.root or implementer is reviewer:
        raise StatePermissionDenied(
            'explicit local requirement scope and independent models required')
    session = AutomationSession(factory.root,
        subject='requirements:' + config.repository + ':' + config.issue,
        config_fingerprint=fingerprint({'development': config.fingerprint,
                                       'reviewers': trusted_reviewers}), limits=limits)
    lock = factory.root / 'requirement-controller-v1'
    lock.mkdir(mode=0o700, exist_ok=True)
    with lock_directory(lock):
        state = session.snapshot()
        if state['status'] in {'completed', 'stopped'}:
            return {'session_id': session.id, 'status': state['status'], **state['data']}
        previous = []
        for adapter in (scm, tracker):
            if any(adapter is a for a, _ in previous):
                continue
            if hasattr(adapter, 'request_guard'):
                old = getattr(adapter, 'request_guard')
                previous.append((adapter, old))
                setattr(adapter, 'request_guard', session.api_call)
        class BudgetedSource:
            def fetch_issue(self, external_id):
                session.api_call()
                return source.fetch_issue(external_id)
        try:
            return _advance(factory, config, BudgetedSource(), scm, tracker,
                BudgetedModel(implementer, session, role='workflow-implementation',
                              max_output_tokens=32768),
                BudgetedModel(reviewer, session, role='workflow-review', max_output_tokens=32768),
                session, execute, trusted_reviewers)
        except (RequirementSourceError, RequirementPlanningError) as exc:
            return _save(session, session.snapshot()['data'], exc.code, status='stopped',
                         **getattr(exc, 'facts', {}))
        except Exception as exc:
            current = session.snapshot()
            unknown_model = any(a['kind'] == 'model' and a['status'] == 'pending'
                                for a in current['actions'].values())
            unknown_execution = any(c['status'] == 'executing'
                                    for c in current['data'].get('children', {}).values())
            if (isinstance(exc, SourceControlError) and exc.kind == 'unavailable'
                    and current['status'] not in {'stopped', 'completed'}
                    and not unknown_model and not unknown_execution):
                return _save(session, current['data'], 'remote_read_unavailable')
            if session.snapshot()['status'] not in {'stopped', 'completed'}:
                _save(session, session.snapshot()['data'], 'requirement_advance_stopped',
                      status='stopped', error_type=type(exc).__name__)
            final = session.snapshot()
            return {'session_id': session.id, 'status': final['status'],
                    'reason': 'requirement_advance_stopped', **final['data']}
        finally:
            for adapter, old in previous:
                setattr(adapter, 'request_guard', old)


def _advance(factory, config, source, scm, tracker, implementer, reviewer,
             session, execute, trusted_reviewers):
    data = session.snapshot()['data']
    fresh = not data
    if not data:
        if execute:
            execution_readiness(config)
        parent = source.fetch_issue(config.issue)
        if parent.external_id != config.issue:
            raise StateConflict('different parent Issue returned')
        issue_key = factory.import_issue(**asdict(parent))
        factory.bind_issue_repository(issue_key, config.repository, config.root)
        from sf_factory.remote_harness import verify_remote_harness
        info = scm.describe_repository(config.repository)
        revision = scm.branch_revision(config.repository, info.default_branch)
        remote = scm.read_revision(config.repository, revision)
        verify_remote_harness(config.root, remote)
        if remote.repository != config.repository or remote.revision != revision:
            raise StateConflict('planning source differs from repository revision')
        selected_sources = discover_requirement_sources(remote, explicit=config.context_paths,
            reference_slots=32 - len(config.selected_harness))
        discovered_hashes = {d.path: d.sha256 for d in selected_sources.documents}
        if any(discovered_hashes.get(p) != digest for p, digest in config.context_hashes):
            raise RequirementSourceError('requirements_source_changed', {})
        paths = set((*config.selected_harness, *config.allowed_paths,
                     *(d.path for d in selected_sources.documents)))
        context = {f.path: f.content.decode('utf-8') for f in remote.files if f.path in paths}
        if len(json.dumps(context, ensure_ascii=True)) > 65536:
            raise RequirementSourceError('requirements_context_limit', {
                'source_count': len(selected_sources.documents),
                'sources_fingerprint': selected_sources.fingerprint})
        data = {'parent': asdict(parent), 'phase': 'planning', 'children': {},
                'source_revision': revision, 'source_fingerprint': remote.fingerprint,
                'source_branch': info.default_branch,
                'repository_context': context,
                'requirement_sources': selected_sources.document()}
        _save(session, data, 'planning_scope_frozen', status='ready',
              requirement_mode=selected_sources.mode,
              source_count=len(selected_sources.documents),
              sources_fingerprint=selected_sources.fingerprint)
    parent = ExternalIssue(**data['parent'])
    # An edited requirement cannot silently change the frozen dependency plan.
    if asdict(source.fetch_issue(config.issue)) != data['parent']:
        return _save(session, data, 'parent_requirement_changed', status='stopped')
    if data['phase'] == 'planning':
        sources = data.get('requirement_sources')
        if not fresh and sources is not None:
            revision = scm.branch_revision(config.repository, data['source_branch'])
            if revision != data['source_revision']:
                verify_requirement_sources(sources, scm.read_revision(config.repository, revision))
        # Prompts are deterministic and completed model receipts are reusable.
        # A pending unknown model reservation cannot be replayed by BudgetedModel.
        def record_review(report):
            data['planning_review'] = report
            _save(session, data, 'requirements_interpreted', status='ready',
                  requirement_status=report['report'].get('requirements_status',
                                                         report['report'].get('status')))
        plan = propose_plan(parent.prompt, config, implementer, reviewer,
                            max_children=session.snapshot()['limits']['max_children'],
                            repository_context=data['repository_context'],
                            requirement_sources=data.get('requirement_sources'),
                            on_review=record_review)
        data.update(plan=asdict(plan), plan_fingerprint=plan.fingerprint, phase='children')
        _save(session, data, 'plan_independently_reviewed', status='ready',
              plan_fingerprint=plan.fingerprint, children=len(plan.children))
    sources = data.get('requirement_sources')
    source_ids = ('issue', *(d['path'] for d in sources['documents'])) if sources else None
    plan = parse_plan(json.dumps(data['plan']), config,
        max_children=session.snapshot()['limits']['max_children'], source_ids=source_ids)
    if plan.fingerprint != data['plan_fingerprint']:
        raise StateConflict('stored dependency plan changed')
    # At most max_children iterations; topological order for external Issue links.
    for _ in range(len(plan.children)):
        remaining = [c for c in plan.children if c.id not in data['children']]
        if not remaining:
            break
        child = next(c for c in remaining if set(c.depends_on) <= set(data['children']))
        title, body, marker = child_content(plan.fingerprint, child, parent, data['children'],
                                            sources, plan.requirements)
        key = 'issue:' + child.id
        action = session.snapshot()['actions'].get(key)
        found = tracker.find_issue(config.repository, marker)
        if found is None:
            if action is not None:
                return _save(session, data, 'child_create_unresolved', child=child.id)
            session.reserve('write', key)
            try:
                found = tracker.create_issue(config.repository, title=title, body=body)
            except Exception:
                return _save(session, data, 'child_create_unresolved', child=child.id)
        if (action is not None and action['status'] == 'completed'
                and action['receipt'] != asdict(found)):
            raise StateConflict('child identity differs from durable creation receipt')
        if (found.prompt != title + '\n\n' + body or found.instance != parent.instance
                or found.provider != parent.provider):
            raise StateConflict('existing child content/provider differs from reviewed plan')
        if action is None and key not in session.snapshot()['actions']:
            session.reserve('write', key)  # Adopt exact existing content, no external write.
        if session.snapshot()['actions'][key]['status'] == 'pending':
            session.complete_action(key, asdict(found))
        link = 'link:' + child.id
        linked = tracker.child_issues(config.repository, config.issue)
        if found.external_id not in {i.external_id for i in linked}:
            if link in session.snapshot()['actions']:
                return _save(session, data, 'child_link_unresolved', child=child.id)
            session.reserve('write', link)
            try:
                tracker.attach_child(config.repository, config.issue, found.external_id)
            except Exception:
                return _save(session, data, 'child_link_unresolved', child=child.id)
            linked = tracker.child_issues(config.repository, config.issue)
            if found.external_id not in {i.external_id for i in linked}:
                return _save(session, data, 'child_link_unresolved', child=child.id)
        if link not in session.snapshot()['actions']:
            session.reserve('write', link)
        if session.snapshot()['actions'][link]['status'] == 'pending':
            session.complete_action(link, {'parent': config.issue, 'child': found.external_id})
        data['children'][child.id] = {'issue': asdict(found), 'status': 'pending'}
        _save(session, data, 'external_child_linked', status='ready', child=child.id,
              external_id=found.external_id)
    data['phase'] = 'executing'
    if not execute:
        return _save(session, data, 'plan_ready')
    active = next((c for c in plan.children
                   if data['children'][c.id]['status'] not in {'pending', 'merged'}), None)
    if active is not None:
        item = data['children'][active.id]
        current_issue = source.fetch_issue(item['issue']['external_id'])
        if asdict(current_issue) != item['issue']:
            return _save(session, data, 'child_requirement_changed', status='stopped')
        if current_issue.external_id not in {i.external_id for i in
                tracker.child_issues(config.repository, config.issue)}:
            return _save(session, data, 'child_parent_link_changed', status='stopped')
        scoped = child_scope(config, active, item['issue']['external_id'], sources)
        if item['status'] == 'executing':
            return _save(session, data, 'child_execution_outcome_unknown', status='stopped')
        if item['status'] == 'delivery_pending':
            # Existing controller's read-only delivery reconciliation; never a second inference.
            result = develop_issue(factory=factory, config=scoped, source=source, scm=scm,
                implementer=implementer, reviewer=reviewer, confirmed=True, resume=item['run_id'])
            item.update(status='pr_open', pull_request=result['pull_request'])
            session.complete_action('delivery:' + active.id, result)
            session.complete_action('develop:' + active.id, {'run_id': item['run_id']})
            return _save(session, data, 'child_delivery_reconciled')
        result = advance_review(factory=factory, config=scoped, source=source, scm=scm,
            implementer=implementer, reviewer=reviewer, initial_run=item['run_id'],
            confirmed=True, trusted_reviewers=trusted_reviewers)
        if result['status'] == 'stopped':
            return _save(session, data, 'child_review_stopped', status='stopped',
                         child=active.id, review_session=result['session_id'])
        if result['status'] != 'completed':
            return _save(session, data, 'child_awaiting_review_or_merge', child=active.id,
                         review_session=result['session_id'])
        item.update(status='merged', merged_head=result['head'])
        return _save(session, data, 'child_merge_verified', status='ready', child=active.id)
    if all(i['status'] == 'merged' for i in data['children'].values()):
        return _save(session, data, 'all_child_prs_merged', status='completed')
    done = {key for key, item in data['children'].items() if item['status'] == 'merged'}
    child = next(c for c in plan.children if data['children'][c.id]['status'] == 'pending'
                 and set(c.depends_on) <= done)
    item = data['children'][child.id]
    exact = source.fetch_issue(item['issue']['external_id'])
    if asdict(exact) != item['issue']:
        return _save(session, data, 'child_requirement_changed', status='stopped', child=child.id)
    # Native parent relationship is authoritative at execution time as well.
    linked = tracker.child_issues(config.repository, config.issue)
    if exact.external_id not in {i.external_id for i in linked}:
        return _save(session, data, 'child_parent_link_changed', status='stopped')
    scoped = child_scope(config, child, exact.external_id, sources)
    info = scm.describe_repository(config.repository)
    revision = scm.branch_revision(config.repository, info.default_branch)
    remote = scm.read_revision(config.repository, revision)
    if sources is not None:
        verify_requirement_sources(sources, remote)
    session.reserve('round', 'develop:' + child.id, unit=child.id)
    session.reserve('write', 'delivery:' + child.id)
    item['status'] = 'executing'
    _save(session, data, 'child_execution_reserved', status='ready', child=child.id)
    class FrozenSource:
        def fetch_issue(self, external_id):
            if external_id != exact.external_id:
                raise StateConflict('different frozen Issue requested')
            return exact
    try:
        result = develop_issue(factory=factory, config=scoped, source=FrozenSource(), scm=scm,
            implementer=implementer, reviewer=reviewer, confirmed=True, remote_source=remote)
    except DevelopmentStopped as exc:
        item['run_id'] = exc.run_id
        artifact = _artifact(factory, exc.run_id)
        if artifact['phase'] in {'reviewed', 'delivered'}:
            item['status'] = 'delivery_pending'
            return _save(session, data, 'child_delivery_pending', child=child.id, run_id=exc.run_id)
        item['status'] = 'failed'
        return _save(session, data, 'child_quality_failed', status='stopped',
                     child=child.id, run_id=exc.run_id)
    item.update(status='pr_open', run_id=result['run_id'], pull_request=result['pull_request'])
    session.complete_action('delivery:' + child.id, result)
    session.complete_action('develop:' + child.id, {'run_id': item['run_id']})
    return _save(session, data, 'child_pr_submitted', child=child.id, run_id=result['run_id'])
