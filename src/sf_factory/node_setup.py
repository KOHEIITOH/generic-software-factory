"""Static npm proposals and explicitly approved, manifest-only dependency images."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import signal
import subprocess
import tempfile
import time
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from sf_factory.automation_state import fingerprint
from sf_factory.docker_execution import _docker, _docker_env
from sf_factory.file_document import read_document, write_document
from sf_factory.file_state import lock_directory
from sf_factory.source_snapshot import _git, _sync_directory
from sf_factory.state_store import StateConflict

PYTHON_IMAGE = 'python@sha256:09a17cad02668ae61ece136b4fd36ac3849e14f670ebedb637ea3e15580525bc'
NODE_IMAGE = 'node@sha256:5ec23b7c622b00547753bc6ffd78085dd868a68aeb41c8e0a1418f033e13d96d'
DOCKERFILE = f'''FROM {NODE_IMAGE} AS node
FROM {PYTHON_IMAGE}
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \\
 && mkdir /opt/sf-node-deps && chown 65534:65534 /opt/sf-node-deps
WORKDIR /opt/sf-node-deps
COPY --chown=65534:65534 package.json package-lock.json ./
USER 65534:65534
RUN --mount=type=secret,id=proxy_ca,uid=65534 \\
 NODE_EXTRA_CA_CERTS=/run/secrets/proxy_ca npm ci --ignore-scripts --no-audit --no-fund \\
 --registry=https://registry.npmjs.org --fetch-retries=0 --cache=/tmp/npm-cache \\
 && rm -rf /tmp/npm-cache
WORKDIR /workspace
'''

# Runs inside the existing offline candidate container, never on the host.
# Commands operate on a private copy: caches/reports cannot alter source provenance.
NODE_CHECK = r'''
import hashlib,json,os,shutil,subprocess,sys,tempfile
from pathlib import Path
plan=json.loads(sys.argv[1])
source=Path('/workspace')
for name,sha in plan['hashes'].items():
    if hashlib.sha256((source/name).read_bytes()).hexdigest()!=sha:
        raise SystemExit('Node manifests changed; approve a new dependency image')
with tempfile.TemporaryDirectory(prefix='sf-node-',dir='/tmp') as temporary:
    work=Path(temporary)/'source'
    shutil.copytree(source,work)
    modules=work/'node_modules'
    modules.mkdir()
    for package in Path('/opt/sf-node-deps/node_modules').iterdir():
        (modules/package.name).symlink_to(package)
    env=dict(os.environ,CI='1',HOME=temporary,NEXT_TELEMETRY_DISABLED='1',
             npm_config_cache=temporary+'/npm-cache',npm_config_offline='true',
             npm_config_ignore_scripts='true',NO_COLOR='1')
    command=['npm','--offline','--ignore-scripts','run',plan['script']]
    report=Path(temporary)/'report.json'
    if plan['runner']=='vitest':
        command+=['--','--run','--maxWorkers=1','--no-file-parallelism',
                  '--reporter=json','--outputFile='+str(report)]
    elif plan['runner']=='jest':
        command+=['--','--runInBand','--watch=false','--json','--outputFile='+str(report)]
    result=subprocess.run(command,cwd=work,env=env,stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT,timeout=25)
    if result.returncode:
        print(result.stdout.decode(errors='replace')[:8192])
        raise SystemExit(1)
    if plan['runner'] in ('vitest','jest'):
        if not report.is_file() or report.stat().st_size>1048576:
            raise SystemExit('bounded test report required')
        value=json.loads(report.read_text())
        rows=[a for t in value.get('testResults',[]) for a in t.get('assertionResults',[])]
        total=value.get('numTotalTests')
        if (type(total) is not int or total<=0 or len(rows)!=total
                or value.get('numPassedTests')!=total or value.get('numFailedTests')!=0
                or value.get('numPendingTests',0)!=0 or value.get('numTodoTests',0)!=0
                or value.get('success') is not True
                or any(a.get('status')!='passed' for a in rows)):
            raise SystemExit('tests must execute: zero, skipped, todo and failed tests rejected')
print('SF_NODE_CHECK_PASSED')
'''


def _document(body: bytes) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate npm metadata key')
            result[key] = value
        return result
    value = json.loads(body, object_pairs_hook=pairs)
    if not isinstance(value, dict):
        raise ValueError('npm metadata object required')
    return value


def manifests(root: Path) -> dict[str, bytes]:
    return {name: _git(root, ['show', 'HEAD:' + name], 1048576, time.monotonic() + 10)
            for name in ('package.json', 'package-lock.json')}


def _validate_lock(package: dict, lock: dict) -> None:
    if package.get('workspaces') or lock.get('lockfileVersion') not in (2, 3):
        raise ValueError('npm lockfile v2/v3 without workspaces required')
    entries = lock.get('packages')
    if not isinstance(entries, dict) or '' not in entries or len(entries) > 3000:
        raise ValueError('bounded npm package inventory required')
    for path, value in entries.items():
        if not isinstance(value, dict):
            raise ValueError('npm package metadata required')
        if path == '':
            continue
        url = urlsplit(value.get('resolved', ''))
        if (not path.startswith('node_modules/') or '..' in PurePosixPath(path).parts
                or PurePosixPath(path).as_posix() != path or '\\' in path or value.get('link')
                or url.scheme != 'https' or url.netloc != 'registry.npmjs.org'
                or url.query or url.fragment or not url.path.endswith('.tgz')
                or not isinstance(value.get('integrity'), str)
                or not re.fullmatch(r'sha(512|1)-[A-Za-z0-9+/]+=*', value['integrity'])):
            raise ValueError('only integrity-pinned public npm registry packages supported')


def node_plan(root: Path, files: list[str], data_root: Path) -> dict | None:
    if 'package.json' not in files:
        return None
    if 'package-lock.json' not in files:
        return {'available': False, 'reason': 'npmのpackage-lock.jsonが必要です。'
                'yarn/pnpmは自動準備の対象外です。'}
    try:
        bodies = manifests(root)
        package, lock = (_document(bodies[n]) for n in ('package.json', 'package-lock.json'))
        _validate_lock(package, lock)
        scripts = package.get('scripts', {})
        if not isinstance(scripts, dict):
            raise ValueError('npm scripts object required')
        hashes = {n: hashlib.sha256(b).hexdigest() for n, b in bodies.items()}
        checks, display = [], []
        for script in ('test', 'typecheck', 'lint', 'build'):
            text = scripts.get(script)
            if not isinstance(text, str):
                continue
            parts = shlex.split(text)
            runner = None
            if script == 'test' and parts in (['vitest'], ['vitest', 'run'], ['jest']):
                runner = parts[0]
            elif script == 'test':
                return {'available': False, 'reason': 'testスクリプトが自動検証方式に非対応です。'
                        'テストを省略して型・lintだけへ置き換えません。手動検証設定を確認してください。'}
            elif script == 'typecheck' and parts == ['tsc', '--noEmit']:
                runner = 'typecheck'
            elif script == 'lint' and parts and parts[0] == 'eslint' and all(
                    p in {'eslint', '.', 'src', '--max-warnings=0'} for p in parts):
                runner = 'lint'
            elif script == 'build' and not checks and parts in (
                    ['tsc', '--noEmit'], ['tsc', '-b']):
                runner = 'typecheck'
            if runner:
                args = json.dumps({'hashes': hashes, 'script': script, 'runner': runner},
                                  sort_keys=True, separators=(',', ':'))
                checks.append({'id': 'npm_' + script,
                               'argv': ['python', '-I', '-B', '-c', NODE_CHECK, args],
                               'stdout': 'SF_NODE_CHECK_PASSED\n'})
                display.append({'script': script, 'command': text, 'kind': runner})
        if not checks:
            return {'available': False, 'reason': '対応するtest（Vitest/Jest）・typecheck・lintを'
                    '検出できません。手動検証設定が必要です。'}
        recipe = fingerprint({'schema': 1, 'hashes': hashes, 'dockerfile': DOCKERFILE})
        image = cached_image(data_root, recipe)
        return {'available': True, 'fingerprint': recipe, 'hashes': hashes, 'checks': checks,
                'scripts': display, 'has_tests': any(c['kind'] in {'jest', 'vitest'}
                                                   for c in display),
                'image': image, 'bases': [NODE_IMAGE, PYTHON_IMAGE]}
    except (ValueError, TypeError, KeyError, RecursionError):
        return {'available': False, 'reason': 'npm lock・取得元・scriptsを安全に検証できません。'
                '公開npm registryの固定integrity付きlock v2/v3に対応します。'}


def cached_image(data_root: Path, key: str) -> str | None:
    directory = data_root / 'node-images-v1' / key
    if not directory.is_dir():
        return None
    if not (directory / 'state.json').exists():
        return None  # Interrupted first receipt publication; rebuild without executing code.
    with lock_directory(directory) as fd:
        value = read_document(fd)
    image = value.get('image')
    if (value.get('recipe') != key or not isinstance(image, str)
            or not re.fullmatch(r'sha256:[a-f0-9]{64}', image)):
        raise StateConflict('invalid Node image receipt')
    found = _docker(['image', 'inspect', '--format', '{{.Id}}', image], timeout=10)
    return image if found.returncode == 0 and found.stdout.strip() == image else None


def prepare_image(root: Path, data_root: Path, plan: dict) -> str:
    """Caller must authorize network/install; never accept caller Dockerfiles or URLs."""
    key = plan['fingerprint']
    directory = data_root / 'node-images-v1'
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    with lock_directory(directory, lock_timeout=0.1):
        cached = cached_image(data_root, key)
        if cached:
            return cached
        bodies = manifests(root)
        if {n: hashlib.sha256(b).hexdigest() for n, b in bodies.items()} != plan['hashes']:
            raise StateConflict('Node manifests changed before image preparation')
        with tempfile.TemporaryDirectory(prefix='sf-node-image-') as temporary:
            context = Path(temporary)
            (context / 'Dockerfile').write_text(DOCKERFILE)
            for name, body in bodies.items():
                (context / name).write_bytes(body)
            # Proxy CA is a public build secret, never copied into an image layer.
            args = ['docker', '--host=unix:///var/run/docker.sock', 'build', '--quiet',
                    '--iidfile', str(context / 'image-id'), '--label', 'sf.node-recipe=' + key]
            if os.environ.get('CODEX_PROXY_CERT'):
                args += ['--secret', 'id=proxy_ca,src=' + os.environ['CODEX_PROXY_CERT']]
            args.append(str(context))
            with subprocess.Popen(args, env=_docker_env(), stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, start_new_session=True) as process:
                try:
                    code = process.wait(timeout=600)
                finally:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait(timeout=10)
            if code:
                raise ValueError('Node dependency image build failed')
            image = (context / 'image-id').read_text().strip()
        if not re.fullmatch(r'sha256:[a-f0-9]{64}', image):
            raise ValueError('immutable local image identity required')
        # Do not install a receipt if the source manifests changed during the build.
        if {n: hashlib.sha256(b).hexdigest() for n, b in manifests(root).items()} != plan['hashes']:
            raise StateConflict('Node manifests changed during image preparation')
        (directory / key).mkdir(mode=0o700, exist_ok=True)
        with lock_directory(directory / key) as fd:
            write_document(fd, {'image': image, 'recipe': key})
        _sync_directory(directory)
        return image
