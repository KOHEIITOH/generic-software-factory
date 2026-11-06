"""One task persistence contract, reusable by each backend."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from sf_factory.sqlite_state import SqliteStateStore
from sf_factory.state_store import StateNotFound, StateStore, TaskRecord


@pytest.fixture(params=['sqlite'])
def store_factory(request):
    def build(root: Path) -> StateStore:
        root.mkdir(parents=True, exist_ok=True)
        return SqliteStateStore(root / 'factory.sqlite3')
    return build


def test_task_survives_store_recreation(store_factory, tmp_path):
    store = store_factory(tmp_path)
    task = store.create_task('Keep original whitespace  ')
    record = store_factory(tmp_path).get_task(task)
    assert isinstance(record, TaskRecord)
    assert record.id == task
    assert record.prompt == 'Keep original whitespace  '
    assert record.created_at


def test_import_once_retains_original_task_and_prompt(store_factory, tmp_path):
    store = store_factory(tmp_path)
    task = store.import_external_task(provider='github', instance='owner/repo', external_id='42',
                                      prompt='original', external_url='https://example.invalid/42')
    restored = store_factory(tmp_path)
    again = restored.import_external_task(
        provider='github', instance='owner/repo', external_id='42',
        prompt='updated', external_url=None,
    )
    assert task == again
    assert restored.get_task(task).prompt == 'original'


def test_external_identity_namespaces_are_distinct(store_factory, tmp_path):
    store = store_factory(tmp_path)
    tasks = [store.import_external_task(provider=p, instance=i, external_id=n, prompt='task')
             for p, i, n in [('github', 'a/b', '1'), ('github', 'a/c', '1'),
                             ('gitlab', 'a/b', '1'), ('github', 'a/b', '2')]]
    assert len(set(tasks)) == 4


def test_concurrent_imports_create_one_task(store_factory, tmp_path):
    store_factory(tmp_path)

    def attempt(_):
        return store_factory(tmp_path).import_external_task(
            provider='github', instance='a/b', external_id='1', prompt='task',
        )
    with ThreadPoolExecutor(max_workers=4) as pool:
        tasks = list(pool.map(attempt, range(8)))
    assert len(set(tasks)) == 1
    assert store_factory(tmp_path).get_task(tasks[0]).prompt == 'task'


def test_missing_task_has_domain_error(store_factory, tmp_path):
    with pytest.raises(StateNotFound, match='task not found'):
        store_factory(tmp_path).get_task('missing')


@pytest.mark.parametrize('prompt', ['', '   ', None])
def test_invalid_prompt_rejected(store_factory, tmp_path, prompt):
    with pytest.raises(ValueError):
        store_factory(tmp_path).create_task(prompt)


def test_invalid_external_identity_rejected(store_factory, tmp_path):
    store = store_factory(tmp_path)
    with pytest.raises(ValueError):
        store.import_external_task(provider='', instance='a/b', external_id='1', prompt='task')
    with pytest.raises(ValueError):
        store.import_external_task(provider='github', instance='a' * 513,
                                   external_id='1', prompt='task')
