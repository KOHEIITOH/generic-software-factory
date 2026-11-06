"""GitHub is selected without provider configuration; diagnostics never send secrets."""
import json
import sqlite3
import sys

import pytest
from fastapi.testclient import TestClient

from sf_factory.cli import main
from sf_factory.factory_selection import open_factory
from sf_factory.github_issues_source import GitHubIssuesSource
from sf_factory.github_repo_identity import GitHubRepositoryBinding
from sf_factory.github_source_control import GitHubSourceControl
from sf_factory.integration_defaults import (
    describe_integrations,
    repository_binding,
    source_control,
    task_source,
)
from sf_factory.task_sources import ExternalIssue, import_issue
from sf_factory.web_api import create_app


def test_initial_integration_factories_select_github(monkeypatch):
    monkeypatch.delenv('GH_TOKEN', raising=False)
    monkeypatch.delenv('GITHUB_TOKEN', raising=False)
    assert isinstance(repository_binding(), GitHubRepositoryBinding)
    assert isinstance(source_control(), GitHubSourceControl)
    assert isinstance(task_source('example/repo'), GitHubIssuesSource)
    config = describe_integrations()
    assert config['task_source'] == config['source_control'] == 'github'
    assert config['credentials']['configured'] is False
    assert config['credentials']['authenticated'] == 'not_checked'


@pytest.mark.parametrize('primary,fallback,expected', [
    ('first-test-only', 'second-test-only', 'first-test-only'),
    ('', 'second-test-only', 'second-test-only'),
    ('', '', None),
])
def test_existing_authentication_priority_and_secret_repr(monkeypatch, primary, fallback, expected):
    monkeypatch.setenv('GH_TOKEN', primary)
    monkeypatch.setenv('GITHUB_TOKEN', fallback)
    adapter = task_source('example/repo')
    assert isinstance(adapter, GitHubIssuesSource)
    assert adapter.token == expected
    for secret in (primary, fallback):
        if secret:
            assert secret not in repr(adapter)
            assert secret not in json.dumps(describe_integrations())
    assert describe_integrations()['credentials']['configured'] is bool(expected)


def test_default_task_source_reuses_neutral_import_contract(tmp_path, monkeypatch):
    factory = open_factory(tmp_path)
    def fetch(self, external_id):
        return ExternalIssue('github', self.repository, external_id, 'Default source task')
    monkeypatch.setattr(GitHubIssuesSource, 'fetch_issue', fetch)
    first = import_issue(factory, task_source('example/repo'), '7')
    second = import_issue(factory, task_source('example/repo'), '7')
    assert first == second
    assert factory.show_task(first)['task']['prompt'] == 'Default source task'


def test_diagnostics_are_read_only_without_database_or_network(tmp_path, monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        pytest.fail('diagnostics must not open a database or call GitHub')
    monkeypatch.setattr(sqlite3, 'connect', forbidden)
    monkeypatch.setattr('sf_factory.github_source_control.urlopen', forbidden)
    monkeypatch.setattr('sf_factory.github_issues_source.urlopen', forbidden)
    monkeypatch.setenv('GH_TOKEN', 'never-print-this-test-only')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, 'argv', ['sf', 'integration', 'show'])
    assert main() == 0
    printed = capsys.readouterr().out
    assert 'never-print-this-test-only' not in printed
    assert json.loads(printed)['source_control'] == 'github'
    with TestClient(create_app(data_dir=tmp_path / 'unused')) as client:
        response = client.get('/api/integrations')
        assert response.status_code == 200
        assert response.json()['credentials']['authenticated'] == 'not_checked'
        assert 'never-print-this-test-only' not in response.text
    assert list(tmp_path.iterdir()) == []
