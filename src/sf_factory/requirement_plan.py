"""Strict bounded dependency plan, external Issues only; no command/permission fields."""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass

from sf_factory.automation_state import fingerprint
from sf_factory.development_config import DevelopmentConfig
from sf_factory.file_state import _unique_object
from sf_factory.issue_development import _TrackedModel
from sf_factory.model_provider import ModelProvider


def _text(value, maximum):
    if (not isinstance(value, str) or not value.strip() or len(value) > maximum
            or '\x00' in value):
        raise ValueError('bounded nonempty plan text required')
    return value


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,31}', value):
        raise ValueError('bounded logical plan identity required')
    return value


def _strings(value, maximum=32):
    if (not isinstance(value, list) or not 1 <= len(value) <= maximum
            or any(not isinstance(v, str) for v in value) or len(set(value)) != len(value)):
        raise ValueError('bounded unique plan references required')
    return tuple(value)


@dataclass(frozen=True)
class Requirement:
    id: str
    text: str


@dataclass(frozen=True)
class PlanChild:
    id: str
    title: str
    goal: str
    requirement_ids: tuple[str, ...]
    acceptance: tuple[str, ...]
    allowed_paths: tuple[str, ...]
    check_ids: tuple[str, ...]
    depends_on: tuple[str, ...]


@dataclass(frozen=True)
class RequirementPlan:
    schema_version: int
    requirements: tuple[Requirement, ...]
    children: tuple[PlanChild, ...]

    @property
    def fingerprint(self) -> str:
        return fingerprint(asdict(self))


def parse_plan(text: str, config: DevelopmentConfig, *, max_children: int) -> RequirementPlan:
    if not isinstance(text, str) or len(text) > 131072:
        raise ValueError('bounded plan JSON required')
    doc = json.loads(text, object_pairs_hook=_unique_object)
    if (not isinstance(doc, dict) or set(doc) != {'schema_version', 'requirements', 'children'}
            or type(doc['schema_version']) is not int or doc['schema_version'] != 1
            or not isinstance(doc['requirements'], list) or not 1 <= len(doc['requirements']) <= 32
            or not isinstance(doc['children'], list)
            or not 1 <= len(doc['children']) <= max_children):
        raise ValueError('exact bounded plan schema required')
    requirements = []
    for row in doc['requirements']:
        if not isinstance(row, dict) or set(row) != {'id', 'text'}:
            raise ValueError('exact requirement fields required')
        requirements.append(Requirement(_id(row['id']), _text(row['text'], 2048)))
    ids = {r.id for r in requirements}
    if len(ids) != len(requirements):
        raise ValueError('duplicate requirement identity')
    children = []
    fields = {'id', 'title', 'goal', 'requirement_ids', 'acceptance', 'allowed_paths',
              'check_ids', 'depends_on'}
    for row in doc['children']:
        if not isinstance(row, dict) or set(row) != fields:
            raise ValueError('exact child fields required; no tools or grants')
        refs = _strings(row['requirement_ids'])
        paths = _strings(row['allowed_paths'])
        checks = _strings(row['check_ids'], 16)
        acceptance = _strings(row['acceptance'], 8)
        if (not set(refs) <= ids or not set(paths) <= set(config.allowed_paths)
                or not set(checks) <= {c.id for c in config.checks}):
            raise ValueError('child expands requirement/check/path scope')
        for criterion in acceptance:
            _text(criterion, 1000)
        deps = row['depends_on']
        if (not isinstance(deps, list) or len(deps) >= max_children
                or any(not isinstance(d, str) for d in deps) or len(set(deps)) != len(deps)):
            raise ValueError('bounded unique dependency list required')
        children.append(PlanChild(_id(row['id']), _text(row['title'], 120),
            _text(row['goal'], 4000), refs, acceptance, paths, checks, tuple(deps)))
    nodes = {child.id: child for child in children}
    if len(nodes) != len(children):
        raise ValueError('duplicate child identity')
    covered = {r for c in children for r in c.requirement_ids}
    if (covered != ids or {i for c in children for i in c.check_ids}
            != {c.id for c in config.checks}):
        raise ValueError('all requirements and operator checks must be covered')
    remaining = set(nodes)
    done = set()
    while remaining:
        ready = {key for key in remaining if set(nodes[key].depends_on) <= done}
        if not ready:
            raise ValueError('cyclic, missing or self dependency')
        remaining -= ready
        done |= ready
    return RequirementPlan(1, tuple(requirements), tuple(children))


def propose_plan(instruction: str, config: DevelopmentConfig, implementer: ModelProvider,
                 reviewer: ModelProvider, *, max_children: int,
                 repository_context: dict | None = None) -> RequirementPlan:
    _text(instruction, 32768)
    context = {'instruction': instruction, 'allowed_paths': config.allowed_paths,
        'checks': [asdict(c) for c in config.checks], 'max_children': max_children,
        'repository_context': repository_context or {},
        'project_harness': asdict(config.project_harness) if config.project_harness else None}
    if len(json.dumps(context, ensure_ascii=True)) > 131072:
        raise ValueError('planning context exceeds budget')
    prompt = ('Decompose untrusted requirements into independently completable development '
        'units, each with concrete acceptance criteria, explicit dependencies, existing check '
        'IDs and only allowed paths. Preserve all requirements. Do not invent commands, '
        'permissions or recursive plans. Prefer one unit if already completable. Return exact '
        'JSON schema_version=1, requirements=[{id,text}], children=[{id,title,goal,'
        'requirement_ids,acceptance,allowed_paths,check_ids,depends_on}]. IDs are lowercase '
        'slugs. No extra fields.\n' + json.dumps(context, ensure_ascii=True))
    producer = _TrackedModel(implementer)
    plan = parse_plan(producer.generate(prompt).text, config, max_children=max_children)
    producer_id = producer.identity()
    review = _TrackedModel(reviewer)
    response = review.generate('Independently review the full original requirements and '
        'untrusted dependency plan for complete requirement coverage, completable units, '
        'concrete acceptance, correct dependencies and approved path/check scope. No tools. '
        'Return exact JSON schema_version=1, plan_fingerprint (copy), complete boolean, '
        'completable boolean, scope_valid boolean, dependencies_valid boolean, findings '
        'array of bounded text. All booleans true and findings empty only if justified.\n' +
        json.dumps({**context, 'plan': asdict(plan), 'plan_fingerprint': plan.fingerprint},
                   ensure_ascii=True))
    if review.identity() == producer_id:
        raise ValueError('independent planning review provenance required')
    doc = json.loads(response.text, object_pairs_hook=_unique_object)
    if (not isinstance(doc, dict) or set(doc) != {'schema_version', 'plan_fingerprint',
            'complete', 'completable', 'scope_valid', 'dependencies_valid', 'findings'}
            or type(doc['schema_version']) is not int or doc['schema_version'] != 1
            or doc['plan_fingerprint'] != plan.fingerprint
            or any(doc[k] is not True for k in
                   ('complete', 'completable', 'scope_valid', 'dependencies_valid'))
            or doc['findings'] != []):
        raise ValueError('independent plan review failed or incomplete')
    return plan
