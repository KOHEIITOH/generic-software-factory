"""Fail-closed execution planning for AI code changes.

A plan is a description of requirements, never permission to execute.
Git worktrees alone do not provide process isolation.
"""

from __future__ import annotations

from dataclasses import dataclass

from sf_factory.agent_registry import AgentRuntimeRegistry
from sf_factory.execution_authorization import (
    AuthorizedOperation,
    ExecutionGrant,
    authorize_operation,
)


@dataclass(frozen=True)
class ImplementationPlan:
    task_id: str
    repository: str
    runtime: str
    ready: bool
    blockers: tuple[str, ...]


def plan_implementation(
    *,
    task_id: str,
    repository: str,
    runtime: str,
    registry: AgentRuntimeRegistry,
    grant: ExecutionGrant | None = None,
    process_isolated: bool = False,
) -> ImplementationPlan:
    """Validate prerequisites without starting any process or modifying files."""
    blockers: list[str] = []
    if not task_id.strip() or not repository.strip():
        blockers.append("Task ID and repository are required")
    if runtime not in registry.names():
        blockers.append("Runtime is not registered")
    if not process_isolated:
        blockers.append("OS process isolation is required; Git worktree alone is insufficient")
    if grant is None:
        blockers.append("Explicit task/repository-scoped implementation approval is required")
    else:
        try:
            authorize_operation(
                grant,
                task_id=task_id,
                repository=repository,
                operation=AuthorizedOperation.IMPLEMENT,
                isolated=process_isolated,
            )
        except PermissionError as exc:
            blockers.append(str(exc))
    return ImplementationPlan(
        task_id=task_id,
        repository=repository,
        runtime=runtime,
        ready=not blockers,
        blockers=tuple(blockers),
    )
