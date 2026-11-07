"""Delivery preparation binds full source inventory, without granting delivery."""
import copy
import hashlib
import json
from dataclasses import replace

import pytest

from sf_factory.change_proposal import ProposalScope, parse_change_proposal
from sf_factory.delivery_plan import build_delivery_plan
from sf_factory.source_snapshot import _fingerprint


def fixture():
    files = {'app.py': b'old\n', 'untouched.py': b'keep\n'}
    manifest = {'schema_version': 1, 'run_id': 'a' * 32, 'revision': 'b' * 40,
                'bundle_hash': 'c' * 64, 'files': [
                    {'path': path, 'mode': '100755' if path == 'app.py' else '100644',
                     'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                    for path, data in files.items()]}
    fingerprint = _fingerprint(manifest)
    scope = ProposalScope('a' * 32, 'b' * 40, 'c' * 64, fingerprint, ('app.py', 'new.py'))
    proposal = parse_change_proposal(json.dumps({
        'schema_version': 1, 'run_id': scope.run_id, 'revision': scope.revision,
        'bundle_hash': scope.bundle_hash, 'source_fingerprint': fingerprint,
        'changes': [{'path': 'app.py', 'before_sha256': hashlib.sha256(files['app.py']).hexdigest(),
                     'content': 'new\n'}, {'path': 'new.py', 'before_sha256': None,
                                          'content': 'created\n'}]}),
        scope=scope, source_files=files)
    return dict(scope=scope, proposal=proposal, source_files=files,
                snapshot={'snapshot_id': 'd' * 32, 'fingerprint': fingerprint,
                          'manifest': manifest}, repository='provider/repository',
                base_branch='main')


def test_exact_bytes_modes_and_stable_identity_without_side_effects(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    kwargs = fixture()
    plan = build_delivery_plan(**kwargs)
    assert plan == build_delivery_plan(**copy.deepcopy(kwargs))
    changes = {c.path: c for c in plan.changes}
    assert changes['app.py'].before == b'old\n'
    assert changes['app.py'].after == b'new\n'
    assert changes['app.py'].executable is True
    assert changes['new.py'].before is None
    assert changes['new.py'].executable is False
    assert 'untouched.py' not in changes
    assert plan.fingerprint in plan.marker
    assert plan.branch.endswith(plan.fingerprint[:12])
    assert list(tmp_path.iterdir()) == []


def test_unchanged_file_tampering_is_detected():
    kwargs = fixture()
    kwargs['source_files']['untouched.py'] = b'evil\n'
    with pytest.raises(ValueError, match='inventory'):
        build_delivery_plan(**kwargs)


@pytest.mark.parametrize('field,value', [('run_id', 'e' * 32), ('revision', 'e' * 40),
    ('bundle_hash', 'e' * 64), ('schema_version', True), ('files', [])])
def test_snapshot_cannot_be_substituted(field, value):
    kwargs = fixture()
    kwargs['snapshot']['manifest'][field] = value
    with pytest.raises(ValueError):
        build_delivery_plan(**kwargs)


@pytest.mark.parametrize('field,value', [('mode', []), ('mode', '120000'), ('bytes', True),
    ('sha256', 'e' * 64), ('path', 'missing.py')])
def test_self_consistent_manifest_still_requires_exact_inventory(field, value):
    kwargs = fixture()
    manifest = kwargs['snapshot']['manifest']
    manifest['files'][0][field] = value
    fp = _fingerprint(manifest)
    kwargs['snapshot']['fingerprint'] = fp
    kwargs['scope'] = replace(kwargs['scope'], source_fingerprint=fp)
    kwargs['proposal'] = replace(kwargs['proposal'], source_fingerprint=fp)
    with pytest.raises(ValueError, match='inventory'):
        build_delivery_plan(**kwargs)


def test_duplicate_inventory_is_rejected_even_with_matching_fingerprint():
    kwargs = fixture()
    manifest = kwargs['snapshot']['manifest']
    manifest['files'][1] = manifest['files'][0].copy()
    fp = _fingerprint(manifest)
    kwargs['snapshot']['fingerprint'] = fp
    kwargs['scope'] = replace(kwargs['scope'], source_fingerprint=fp)
    kwargs['proposal'] = replace(kwargs['proposal'], source_fingerprint=fp)
    with pytest.raises(ValueError, match='inventory'):
        build_delivery_plan(**kwargs)


@pytest.mark.parametrize('field,value', [('repository', 'other/repository'),
                                        ('base_branch', 'release')])
def test_delivery_destination_is_part_of_identity(field, value):
    kwargs = fixture()
    plan = build_delivery_plan(**kwargs)
    kwargs[field] = value
    assert plan.fingerprint != build_delivery_plan(**kwargs).fingerprint


def test_exact_bytes_and_modes_are_part_of_identity():
    plan = build_delivery_plan(**fixture())
    change = plan.changes[0]
    assert replace(plan, changes=(replace(change, after=b'other'),)).fingerprint != plan.fingerprint
    different_mode = replace(plan, changes=(replace(change, executable=False),))
    assert different_mode.fingerprint != plan.fingerprint
