"""Common demo orchestration depends on capabilities and opaque SCM identities."""
import pytest

from sf_factory.draft_pr_demo import create_draft_pr_demo
from sf_factory.repository_contracts import RepositoryCapabilities
from sf_factory.source_control import PullRequestReference, RepositoryInfo, SourceControlError


class FixtureSourceControl:
    def __init__(self, writable=True, fail_write=False):
        self.writable, self.fail_write = writable, fail_write
        self.calls = []

    def describe_repository(self, repository):
        self.calls.append('describe')
        assert repository == 'opaque:repository'
        return RepositoryInfo(repository, 'default', RepositoryCapabilities(
            read=True, write=self.writable, pull_request=self.writable,
        ))

    def branch_revision(self, repository, branch):
        self.calls.append('revision')
        assert repository == 'opaque:repository'
        assert branch == 'default'
        return 'opaque-revision'

    def create_branch(self, repository, branch, revision):
        self.calls.append('branch')
        assert revision == 'opaque-revision'

    def write_file(self, repository, *, branch, path, content, message):
        self.calls.append('write')
        assert path == f'.sf-factory-demo/{branch}.md'
        assert b'No AI or application code was changed' in content
        if self.fail_write:
            raise SourceControlError('unavailable', 'fixture failure')

    def create_draft_pull_request(self, repository, *, title, head, base, body):
        self.calls.append('draft')
        assert base == 'default'
        return PullRequestReference('opaque-pr', 'https://fixture.invalid/pr/opaque')


def test_common_workflow_accepts_non_github_identifiers():
    adapter = FixtureSourceControl()
    result = create_draft_pr_demo(adapter, 'opaque:repository', confirmed=True)
    assert result.pull_request.external_id == 'opaque-pr'
    assert adapter.calls == ['describe', 'revision', 'branch', 'write', 'draft']


@pytest.mark.parametrize('confirmation', [False, 1, 'yes', None])
def test_confirmation_required_before_any_adapter_call(confirmation):
    adapter = FixtureSourceControl()
    with pytest.raises(ValueError):
        create_draft_pr_demo(adapter, 'opaque:repository', confirmed=confirmation)
    assert adapter.calls == []


def test_permission_denial_prevents_all_mutations():
    adapter = FixtureSourceControl(writable=False)
    with pytest.raises(SourceControlError) as error:
        create_draft_pr_demo(adapter, 'opaque:repository', confirmed=True)
    assert error.value.kind == 'access_denied'
    assert adapter.calls == ['describe']


def test_partial_failure_never_attempts_pr_or_retries():
    adapter = FixtureSourceControl(fail_write=True)
    with pytest.raises(SourceControlError):
        create_draft_pr_demo(adapter, 'opaque:repository', confirmed=True)
    assert adapter.calls == ['describe', 'revision', 'branch', 'write']
