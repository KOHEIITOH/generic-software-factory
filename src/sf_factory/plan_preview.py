"""Canonical human approval scope and an operator-only derived plan presentation."""
from sf_factory.automation_state import fingerprint


def approval_fingerprint(state: dict) -> str:
    data = state['data']
    return fingerprint({'plan': data['plan'], 'plan_fingerprint': data['plan_fingerprint'],
        'parent': data['parent'], 'configuration': state['config'],
        'sources': data.get('requirement_sources'),
        'source_fingerprint': data['source_fingerprint'],
        'planning_review': data.get('planning_review'),
        'source_revision': data['source_revision'], 'local_revision': data.get('local_revision')})


def plan_preview(state: dict) -> dict | None:
    data = state['data']
    if 'plan' not in data or not data.get('require_plan_approval'):
        return None
    approval = data.get('plan_approval')
    if approval is None:
        return None
    return {'plan': data['plan'], 'plan_fingerprint': data['plan_fingerprint'],
        'interpretation': data.get('planning_review', {}).get('report', {}).get(
            'interpretation', ''),
        'approval_required': data.get('require_plan_approval', False),
        'approval_status': approval['status'],
        'approval_fingerprint': approval_fingerprint(state)}
