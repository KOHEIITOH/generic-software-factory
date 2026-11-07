"""Regression tests for optional, additive local issue/project links."""
import sqlite3
from pathlib import Path

import pytest
from issue_fixtures import seed_issue

from sf_factory.factory import Factory
from sf_factory.local_issue_projects import LocalIssueProjects
from sf_factory.local_project_registry import LocalProjectRegistry
from sf_factory.repository_contracts import Project


def test_existing_tasks_remain_unassigned_and_survive_restart(tmp_path: Path) -> None:
    factory = Factory(tmp_path)
    legacy = seed_issue(factory, "legacy issue")
    registry = LocalProjectRegistry(factory.db)
    registry.add_project(Project("p", "Local project", "local"))
    links = LocalIssueProjects(factory.db)
    assert links.project_for_issue(legacy) is None
    links.assign(legacy, "p")
    assert LocalIssueProjects(factory.db).project_for_issue(legacy) == "p"
    assert links.issues_for_project("p") == (legacy,)
    assert Factory(tmp_path).show_issue(legacy)["issue"]["prompt"] == "legacy issue"


def test_invalid_and_duplicate_associations_fail_closed(tmp_path: Path) -> None:
    factory = Factory(tmp_path)
    issue = seed_issue(factory, "work")
    registry = LocalProjectRegistry(factory.db)
    registry.add_project(Project("p", "Project", "local"))
    links = LocalIssueProjects(factory.db)
    with pytest.raises(sqlite3.IntegrityError):
        links.assign("missing", "p")
    with pytest.raises(sqlite3.IntegrityError):
        links.assign(issue, "missing")
    links.assign(issue, "p")
    with pytest.raises(sqlite3.IntegrityError):
        links.assign(issue, "p")
    with pytest.raises(ValueError):
        links.assign(" ", "p")


def test_multiple_tasks_can_share_project(tmp_path: Path) -> None:
    factory = Factory(tmp_path)
    LocalProjectRegistry(factory.db).add_project(Project("p", "Project", "local"))
    links = LocalIssueProjects(factory.db)
    issues = [seed_issue(factory, "issue A"), seed_issue(factory, "issue B")]
    for issue in issues:
        links.assign(issue, "p")
    assert set(links.issues_for_project("p")) == set(issues)
