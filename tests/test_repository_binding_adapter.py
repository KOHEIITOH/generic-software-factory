"""Core uses injected repository rules; initial GitHub behavior remains intact."""
import ast
from pathlib import Path

import pytest
from issue_fixtures import seed_issue

from sf_factory.factory import Factory
from sf_factory.file_dashboard import FileDashboardFactory


class FixtureBinding:
    def __init__(self):
        self.calls = []

    def verify(self, *, provider, instance, repository, local_path):
        self.calls.append((provider, instance, repository))
        if provider != 'fixture' or instance != repository:
            raise ValueError('fixture issue scope mismatch')
        return local_path.resolve(strict=True)


@pytest.fixture(params=[Factory, FileDashboardFactory])
def factory(request, tmp_path):
    binding = FixtureBinding()
    return request.param(tmp_path / 'data', repository_binding=binding), binding


def test_core_binds_using_provider_rules_without_github_assumptions(factory, tmp_path):
    service, binding = factory
    issue = service.import_issue(provider='fixture', instance='CaseSensitive/Scope',
                                        external_id='T-1', prompt='Keep provider-neutral')
    result = service.bind_issue_repository(issue, 'CaseSensitive/Scope', tmp_path)
    assert result['local_path'] == str(tmp_path.resolve())
    assert binding.calls == [('fixture', 'CaseSensitive/Scope', 'CaseSensitive/Scope')]
    row = next(row for row in service.list_issues() if row['key'] == issue)
    assert row['bound_repository'] == 'CaseSensitive/Scope'


def test_core_cannot_bypass_adapter_scope_check(factory, tmp_path):
    service, _ = factory
    issue = service.import_issue(provider='fixture', instance='Sensitive/Scope',
                                        external_id='T-1', prompt='Preserve scope')
    with pytest.raises(ValueError, match='scope mismatch'):
        service.bind_issue_repository(issue, 'sensitive/scope', tmp_path)
    assert service.issue_repository(issue)['repository'] is None


def test_unrelated_external_issue_cannot_bind_to_another_scope(factory, tmp_path):
    service, binding = factory
    issue = seed_issue(service, 'Local')
    with pytest.raises(ValueError, match='scope mismatch'):
        service.bind_issue_repository(issue, 'anything', tmp_path)
    assert binding.calls == [('fixture', 'fixture/repo', 'anything')]


def test_core_and_shared_workflows_do_not_import_github_adapters():
    root = Path(__file__).resolve().parents[1] / 'src/sf_factory'
    for name in ('factory', 'file_dashboard', 'workflow', 'workflow_runner', 'harness_runs',
                 'run_evidence', 'source_snapshot', 'draft_pr_demo', 'source_control'):
        tree = ast.parse((root / f'{name}.py').read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert 'github' not in (node.module or '').casefold(), name
            elif isinstance(node, ast.Import):
                assert all('github' not in alias.name.casefold() for alias in node.names), name
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert node.value != 'github', name
