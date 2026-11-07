"""Run validated candidate bytes in verified offline Docker, never on the host."""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
from collections.abc import Mapping
from dataclasses import dataclass

from sf_factory.change_proposal import ChangeProposal, ProposalScope, candidate_files
from sf_factory.docker_execution import run_offline_command
from sf_factory.run_review import _unique

# This program is trusted controller code passed as argv, not generated code.
# Isolated Python (-I) never imports the repository into this parent process.
_WORKER = r'''
import base64, ctypes, hashlib, json, os, selectors, signal, stat, subprocess, sys, time
from pathlib import Path, PurePosixPath
# Same-UID candidate code must not read/alter this collector via /proc or ptrace.
libc = ctypes.CDLL(None, use_errno=True)
if libc.prctl(4, 0, 0, 0, 0) != 0 or libc.prctl(3, 0, 0, 0, 0) != 0:
    raise ValueError('private collector process required')
raw = sys.stdin.buffer.read(16777217)
if len(raw) > 16777216:
    raise ValueError('input limit')
data = json.loads(raw)
if (set(data) != {'schema_version','challenge','subject','files','argv',
                 'timeout_seconds','output_limit'}
        or type(data['schema_version']) is not int or data['schema_version'] != 1):
    raise ValueError('input schema')
root = Path('/workspace')
if Path.cwd() != root or any(root.iterdir()):
    raise ValueError('fresh workspace required')
expected, total = {}, 0
for item in data['files']:
    if set(item) != {'path','sha256','content'}:
        raise ValueError('source schema')
    path = PurePosixPath(item['path'])
    if (not path.parts or path.is_absolute() or path.as_posix() != item['path']
            or '..' in path.parts or chr(92) in item['path'] or chr(0) in item['path']
            or len(path.parts) > 16 or item['path'] in expected):
        raise ValueError('source path')
    body = base64.b64decode(item['content'], validate=True)
    total += len(body)
    if (len(body) > 1048576 or total > 8388608 or len(expected) >= 1000
            or hashlib.sha256(body).hexdigest() != item['sha256']):
        raise ValueError('source budget/hash')
    destination = root.joinpath(*path.parts)
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with destination.open('xb') as stream:
        stream.write(body)
    destination.chmod(0o600)
    expected[item['path']] = item['sha256']
argv = data['argv']
if (not isinstance(argv,list) or not argv or len(argv) > 128
        or any(not isinstance(a,str) or chr(0) in a or len(a) > 65536 for a in argv)
        or not argv[0] or argv[0].startswith('-')):
    raise ValueError('command schema')
if (type(data['timeout_seconds']) is not int or not 1 <= data['timeout_seconds'] <= 55
        or type(data['output_limit']) is not int or not 1 <= data['output_limit'] <= 32768):
    raise ValueError('command budget')
env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
p = subprocess.Popen(argv, cwd=root, env=env, stdin=subprocess.DEVNULL,
                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
output, outcome = bytearray(), 'failed'
try:
    deadline = time.monotonic() + data['timeout_seconds']
    with selectors.DefaultSelector() as selector:
        selector.register(p.stdout, selectors.EVENT_READ)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                outcome = 'timed_out'
                break
            if not selector.select(min(remaining,.1)):
                continue
            chunk = os.read(p.stdout.fileno(),8192)
            if not chunk:
                p.wait(timeout=max(.01,deadline-time.monotonic()))
                outcome = 'succeeded' if p.returncode == 0 else 'failed'
                break
            available = data['output_limit'] - len(output)
            output.extend(chunk[:available])
            if len(chunk) > available:
                outcome = 'output_limit'
                break
finally:
    try:
        os.killpg(p.pid,signal.SIGKILL)
    except ProcessLookupError:
        pass
    p.wait()
    p.stdout.close()
actual, integrity = {}, True
try:
    for path in root.rglob('*'):
        if path.is_symlink():
            raise ValueError('symlink after check')
        if path.is_file():
            fd = os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
            with os.fdopen(fd,'rb') as stream:
                meta = os.fstat(stream.fileno())
                if not stat.S_ISREG(meta.st_mode) or meta.st_size > 1048576:
                    raise ValueError('source after check')
                digest = hashlib.sha256(stream.read(1048577)).hexdigest()
                actual[path.relative_to(root).as_posix()] = digest
        elif not path.is_dir():
            raise ValueError('special file after check')
    integrity = actual == expected
except (OSError,ValueError):
    integrity = False
if not integrity:
    outcome = 'tampered'
code = p.returncode
if code is not None and code < 0:
    code = 128 - code
print(json.dumps({'schema_version':1,'request_sha256':hashlib.sha256(raw).hexdigest(),
                  'status':outcome,'exit_code':code,'source_unchanged':integrity,
                  'output':output.decode('utf-8',errors='replace')}))
'''


@dataclass(frozen=True)
class WorkspaceCheckResult:
    status: str
    exit_code: int | None
    output: str
    request_sha256: str
    proposal_fingerprint: str
    cleaned_up: bool
    source_unchanged: bool
    reason: str = ''


def run_candidate_check(
    *, image: str, scope: ProposalScope, proposal: ChangeProposal,
    source_files: Mapping[str, bytes], argv: tuple[str, ...], timeout_seconds: int = 30,
    max_output_bytes: int = 16384,
) -> WorkspaceCheckResult:
    """Trusted approved controller only. Exit zero is not a quality/delivery grant.

    Test commands must come from the approved controller plan, never model output.
    The caller must bind real test counts/reports, independent review and approval.
    """
    files = candidate_files(proposal, scope=scope, source_files=source_files)
    if (not isinstance(argv, tuple) or not argv or len(argv) > 128
            or any(not isinstance(a, str) or '\x00' in a or len(a) > 65536 for a in argv)
            or not argv[0] or argv[0].startswith('-')):
        raise ValueError('explicit approved command argv required')
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 55:
        raise ValueError('check timeout must be between one and 55 seconds')
    if type(max_output_bytes) is not int or not 1 <= max_output_bytes <= 32768:
        raise ValueError('invalid command output budget')
    payload = json.dumps({'schema_version': 1, 'challenge': secrets.token_hex(32), 'subject': {
        'run_id': scope.run_id, 'revision': scope.revision, 'bundle_hash': scope.bundle_hash,
        'source_fingerprint': scope.source_fingerprint,
        'proposal_fingerprint': proposal.fingerprint}, 'files': [
        {'path': path, 'sha256': hashlib.sha256(body).hexdigest(),
         'content': base64.b64encode(body).decode()} for path, body in sorted(files.items())],
        'argv': list(argv), 'timeout_seconds': timeout_seconds, 'output_limit': max_output_bytes},
        sort_keys=True, separators=(',', ':')).encode()
    fingerprint = hashlib.sha256(payload).hexdigest()
    execution = run_offline_command(image=image, argv=('python', '-I', '-c', _WORKER),
        timeout_seconds=timeout_seconds + 5, max_output_bytes=262144, input_bytes=payload)
    def result(status, code=None, output='', unchanged=False, reason=''):
        return WorkspaceCheckResult(status, code, output, fingerprint, proposal.fingerprint,
                                    execution.cleaned_up, unchanged, reason)
    if not execution.cleaned_up:
        return result('cleanup_failed', reason=execution.reason)
    if execution.status != 'succeeded':
        return result(execution.status, reason=execution.reason)
    if execution.exit_code != 0:
        return result('protocol_error', reason='executor_success_not_verified')
    try:
        report = json.loads(execution.output, object_pairs_hook=_unique)
        if (not isinstance(report, dict) or set(report) != {'schema_version', 'request_sha256',
                'status', 'exit_code', 'source_unchanged', 'output'}
                or type(report['schema_version']) is not int or report['schema_version'] != 1
                or report['request_sha256'] != fingerprint
                or report['status'] not in {'succeeded', 'failed', 'timed_out', 'output_limit',
                                            'tampered'}
                or type(report['source_unchanged']) is not bool
                or not isinstance(report['output'], str)
                or len(report['output'].encode('utf-8')) > max_output_bytes * 3
                or (report['exit_code'] is not None and (type(report['exit_code']) is not int
                    or not 0 <= report['exit_code'] <= 255))
                or (report['status'] == 'succeeded' and (report['exit_code'] != 0
                    or not report['source_unchanged']))):
            raise ValueError('invalid workspace report')
        return result(report['status'], report['exit_code'], report['output'],
                      report['source_unchanged'])
    except (ValueError, TypeError, KeyError, RecursionError):
        return result('protocol_error', reason='workspace_report_not_verified')
