"""File storage durability, process exclusion, corruption and failure behavior."""
import json
import multiprocessing
import os
import stat
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pytest
from issue_fixtures import seed_issue

from sf_factory.file_state import FileIssueStore
from sf_factory.state_store import StateConflict, StateCorrupt, StateUnavailable


def _import_process(root):
    return FileIssueStore(Path(root)).import_issue(
        provider='github', instance='owner/repo', external_id='42', prompt='original',
    )


def test_independent_processes_import_once(tmp_path):
    FileIssueStore(tmp_path)
    with ProcessPoolExecutor(
        max_workers=2, mp_context=multiprocessing.get_context('spawn'),
    ) as pool:
        issues = list(pool.map(_import_process, [str(tmp_path)] * 4))
    assert len(set(issues)) == 1
    files = list((tmp_path / 'issues-v2').glob('*.json'))
    assert len(files) == 1
    assert len(json.loads(files[0].read_text())['events']) == 1


@pytest.mark.parametrize('corruption', ['bad_json', 'new_version', 'bool_version', 'duplicate_key'])
def test_corrupt_or_unknown_record_is_not_overwritten(tmp_path, corruption):
    store = FileIssueStore(tmp_path)
    issue_key = _import_process(str(tmp_path))
    path = store.directory / (issue_key + '.json')
    if corruption == 'bad_json':
        path.write_text('{bad json')
    elif corruption == 'duplicate_key':
        original = path.read_text()
        path.write_text('{"schema_version":1,' + original[1:])
    else:
        record = json.loads(path.read_text())
        record['schema_version'] = True if corruption == 'bool_version' else 999
        path.write_text(json.dumps(record))
    before = path.read_bytes()
    with pytest.raises(StateCorrupt):
        _import_process(str(tmp_path))
    assert path.read_bytes() == before


def test_task_and_lock_symlinks_are_refused(tmp_path):
    store = FileIssueStore(tmp_path)
    issue = seed_issue(store, 'issue')
    path = store.directory / (issue + '.json')
    outside = tmp_path / 'outside-canary'
    outside.write_text('must remain unchanged')
    path.unlink()
    path.symlink_to(outside)
    with pytest.raises(StateUnavailable):
        store.get_issue(issue)
    lock = store.directory / '.lock'
    lock.unlink()
    lock.symlink_to(outside)
    with pytest.raises(StateUnavailable):
        seed_issue(store, 'another')
    assert outside.read_text() == 'must remain unchanged'


def test_failed_replace_leaves_no_partial_task(tmp_path, monkeypatch):
    store = FileIssueStore(tmp_path)

    def fail(*args, **kwargs):
        raise OSError('simulated replace failure')
    monkeypatch.setattr('sf_factory.file_state.os.replace', fail)
    with pytest.raises(StateUnavailable):
        seed_issue(store, 'issue')
    assert [p.name for p in store.directory.iterdir()] == ['.lock']


def test_failed_file_fsync_leaves_no_partial_task(tmp_path, monkeypatch):
    store = FileIssueStore(tmp_path)
    original = os.fsync

    def fail(fd):
        if stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError('simulated fsync failure')
        return original(fd)
    monkeypatch.setattr('sf_factory.file_state.os.fsync', fail)
    with pytest.raises(StateUnavailable):
        seed_issue(store, 'issue')
    assert [p.name for p in store.directory.iterdir()] == ['.lock']


def test_uncertain_directory_sync_reimport_is_idempotent(tmp_path, monkeypatch):
    store = FileIssueStore(tmp_path)
    original = os.fsync
    failed = []

    def fail_once(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode) and not failed:
            failed.append(True)
            raise OSError('simulated directory durability failure')
        return original(fd)
    monkeypatch.setattr('sf_factory.file_state.os.fsync', fail_once)
    with pytest.raises(StateUnavailable):
        store.import_issue(
            provider='github', instance='a/b', external_id='1', prompt='issue',
        )
    issue = store.import_issue(provider='github', instance='a/b', external_id='1',
                                      prompt='updated')
    assert store.get_issue(issue).prompt == 'updated'
    assert len(list(store.directory.glob('*.json'))) == 1


def test_missing_lock_capability_does_not_fall_back(tmp_path, monkeypatch):
    monkeypatch.setattr('sf_factory.file_state.fcntl', None)
    with pytest.raises(StateUnavailable):
        FileIssueStore(tmp_path)


def test_existing_sqlite_root_requires_explicit_migration(tmp_path):
    (tmp_path / 'factory.sqlite3').write_text('existing database placeholder')
    with pytest.raises(StateConflict):
        FileIssueStore(tmp_path)


def test_record_is_private_and_bounded(tmp_path, monkeypatch):
    store = FileIssueStore(tmp_path)
    issue = seed_issue(store, 'private issue')
    assert (store.directory / (issue + '.json')).stat().st_mode & 0o777 == 0o600
    monkeypatch.setattr('sf_factory.file_state.MAX_RECORD_BYTES', 10)
    with pytest.raises(StateCorrupt):
        store.get_issue(issue)
    with pytest.raises(ValueError):
        seed_issue(store, 'large issue')
    assert len(list(store.directory.glob('*.json'))) == 1


def test_lock_timeout_does_not_write_without_exclusion(tmp_path):
    import fcntl
    store = FileIssueStore(tmp_path, lock_timeout=0.02)
    with (store.directory / '.lock').open('wb') as locked:
        fcntl.flock(locked, fcntl.LOCK_EX)
        with pytest.raises(StateUnavailable, match='lock timed out'):
            seed_issue(store, 'must not write')
    assert not list(store.directory.glob('*.json'))


def _crash_before_publish(root):
    store = FileIssueStore(Path(root))

    def crash(*args, **kwargs):
        os._exit(23)
    os.replace = crash
    store.import_issue(provider='github', instance='a/b', external_id='1', prompt='issue')


def test_process_crash_releases_lock_and_does_not_publish_partial_state(tmp_path):
    process = multiprocessing.get_context('spawn').Process(
        target=_crash_before_publish, args=(str(tmp_path),),
    )
    process.start()
    process.join(timeout=10)
    if process.is_alive():
        process.terminate()
        process.join(timeout=5)
        pytest.fail('state process did not stop')
    assert process.exitcode == 23
    assert not list((tmp_path / 'issues-v2').glob('*.json'))
    store = FileIssueStore(tmp_path)
    issue = store.import_issue(provider='github', instance='a/b', external_id='1',
                                      prompt='recovered')
    assert store.get_issue(issue).prompt == 'recovered'
    assert len(list(store.directory.glob('*.json'))) == 1


def test_unlock_error_still_closes_descriptors_and_releases_lock(tmp_path, monkeypatch):
    import fcntl
    store = FileIssueStore(tmp_path, lock_timeout=0.1)
    original = fcntl.flock
    failed = []

    def fail_once(fd, operation):
        if operation == fcntl.LOCK_UN and not failed:
            failed.append(True)
            raise OSError('simulated unlock failure')
        return original(fd, operation)
    monkeypatch.setattr('sf_factory.file_state.fcntl.flock', fail_once)
    with pytest.raises(StateUnavailable, match='cleanup failed'):
        seed_issue(store, 'result uncertain')
    # The write may already be committed, but the caller was not told it succeeded.
    record = next(store.directory.glob('*.json'))
    assert store.get_issue(record.stem).prompt == 'result uncertain'


def test_sqlite_and_factory_refuse_existing_file_state_without_creating_db(tmp_path):
    from sf_factory.factory import Factory
    from sf_factory.sqlite_state import SqliteIssueStore
    seed_issue(FileIssueStore(tmp_path), 'file issue')
    database = tmp_path / 'factory.sqlite3'
    with pytest.raises(StateConflict):
        SqliteIssueStore(database)
    assert not database.exists()
    with pytest.raises(StateConflict):
        Factory(tmp_path)
    assert not database.exists()
