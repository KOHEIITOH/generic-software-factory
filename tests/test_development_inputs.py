"""Only observed behavioral checks and isolated model sessions become facts."""
from dataclasses import replace

import pytest
from test_workspace_check import fixture_data

from sf_factory.behavioral_check import BehavioralCheck, collect_behavioral_check
from sf_factory.copilot_model_provider import CopilotModelProvider
from sf_factory.runtime import RuntimeResult
from sf_factory.workspace_check import WorkspaceCheckResult


def test_text_provider_has_empty_workspace_and_returns_observed_session(monkeypatch):
    roots = []
    def execute(self, *, prompt, workspace, timeout_seconds):
        assert list(workspace.iterdir()) == []
        roots.append(workspace)
        return RuntimeResult('copilot', 'succeeded', 'fixture text', 0, session_id='actual-session')
    monkeypatch.setattr('sf_factory.copilot_model_provider.CopilotSdkRuntime.execute', execute)
    response = CopilotModelProvider().generate('approved prompt')
    assert response.text == 'fixture text'
    assert response.session_id == 'actual-session'
    assert all(not root.exists() for root in roots)


@pytest.mark.parametrize('result', [
    RuntimeResult('copilot', 'failed', 'untrusted error output', 1, error_kind='authentication'),
    RuntimeResult('copilot', 'succeeded', 'text', 0),
    RuntimeResult('copilot', 'succeeded', '', 0, session_id='session'),
])
def test_missing_session_or_failed_inference_is_not_model_success(monkeypatch, result):
    monkeypatch.setattr('sf_factory.copilot_model_provider.CopilotSdkRuntime.execute',
                        lambda *a, **kw: result)
    with pytest.raises(RuntimeError):
        CopilotModelProvider().generate('approved prompt')


def test_behavioral_scenario_requires_actual_success_and_exact_output(monkeypatch):
    files, scope, proposal = fixture_data()
    observed = WorkspaceCheckResult('succeeded', 0, '5\n', 'a' * 64,
                                    proposal.fingerprint, True, True)
    monkeypatch.setattr('sf_factory.behavioral_check.run_candidate_check', lambda **kw: observed)
    observation = collect_behavioral_check(check=BehavioralCheck('addition', ('python',), '5\n'),
        image='fixture', scope=scope, proposal=proposal, source_files=files)
    assert observation.tests_run == 1
    assert observation.status == 'completed'
    assert observation.run_id == scope.run_id


@pytest.mark.parametrize('changes,status', [({'output': 'not the expected result'}, 'failed'),
    ({'output': 'Ran 100 tests OK'}, 'failed'), ({'status': 'unavailable'}, 'error'),
    ({'status': 'timed_out', 'exit_code': None}, 'error'),
    ({'source_unchanged': False}, 'error'), ({'cleaned_up': False}, 'error'),
    ({'proposal_fingerprint': 'f' * 64}, 'error')])
def test_claimed_counts_timeout_or_tampering_never_pass(monkeypatch, changes, status):
    files, scope, proposal = fixture_data()
    observed = WorkspaceCheckResult('succeeded', 0, '5\n', 'a' * 64,
                                    proposal.fingerprint, True, True)
    monkeypatch.setattr('sf_factory.behavioral_check.run_candidate_check',
                        lambda **kw: replace(observed, **changes))
    result = collect_behavioral_check(check=BehavioralCheck('addition', ('python',), '5\n'),
        image='fixture', scope=scope, proposal=proposal, source_files=files)
    assert result.status == status
    assert result.tests_run is None if status == 'error' else result.tests_run == 1
