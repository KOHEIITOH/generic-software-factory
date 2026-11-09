"""Retired routes cannot read credentials, inspect paths, or create remote resources."""
import pytest
from fastapi.testclient import TestClient

from sf_factory.web_api import create_app


@pytest.mark.parametrize('serve_dashboard', [False, True])
def test_obsolete_routes_are_absent_from_http_and_openapi(tmp_path, monkeypatch, serve_dashboard):
    def forbidden(*args, **kwargs):
        pytest.fail('retired endpoint must not invoke an integration')
    monkeypatch.setattr('sf_factory.github_issues_source.GitHubIssuesSource.from_environment',
                        forbidden)
    monkeypatch.setattr('sf_factory.integration_defaults.source_control', forbidden)
    monkeypatch.setattr('sf_factory.repo_discovery.discover_git_root', forbidden)
    static = None
    if serve_dashboard:
        static = tmp_path / 'dist'
        (static / 'assets').mkdir(parents=True)
        (static / 'index.html').write_text('<html>dashboard</html>')
    paths = [('/api/quick/repository', 'get'), ('/api/quick/repository/inspect', 'post'),
             ('/api/github/repositories', 'get'), ('/api/github/issues', 'get'),
             ('/api/github/issue', 'get'), ('/api/github/import', 'post'),
             ('/api/github/demo/draft-pr', 'post'),
             ('/api/issues/fixture/repository', 'post'),
             ('/api/issues/fixture/implementation-preflight', 'get')]
    with TestClient(create_app(static_dir=static, data_dir=tmp_path / 'data')) as client:
        for path, method in paths:
            response = client.request(method, path, headers={'Origin': 'http://testserver'},
                params={'repository': 'owner/repo', 'number': 1},
                json={'repository': 'owner/repo', 'number': 1, 'confirmed': True,
                      'path': str(tmp_path), 'local_path': str(tmp_path)})
            assert response.status_code == 404, path
        schema = client.get('/openapi.json').json()['paths']
        assert not any('/quick/' in p or '/github/' in p or 'preflight' in p for p in schema)
        assert '/api/issues/{issue_key}/repository' not in schema
        assert '/api/operator/profiles/{key}/issues' in schema
        assert '/api/operator/profiles/{key}/diagnostics' in schema
        assert '/api/operator/jobs' in schema
        assert '/api/projects' in schema
        assert client.get('/api/health').json() == {'status': 'ok'}
