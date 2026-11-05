"""Regression tests for optional, additive local task/project links."""

import sqlite3
from pathlib import Path

import pytest

from sf_factory.factory import Factory
from sf_factory.local_project_registry import LocalProjectRegistry
from sf_factory.local_task_projects import LocalTaskProjects
from sf_factory.repository_contracts import Project


def test_existing_tasks_remain_unassigned_and_survive_restart(tmp_path: Path) -> None:
    factory = Factory(tmp_path)
    legacy = factory.create_task("legacy task")
    registry = LocalProjectRegistry(factory.db)
    registry.add_project(Project("p", "Local project", "local"))
    links = LocalTaskProjects(factory.db)
    assert links.project_for_task(legacy) is None
    links.assign(legacy, "p")
    assert LocalTaskProjects(factory.db).project_for_task(legacy) == "p"
    assert links.tasks_for_project("p") == (legacy,)
    assert Factory(tmp_path).show_task(legacy)["task"]["prompt"] == "legacy task"


def test_invalid_and_duplicate_associations_fail_closed(tmp_path: Path) -> None:
    factory = Factory(tmp_path)
    task = factory.create_task("work")
    registry = LocalProjectRegistry(factory.db)
    registry.add_project(Project("p", "Project", "local"))
    links = LocalTaskProjects(factory.db)
    with pytest.raises(sqlite3.IntegrityError):
        links.assign("missing", "p")
    with pytest.raises(sqlite3.IntegrityError):
        links.assign(task, "missing")
    links.assign(task, "p")
    with pytest.raises(sqlite3.IntegrityError):
        links.assign(task, "p")
    with pytest.raises(ValueError):
        links.assign(" ", "p")


def test_multiple_tasks_can_share_project(tmp_path: Path) -> None:
    factory = Factory(tmp_path)
    LocalProjectRegistry(factory.db).add_project(Project("p", "Project", "local"))
    links = LocalTaskProjects(factory.db)
    tasks = [factory.create_task("task A"), factory.create_task("task B")]
    for task in tasks:
        links.assign(task, "p")
    assert set(links.tasks_for_project("p")) == set(tasks)
