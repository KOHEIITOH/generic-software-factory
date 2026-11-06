"""Reject ambiguous or malformed check outcomes before persistence."""
from dataclasses import replace

import pytest

from sf_factory.run_evidence import CheckObservation, CheckRequirement, EvidenceSubject


@pytest.mark.parametrize('change', [
    {'exit_code': True}, {'exit_code': 1}, {'tests_run': True}, {'tests_run': -1},
    {'run_id': 'wrong'}, {'status': 'passed'}, {'report_sha256': 'missing'}, {'check_id': ''},
    {'status': 'skipped', 'exit_code': 0}, {'status': 'failed', 'exit_code': 0},
])
def test_invalid_check_outcome_is_rejected(change):
    observation = CheckObservation('unit', 'completed', 0, 'a' * 64, 2, run_id='a' * 32)
    with pytest.raises(ValueError):
        replace(observation, **change)


def test_unpinned_subject_and_unknown_check_kind_are_rejected():
    with pytest.raises(ValueError):
        EvidenceSubject('main', 'a' * 64, 'b' * 64)
    with pytest.raises(ValueError):
        CheckRequirement('unit', 'agent-says-ok')
