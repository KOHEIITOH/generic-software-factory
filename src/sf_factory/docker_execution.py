"""Experimental offline command isolation. Not connected to AI authorization.

No host mounts, inherited credentials, network or external operations.
Explicit bounded stdin is data only; workspace/AI integration remains separate.
Only a trusted controller may select the pinned image and command.
"""
from __future__ import annotations

import json
import os
import re
import selectors
import subprocess
import time
import uuid
from dataclasses import dataclass
from typing import Literal

_PROXY_NAMES = ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY',
                'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy')
_TMPFS = {'/workspace': 'rw,nosuid,nodev,noexec,size=16m,mode=1777',
          '/tmp': 'rw,nosuid,nodev,noexec,size=16m,mode=1777'}


MAX_INPUT_BYTES = 16 * 1024 * 1024


ExecutionStatus = Literal[
    'succeeded', 'failed', 'timed_out', 'output_limit', 'cleanup_failed', 'unavailable'
]


@dataclass(frozen=True)
class DockerExecutionResult:
    status: ExecutionStatus
    exit_code: int | None
    output: str
    image: str
    cleaned_up: bool
    reason: str = ''


def _docker_env() -> dict[str, str]:
    # Pin the local daemon without altering registry configuration or authentication.
    return {k: v for k, v in os.environ.items() if k not in {
        'DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_TLS', 'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH'
    }}


def _docker(args: list[str], *, timeout: int = 15) -> subprocess.CompletedProcess:
    return subprocess.run(
        ['docker', '--host=unix:///var/run/docker.sock', *args],
        env=_docker_env(), capture_output=True, text=True, timeout=timeout, check=False,
    )


def resource_limits_available() -> bool:
    """Inspect the pinned daemon's enforcement capabilities, not requested values."""
    template = (
        '{"driver":{{json .CgroupDriver}},"version":{{json .CgroupVersion}},'
        '"memory":{{json .MemoryLimit}},"swap":{{json .SwapLimit}},'
        '"pids":{{json .PidsLimit}},"cpu":{{json .CPUCfsQuota}}}'
    )
    try:
        result = _docker(['info', '--format', template])
        info = json.loads(result.stdout) if result.returncode == 0 else {}
        return (info.get('driver') in {'systemd', 'cgroupfs'} and info.get('version') == '2'
                and all(info.get(key) is True for key in ('memory', 'swap', 'pids', 'cpu')))
    except (OSError, ValueError, TypeError, AttributeError, subprocess.SubprocessError):
        return False


def _verified(document: dict, image: str, argv: tuple[str, ...], *, stdin: bool = False) -> bool:
    config, host = document.get('Config', {}), document.get('HostConfig', {})
    environment = config.get('Env') or []
    return all((
        config.get('Image') == image,
        config.get('User') == '65534:65534',
        config.get('WorkingDir') == '/workspace',
        config.get('OpenStdin', False) is stdin,
        config.get('Entrypoint') == [argv[0]],
        (config.get('Cmd') or []) == list(argv[1:]),
        all(name + '=' in environment for name in _PROXY_NAMES),
        host.get('NetworkMode') == 'none',
        host.get('ReadonlyRootfs') is True,
        host.get('Privileged') is False,
        host.get('CapDrop') == ['ALL'],
        not host.get('CapAdd'),
        host.get('SecurityOpt') == ['no-new-privileges'],
        host.get('PidsLimit') == 64,
        host.get('Memory') == 268435456,
        host.get('MemorySwap') == 268435456,
        host.get('NanoCpus') == 1000000000,
        host.get('Init') is True,
        not host.get('Binds'),
        not host.get('Mounts'),
        not document.get('Mounts'),
        host.get('Tmpfs') == _TMPFS,
        host.get('LogConfig', {}).get('Type') == 'none',
        host.get('PidMode', '') == '',
        host.get('UsernsMode', '') == '',
        host.get('UTSMode', '') == '',
        not host.get('VolumesFrom'),
        not host.get('PortBindings'),
        not host.get('PublishAllPorts'),
        host.get('IpcMode') == 'private',
        not host.get('Devices'),
    ))


def run_offline_command(
    *, image: str, argv: tuple[str, ...], timeout_seconds: int = 30,
    max_output_bytes: int = 65536, input_bytes: bytes | None = None,
) -> DockerExecutionResult:
    """Run only in tmpfs workspace; no arbitrary host path can be mounted.

    `succeeded` means command exit zero and cleanup confirmed, not quality or
    isolation approval for an AI runtime. Images must already be pulled by the
    controller through a trusted registry; this function never pulls an image.
    """
    from sf_factory.operation_control import checkpoint
    checkpoint()
    if not re.fullmatch(r'[a-z0-9./:_-]+@sha256:[a-f0-9]{64}', image):
        raise ValueError('a pinned image digest is required')
    if (not isinstance(argv, tuple) or not argv or len(argv) > 128
            or any(not isinstance(a, str) or '\x00' in a or len(a) > 65536 for a in argv)
            or not argv[0] or argv[0].startswith('-')):
        raise ValueError('explicit bounded command argv required')
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 60:
        raise ValueError('timeout must be between 1 and 60 seconds')
    if type(max_output_bytes) is not int or not 1 <= max_output_bytes <= 1048576:
        raise ValueError('invalid output budget')
    if input_bytes is not None and (not isinstance(input_bytes, bytes)
                                    or len(input_bytes) > MAX_INPUT_BYTES):
        raise ValueError('stdin must be immutable bytes within the input budget')
    if not resource_limits_available():
        return DockerExecutionResult(
            'unavailable', None, '', image, True, 'daemon_cannot_enforce_resource_limits'
        )
    name = 'sf-offline-' + uuid.uuid4().hex
    arguments = [
        'create', '--pull=never', '--name', name, '--label', 'sf.execution=offline-v1',
        '--user', '65534:65534', '--workdir', '/workspace', '--network', 'none',
        '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
        '--pids-limit', '64', '--memory', '256m', '--memory-swap', '256m', '--cpus', '1',
        '--init', '--ipc', 'private', '--log-driver', 'none',
    ]
    if input_bytes is not None:
        arguments.append('--interactive')
    for mount, options in _TMPFS.items():
        arguments += ['--tmpfs', mount + ':' + options]
    for key in _PROXY_NAMES:
        arguments += ['--env', key + '=']
    arguments += ['--entrypoint', argv[0], image, *argv[1:]]
    status: ExecutionStatus = 'failed'
    exit_code = None
    output = bytearray()
    process = None
    cleaned = False
    try:
        created = _docker(arguments)
        if created.returncode != 0:
            raise ValueError('container creation failed')
        inspected = _docker(['inspect', name])
        if inspected.returncode != 0:
            raise ValueError('inspect failed')
        document = json.loads(inspected.stdout)
        if len(document) != 1 or not _verified(
            document[0], image, argv, stdin=input_bytes is not None,
        ):
            raise ValueError('container configuration mismatch')
        start = ['docker', '--host=unix:///var/run/docker.sock', 'start', '--attach']
        if input_bytes is not None:
            start.append('--interactive')
        process = subprocess.Popen(
            [*start, name], env=_docker_env(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL, bufsize=0,
        )
        assert process.stdout is not None
        deadline = time.monotonic() + timeout_seconds
        sent = 0
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ, 'stdout')
            if process.stdin is not None:
                os.set_blocking(process.stdin.fileno(), False)
                if input_bytes:
                    selector.register(process.stdin, selectors.EVENT_WRITE, 'stdin')
                else:
                    process.stdin.close()
            finished = False
            while not finished:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    status = 'timed_out'
                    break
                events = selector.select(min(remaining, 0.1))
                for key, _ in events:
                    if key.data == 'stdin':
                        assert input_bytes is not None and process.stdin is not None
                        try:
                            sent += os.write(process.stdin.fileno(), input_bytes[sent:sent + 8192])
                        except BlockingIOError:
                            continue
                        if sent == len(input_bytes):
                            selector.unregister(process.stdin)
                            process.stdin.close()
                        continue
                    chunk = os.read(process.stdout.fileno(), 8192)
                    if not chunk:
                        finished = True
                        break
                    capacity = max_output_bytes - len(output)
                    output.extend(chunk[:capacity])
                    if len(chunk) > capacity:
                        status = 'output_limit'
                        finished = True
                        break
                # Drain until stdout EOF; neither a full stdin pipe nor process
                # exit may bypass timeout/output bounds or drop trailing output.
        if status not in {'timed_out', 'output_limit'} and input_bytes is not None:
            if sent != len(input_bytes):
                raise ValueError('input transfer did not finish')
        if status not in {'timed_out', 'output_limit'}:
            process.wait(timeout=5)
            state = _docker(['inspect', '--format', '{{json .State}}', name])
            observed = json.loads(state.stdout) if state.returncode == 0 else {}
            if observed.get('Status') == 'exited':
                exit_code = observed.get('ExitCode')
                status = 'succeeded' if exit_code == 0 and process.returncode == 0 else 'failed'
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError):
        status = 'failed'
    finally:
        try:
            removed = _docker(['rm', '--force', '--volumes', name])
            cleaned = removed.returncode == 0
        except (OSError, subprocess.SubprocessError):
            cleaned = False
        if process is not None:
            try:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)
            finally:
                if process.stdin:
                    process.stdin.close()
                if process.stdout:
                    process.stdout.close()
    if not cleaned:
        status = 'cleanup_failed'
    return DockerExecutionResult(status, exit_code, output.decode('utf-8', errors='replace'),
                                 image, cleaned)
