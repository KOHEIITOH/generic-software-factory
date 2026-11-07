"""Candidate bytes reach an offline Worker; host code is never executed as fallback."""
import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

from sf_factory.change_proposal import ProposalScope, parse_change_proposal
from sf_factory.docker_execution import DockerExecutionResult, resource_limits_available
from sf_factory.workspace_check import run_candidate_check

IMAGE = os.environ.get('SF_TEST_DOCKER_IMAGE', '')
real_docker = pytest.mark.skipif(not IMAGE, reason='requires explicit SF_TEST_DOCKER_IMAGE digest')


def fixture_data(*, correct=True):
    root = Path(__file__).resolve().parents[1] / 'fixtures/calculator'
    files = {name: (root / name).read_bytes() for name in ('calculator.py', 'test_calculator.py')}
    scope = ProposalScope('a' * 32, 'b' * 40, 'c' * 64, 'd' * 64, ('calculator.py',))
    proposal = parse_change_proposal(json.dumps({
        'schema_version': 1, 'run_id': scope.run_id, 'revision': scope.revision,
        'bundle_hash': scope.bundle_hash, 'source_fingerprint': scope.source_fingerprint,
        'changes': [{'path': 'calculator.py',
                     'before_sha256': hashlib.sha256(files['calculator.py']).hexdigest(),
                     'content': 'def add(a,b): return a+b\n' if correct
                                else 'def add(a,b): return a-b\n'}],
    }), scope=scope, source_files=files)
    return files, scope, proposal


def check(*, image=None, argv=('python', '-m', 'unittest', 'discover', '-s', '.'), **extra):
    files, scope, proposal = fixture_data()
    return run_candidate_check(image=image or 'python@sha256:' + 'a' * 64, scope=scope,
        proposal=proposal, source_files=files, argv=argv, **extra)


def fake_report(**changes):
    def run(**kwargs):
        report = {'schema_version': 1,
            'request_sha256': hashlib.sha256(kwargs['input_bytes']).hexdigest(),
            'status': 'succeeded', 'exit_code': 0, 'source_unchanged': True, 'output': 'fixture',
            **changes}
        return DockerExecutionResult('succeeded', 0, json.dumps(report), kwargs['image'], True)
    return run


def test_candidate_is_data_on_stdin_and_verified_report_is_bound(monkeypatch):
    seen = []
    generate = fake_report()
    def run(**kwargs):
        seen.append(kwargs)
        return generate(**kwargs)
    monkeypatch.setattr('sf_factory.workspace_check.run_offline_command', run)
    result = check()
    assert result.status == 'succeeded'
    assert result.source_unchanged and result.cleaned_up
    request = json.loads(seen[0]['input_bytes'])
    assert request['subject']['run_id'] == 'a' * 32
    assert request['subject']['proposal_fingerprint'] == result.proposal_fingerprint
    assert seen[0]['argv'][:3] == ('python', '-I', '-c')
    assert '/workspace/generic-software-factory' not in seen[0]['input_bytes'].decode()


@pytest.mark.parametrize('changes', [{'request_sha256': 'f' * 64}, {'exit_code': 1},
    {'source_unchanged': False}, {'schema_version': True}, {'command': 'unexpected'},
    {'output': 'x' * 100000}])
def test_wrong_subject_outcome_or_unbounded_report_is_not_success(monkeypatch, changes):
    monkeypatch.setattr('sf_factory.workspace_check.run_offline_command', fake_report(**changes))
    assert check().status == 'protocol_error'


def test_cleanup_and_transport_failure_cannot_be_success(monkeypatch):
    for outcome in (DockerExecutionResult('succeeded', 0, '', 'fixture', False),
                    DockerExecutionResult('unavailable', None, '', 'fixture', True),
                    DockerExecutionResult('succeeded', None, '', 'fixture', True)):
        monkeypatch.setattr('sf_factory.workspace_check.run_offline_command',
                            lambda **kw: outcome)
        assert check().status != 'succeeded'


def test_stale_proposal_never_starts_executor(monkeypatch):
    def forbidden(**kwargs):
        pytest.fail('invalid scope must not call executor')
    monkeypatch.setattr('sf_factory.workspace_check.run_offline_command', forbidden)
    files, scope, proposal = fixture_data()
    with pytest.raises(ValueError, match='subject'):
        run_candidate_check(image='unused', scope=replace(scope, run_id='f' * 32),
            proposal=proposal, source_files=files, argv=('python',))


def test_unsupported_local_daemon_has_no_host_fallback(monkeypatch):
    monkeypatch.setattr('sf_factory.docker_execution.resource_limits_available', lambda: False)
    result = check()
    assert result.status == 'unavailable'
    assert result.output == ''


def resources():
    if not resource_limits_available():
        pytest.skip('resource limits unavailable; not isolation proof')


@real_docker
def test_real_candidate_runs_approved_fixture_tests():
    resources()
    result = check(image=IMAGE)
    assert result.status == 'succeeded', result
    assert result.exit_code == 0
    assert 'Ran 2 tests' in result.output and 'OK' in result.output
    assert result.source_unchanged and result.cleaned_up


@real_docker
def test_real_candidate_failure_preserves_actual_test_failure():
    resources()
    files, scope, proposal = fixture_data(correct=False)
    result = run_candidate_check(image=IMAGE, scope=scope, proposal=proposal, source_files=files,
        argv=('python', '-m', 'unittest', 'discover', '-s', '.'))
    assert result.status == 'failed', result
    assert result.exit_code == 1
    assert 'FAILED' in result.output
    assert result.source_unchanged and result.cleaned_up


@real_docker
def test_real_candidate_source_mutation_is_rejected():
    resources()
    result = check(image=IMAGE, argv=('python', '-c',
        "from pathlib import Path; Path('calculator.py').write_text('changed')"))
    assert result.status == 'tampered', result
    assert not result.source_unchanged
    assert result.cleaned_up


@real_docker
def test_real_candidate_timeout_is_reaped():
    resources()
    result = check(image=IMAGE, argv=('python', '-c', 'import time; time.sleep(120)'),
                   timeout_seconds=1)
    assert result.status == 'timed_out', result
    assert result.cleaned_up


def test_each_check_has_an_unpredictable_request_binding(monkeypatch):
    requests = []
    generate = fake_report()
    def execute(**kwargs):
        requests.append(json.loads(kwargs['input_bytes']))
        return generate(**kwargs)
    monkeypatch.setattr('sf_factory.workspace_check.run_offline_command', execute)
    first, second = check(), check()
    assert len(requests[0]['challenge']) == 64
    assert requests[0]['challenge'] != requests[1]['challenge']
    assert first.request_sha256 != second.request_sha256


@real_docker
def test_real_parent_process_provenance_is_private():
    resources()
    files, scope, proposal = fixture_data()
    script = '''import os
parent = os.getppid()
for name in ('mem','fd/0'):
    try:
        fd = os.open('/proc/'+str(parent)+'/'+name,os.O_RDONLY|os.O_NONBLOCK)
    except PermissionError:
        print('protected')
    else:
        os.close(fd)
        print('UNPROTECTED')
'''
    result = run_candidate_check(image=IMAGE, scope=scope, proposal=proposal, source_files=files,
                                 argv=('python', '-c', script))
    assert result.status == 'succeeded'
    assert result.output == 'protected\nprotected\n'
    assert result.cleaned_up and result.source_unchanged
