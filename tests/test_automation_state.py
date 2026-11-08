"""Budgets, crash reservations and terminal decisions persist across invocations."""
from datetime import UTC, datetime, timedelta

import pytest

from sf_factory.automation_state import AutomationLimits, AutomationSession, AutomationStopped
from sf_factory.state_store import StateConflict, StateCorrupt


def session(root, **kwargs):
    return AutomationSession(root, subject='review:fixture/repo#1', config_fingerprint='a' * 64,
                             **kwargs)


def test_resume_does_not_reset_budget_or_unknown_action(tmp_path):
    limits = AutomationLimits(max_model_calls=1)
    first = session(tmp_path, limits=limits)
    first.reserve('model', 'implementation', tokens=30)
    restored = session(tmp_path, limits=limits)
    with pytest.raises(StateConflict, match='already reserved'):
        restored.reserve('model', 'implementation')
    with pytest.raises(AutomationStopped):
        restored.reserve('model', 'review')
    final = session(tmp_path, limits=limits).snapshot()
    assert final['counts']['model'] == 1
    assert final['actions']['implementation']['status'] == 'pending'
    assert final['status'] == 'stopped'
    assert final['decisions'][-1]['code'] == 'budget_exhausted'


@pytest.mark.parametrize('field', ['max_rounds', 'max_model_calls', 'max_tokens',
                                  'max_api_calls', 'max_writes', 'max_seconds', 'max_children'])
@pytest.mark.parametrize('value', [True, 0, -1, 10000001])
def test_limits_reject_unbounded_or_ambiguous_configuration(field, value):
    with pytest.raises(ValueError):
        AutomationLimits(**{field: value})


def test_round_budget_is_per_unit_and_persists(tmp_path):
    state = session(tmp_path, limits=AutomationLimits(max_rounds=1))
    state.reserve('round', 'child1-round1', unit='child1')
    state.reserve('round', 'child2-round1', unit='child2')
    with pytest.raises(AutomationStopped):
        state.reserve('round', 'child1-round2', unit='child1')
    assert state.snapshot()['rounds'] == {'child1': 1, 'child2': 1}


def test_repeated_candidate_stops_and_records_evidence(tmp_path):
    state = session(tmp_path)
    state.remember_candidate('pr1', 'b' * 64)
    with pytest.raises(AutomationStopped):
        state.remember_candidate('pr1', 'b' * 64)
    assert state.snapshot()['decisions'][-1]['code'] == 'candidate_repeated'


def test_deadline_and_api_budget_survive_reopening(tmp_path):
    now = datetime.now(UTC)
    state = session(tmp_path, limits=AutomationLimits(max_seconds=1), clock=lambda: now)
    again = session(tmp_path, limits=AutomationLimits(max_seconds=1),
                    clock=lambda: now + timedelta(seconds=2))
    with pytest.raises(AutomationStopped):
        again.api_call()
    assert state.snapshot()['decisions'][-1]['code'] == 'deadline_exhausted'


def test_terminal_state_and_cas_do_not_restart(tmp_path):
    state = session(tmp_path)
    before = state.snapshot()
    state.save({'waiting_for': 'human_review'}, expected_version=before['version'],
               status='waiting')
    with pytest.raises(StateConflict):
        state.save({}, expected_version=before['version'])
    state.save({}, expected_version=state.snapshot()['version'], status='completed')
    with pytest.raises(AutomationStopped):
        state.api_call()
    assert session(tmp_path).snapshot()['status'] == 'completed'


def test_missing_state_never_initializes_over_existing_intent(tmp_path):
    state = session(tmp_path)
    (state.directory / 'state.json').unlink()
    with pytest.raises(StateCorrupt):
        session(tmp_path)


def test_write_receipt_is_single_use(tmp_path):
    state = session(tmp_path)
    state.reserve('write', 'publish-child')
    state.complete_action('publish-child', {'external_id': '2'})
    with pytest.raises(StateConflict):
        state.complete_action('publish-child', {'external_id': '3'})
    assert state.snapshot()['actions']['publish-child']['receipt'] == {'external_id': '2'}


def test_token_and_api_budgets_are_enforced_before_calls(tmp_path):
    state = session(tmp_path, limits=AutomationLimits(max_tokens=2, max_api_calls=1))
    with pytest.raises(AutomationStopped):
        state.reserve('model', 'too-large', tokens=3)
    assert state.snapshot()['counts']['model'] == 0
    other = AutomationSession(tmp_path, subject='other', config_fingerprint='a' * 64,
                              limits=AutomationLimits(max_api_calls=1))
    other.api_call()
    with pytest.raises(AutomationStopped):
        other.api_call()
    assert other.snapshot()['counts']['api'] == 1


def test_exact_inference_receipt_is_cached_without_second_provider_call(tmp_path):
    from sf_factory.budgeted_model import BudgetedModel
    from sf_factory.model_provider import ModelResponse
    class Provider:
        calls = 0
        def generate(self, prompt):
            self.calls += 1
            return ModelResponse('fixture', 'model', 'result', session_id='actual-session')
    provider = Provider()
    state = session(tmp_path)
    model = BudgetedModel(provider, state, role='planner')
    first = model.generate('exact prompt')
    restored = BudgetedModel(provider, session(tmp_path), role='planner')
    assert restored.generate('exact prompt') == first
    assert provider.calls == 1


def test_failed_inference_keeps_reserved_budget_and_never_replays(tmp_path):
    from sf_factory.budgeted_model import BudgetedModel
    class Provider:
        calls = 0
        def generate(self, prompt):
            self.calls += 1
            raise TimeoutError('outcome unknown')
    provider = Provider()
    model = BudgetedModel(provider, session(tmp_path), role='planner')
    with pytest.raises(TimeoutError):
        model.generate('exact prompt')
    with pytest.raises(StateConflict):
        model.generate('exact prompt')
    assert provider.calls == 1
