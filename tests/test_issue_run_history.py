"""Issue-centric read model preserves internal Issue identities and every Run."""
import pytest
from fastapi.testclient import TestClient

from sf_factory.agent_registry import AgentRuntimeRegistry
from sf_factory.factory import Factory
from sf_factory.file_dashboard import FileDashboardFactory
from sf_factory.runtime import RuntimeResult
from sf_factory.web_api import create_app


class FixtureRuntime:
    def execute(self, *, prompt, workspace, timeout_seconds):
        return RuntimeResult('fixture', 'succeeded', 'fixture observation', 0)


@pytest.fixture(params=[Factory, FileDashboardFactory])
def factory(request, tmp_path):
    registry = AgentRuntimeRegistry()
    registry.register('fixture', FixtureRuntime)
    return request.param(tmp_path, runtime_registry=registry)


def import_issue(factory, instance='example/repo', external_id='100'):
    return factory.import_issue(provider='github', instance=instance,
        external_id=external_id, prompt='Original requirement',
        external_url=f'https://github.com/{instance}/issues/{external_id}')


def test_issue_has_repeated_runs_without_duplicate_task(factory):
    issue = import_issue(factory)
    first = factory.run_issue(issue, 'fixture')
    second = factory.run_issue(issue, 'fixture')
    assert import_issue(factory) == issue
    rows = factory.issue_history()
    assert len(rows) == 1
    assert rows[0]['key'] == issue
    assert rows[0]['external_id'] == '100'
    assert rows[0]['total_runs'] == 2
    assert [r['id'] for r in rows[0]['recent_runs']] == [second['id'], first['id']]
    assert rows[0]['recent_runs'][0]['status'] == 'succeeded'
    assert 'output' not in rows[0]['recent_runs'][0]


def test_list_limit_applies_to_external_issue_snapshots(factory):
    first = import_issue(factory)
    second = import_issue(factory, instance='other/repo')
    assert [row['key'] for row in factory.issue_history(1)] == [second]
    assert len(factory.list_issues()) == 2
    assert factory.show_issue(first)['issue']['provider'] == 'github'


def test_run_history_is_per_issue_and_bounded_without_losing_total(factory):
    first = import_issue(factory)
    second = import_issue(factory, instance='other/repo')
    for _ in range(12):
        factory.run_issue(first, 'fixture')
    other_run = factory.run_issue(second, 'fixture')
    by_id = {row['key']: row for row in factory.issue_history()}
    assert by_id[first]['total_runs'] == 12
    assert len(by_id[first]['recent_runs']) == 10
    assert [r['id'] for r in by_id[second]['recent_runs']] == [other_run['id']]
    assert all(r['issue_key'] == first for r in by_id[first]['recent_runs'])


def test_issue_api_is_read_only_and_keeps_legacy_endpoints(factory):
    issue = import_issue(factory)
    run = factory.run_issue(issue, 'fixture')
    with TestClient(create_app(data_dir=factory.root)) as client:
        data = client.get('/api/issues').json()['issues']
        assert data[0]['recent_runs'][0]['id'] == run['id']
        assert client.post('/api/issues', json={}).status_code == 405
        assert client.get('/api/issues').json()['issues'][0]['key'] == issue
    assert len(factory.list_runs()) == 1


def test_empty_history_and_limit_validation(factory):
    assert factory.issue_history() == []
    for limit in (0, 101):
        with pytest.raises(ValueError):
            factory.issue_history(limit)
