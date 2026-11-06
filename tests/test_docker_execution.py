"""Offline executor tests; real isolation checks are opt-in and separately recorded."""
import os
import subprocess

import pytest

from sf_factory.docker_execution import _docker, run_offline_command

IMAGE = os.environ.get('SF_TEST_DOCKER_IMAGE', '')


@pytest.mark.parametrize('kwargs', [
    {'image': 'python:latest'}, {'argv': ()}, {'argv': ('-bad',)},
    {'argv': ('python', '\x00')}, {'timeout_seconds': 0}, {'max_output_bytes': 0},
])
def test_invalid_requests_never_call_docker(monkeypatch, kwargs):
    def forbidden(*args, **kw):
        raise AssertionError('must not invoke Docker')
    monkeypatch.setattr('sf_factory.docker_execution._docker', forbidden)
    arguments = {'image': 'python@sha256:' + 'a' * 64, 'argv': ('python',)} | kwargs
    with pytest.raises(ValueError):
        run_offline_command(**arguments)


def test_inspect_mismatch_never_starts_container(monkeypatch):
    calls = []

    def fake(args, **kwargs):
        calls.append(args)
        if args[0] == 'inspect':
            return subprocess.CompletedProcess([], 0, '[{}]', '')
        return subprocess.CompletedProcess([], 0, '', '')

    monkeypatch.setattr('sf_factory.docker_execution._docker', fake)
    result = run_offline_command(image='python@sha256:' + 'a' * 64, argv=('python',))
    assert result.status == 'failed'
    assert result.cleaned_up
    assert [c[0] for c in calls] == ['create', 'inspect', 'rm']


real_docker = pytest.mark.skipif(not IMAGE, reason='requires explicit SF_TEST_DOCKER_IMAGE digest')


@real_docker
def test_real_offline_filesystem_and_identity():
    code = '''
import os, socket
from pathlib import Path
assert os.getuid() == 65534
assert not Path('/var/run/docker.sock').exists()
assert not Path('/workspace/.git').exists()
assert not Path('/workspace/generic-software-factory').exists()
assert not os.environ.get('SF_HOST_CANARY')
assert all(not os.environ.get(k) for k in ('HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy'))
Path('/workspace/calculator.py').write_text('def add(a,b): return a+b')
namespace = {}
exec(Path('/workspace/calculator.py').read_text(), namespace)
assert namespace['add'](2,3) == 5
try:
    Path('/etc/sf-must-not-write').write_text('bad')
except OSError:
    pass
else:
    raise AssertionError('rootfs writable')
try:
    os.setuid(0)
except PermissionError:
    pass
else:
    raise AssertionError('could become root')
s = socket.socket()
s.settimeout(1)
try:
    s.connect(('1.1.1.1',443))
except OSError:
    pass
else:
    raise AssertionError('network reachable')
print('isolation checks passed')
'''
    result = run_offline_command(image=IMAGE, argv=('python', '-c', code))
    assert result.status == 'succeeded', result
    assert result.exit_code == 0
    assert result.cleaned_up
    assert 'isolation checks passed' in result.output


@real_docker
def test_real_timeout_cleans_child_processes():
    result = run_offline_command(
        image=IMAGE,
        argv=('python', '-c', 'import subprocess,time; subprocess.Popen(["sleep","30"]);'
              'time.sleep(30)'), timeout_seconds=1,
    )
    assert result.status == 'timed_out', result
    assert result.cleaned_up
    remaining = _docker(['ps', '-aq', '--filter', 'label=sf.execution=offline-v1'])
    assert remaining.returncode == 0
    assert not remaining.stdout.strip()


@real_docker
def test_real_output_limit_is_enforced():
    result = run_offline_command(
        image=IMAGE, argv=('python', '-c', 'print("x"*1000000)'), max_output_bytes=128,
    )
    assert result.status == 'output_limit', result
    assert len(result.output) <= 128
    assert result.cleaned_up


def test_cleanup_failure_cannot_be_success(monkeypatch):
    def fake(args, **kwargs):
        if args[0] == 'rm':
            return subprocess.CompletedProcess([], 1, '', 'unavailable')
        return subprocess.CompletedProcess([], 0, '[{}]', '')

    monkeypatch.setattr('sf_factory.docker_execution._docker', fake)
    result = run_offline_command(image='python@sha256:' + 'a' * 64, argv=('python',))
    assert result.status == 'cleanup_failed'
    assert not result.cleaned_up


@real_docker
def test_real_command_failure_is_preserved():
    result = run_offline_command(image=IMAGE, argv=('python', '-c', 'raise SystemExit(7)'))
    assert result.status == 'failed'
    assert result.exit_code == 7
    assert result.cleaned_up
