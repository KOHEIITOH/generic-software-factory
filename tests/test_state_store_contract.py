"""One issue persistence contract, reusable by each backend."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from issue_fixtures import seed_issue

from sf_factory.file_state import FileIssueStore
from sf_factory.sqlite_state import SqliteIssueStore
from sf_factory.state_store import IssueSnapshot, IssueStore, StateNotFound


@pytest.fixture(params=['sqlite', 'file'])
def store_factory(request):
    def build(root: Path) -> IssueStore:
        root.mkdir(parents=True, exist_ok=True)
        if request.param == 'file':
            return FileIssueStore(root)
        return SqliteIssueStore(root / 'factory.sqlite3')
    return build


def test_task_survives_store_recreation(store_factory, tmp_path):
    store = store_factory(tmp_path)
    issue = seed_issue(store, 'Keep original whitespace  ')
    record = store_factory(tmp_path).get_issue(issue)
    assert isinstance(record, IssueSnapshot)
    assert record.key == issue
    assert record.prompt == 'Keep original whitespace  '
    assert record.observed_at


def test_reimport_refreshes_snapshot_without_new_identity(store_factory, tmp_path):
    store = store_factory(tmp_path)
    issue = store.import_issue(provider='github', instance='owner/repo', external_id='42',
                                      prompt='original', external_url='https://example.invalid/42')
    restored = store_factory(tmp_path)
    again = restored.import_issue(
        provider='github', instance='owner/repo', external_id='42',
        prompt='updated', external_url=None,
    )
    assert issue == again
    assert restored.get_issue(issue).prompt == 'updated'


def test_external_identity_namespaces_are_distinct(store_factory, tmp_path):
    store = store_factory(tmp_path)
    issues = [store.import_issue(provider=p, instance=i, external_id=n, prompt='issue')
             for p, i, n in [('github', 'a/b', '1'), ('github', 'a/c', '1'),
                             ('gitlab', 'a/b', '1'), ('github', 'a/b', '2')]]
    assert len(set(issues)) == 4


def test_concurrent_imports_create_one_task(store_factory, tmp_path):
    store_factory(tmp_path)

    def attempt(_):
        return store_factory(tmp_path).import_issue(
            provider='github', instance='a/b', external_id='1', prompt='issue',
        )
    with ThreadPoolExecutor(max_workers=4) as pool:
        issues = list(pool.map(attempt, range(8)))
    assert len(set(issues)) == 1
    assert store_factory(tmp_path).get_issue(issues[0]).prompt == 'issue'


def test_missing_task_has_domain_error(store_factory, tmp_path):
    with pytest.raises(StateNotFound, match='issue not found'):
        store_factory(tmp_path).get_issue('missing')


@pytest.mark.parametrize('prompt', ['', '   ', None])
def test_invalid_prompt_rejected(store_factory, tmp_path, prompt):
    with pytest.raises(ValueError):
        seed_issue(store_factory(tmp_path), prompt)


def test_invalid_external_identity_rejected(store_factory, tmp_path):
    store = store_factory(tmp_path)
    with pytest.raises(ValueError):
        store.import_issue(provider='', instance='a/b', external_id='1', prompt='issue')
    with pytest.raises(ValueError):
        store.import_issue(provider='github', instance='a' * 513,
                                   external_id='1', prompt='issue')
