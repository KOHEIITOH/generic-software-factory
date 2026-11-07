"""No local Task entity; Runs reference external Issues and freeze observed content."""
import json
from dataclasses import asdict

import pytest

from sf_factory.agent_registry import AgentRuntimeRegistry
from sf_factory.factory import Factory
from sf_factory.factory_selection import open_factory
from sf_factory.file_dashboard import FileDashboardFactory
from sf_factory.issue_reference import IssueReference
from sf_factory.runtime import RuntimeResult
from sf_factory.state_store import StateConflict


class FixtureRuntime:
    def execute(self, *, prompt, workspace, timeout_seconds):
        return RuntimeResult('fixture', 'succeeded', prompt, 0)


@pytest.fixture(params=[Factory, FileDashboardFactory])
def factory(request, tmp_path):
    registry = AgentRuntimeRegistry()
    registry.register('fixture', FixtureRuntime)
    return request.param(tmp_path, runtime_registry=registry)


def test_only_external_reference_defines_identity_and_no_standalone_crud_remains(factory):
    ref = IssueReference('github', 'owner/repo', '100')
    key = factory.import_issue(**asdict(ref), prompt='External requirements')
    assert key == ref.key
    assert len(key) == 64
    assert not hasattr(factory, 'create_task')
    assert not hasattr(factory, 'create_issue')
    assert not hasattr(factory, 'task_store')
    assert factory.show_issue(key)['issue']['external_id'] == '100'
    assert 'id' not in factory.show_issue(key)['issue']


def test_refresh_updates_issue_cache_but_never_previous_run_requirements(factory):
    ref = IssueReference('github', 'owner/repo', '100')
    key = factory.import_issue(**asdict(ref), prompt='Original requirement')
    first = factory.run_issue(key, 'fixture')
    assert first['issue_key'] == ref.key
    assert factory.import_issue(**asdict(ref), prompt='Changed upstream requirement') == key
    second = factory.run_issue(key, 'fixture')
    assert factory.show_run(first['id'])['issue_snapshot']['prompt'] == 'Original requirement'
    assert second['issue_snapshot']['prompt'] == 'Changed upstream requirement'
    assert len(factory.issue_history()) == 1
    assert factory.issue_history()[0]['total_runs'] == 2
    assert factory.show_issue(key)['issue']['prompt'] == 'Changed upstream requirement'


def test_sqlite_has_no_task_tables_and_run_references_external_issue(tmp_path):
    factory = Factory(tmp_path)
    with factory._connect() as db:
        names = {row['name'] for row in db.execute("SELECT name FROM sqlite_master")}
        columns = {row['name'] for row in db.execute('PRAGMA table_info(runs)')}
    assert not any(name.startswith('task') for name in names)
    assert 'issue_key' in columns and 'issue_snapshot' in columns
    assert 'task_id' not in columns


def test_legacy_file_data_is_rejected_without_reset_or_new_state(tmp_path):
    original = tmp_path / 'tasks-v1'
    original.mkdir()
    canary = original / 'old-task.json'
    canary.write_text(json.dumps({'legacy': 'keep bytes'}))
    before = canary.read_bytes()
    with pytest.raises(StateConflict, match='Legacy Task'):
        open_factory(tmp_path)
    assert canary.read_bytes() == before
    assert not (tmp_path / 'issues-v2').exists()
    assert not (tmp_path / 'dashboard-v2').exists()


def test_independent_old_records_cannot_be_loaded_by_renaming_the_table(tmp_path):
    import sqlite3

    path = tmp_path / 'factory.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE issues(id TEXT PRIMARY KEY,prompt TEXT,created_at TEXT)')
        db.execute("INSERT INTO issues VALUES ('old-task','keep','old-time')")
    with pytest.raises(StateConflict, match='Unsupported Issue schema'):
        Factory(tmp_path)
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT * FROM issues').fetchall() == [('old-task', 'keep', 'old-time')]
