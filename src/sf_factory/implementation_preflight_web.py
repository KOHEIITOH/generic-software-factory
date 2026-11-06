"""Read-only preflight for the future Issue -> AI implementation workflow.

This endpoint intentionally cannot start an agent or grant write permissions.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException

from sf_factory.agent_registry import default_runtime_registry
from sf_factory.factory_selection import open_factory
from sf_factory.policy import Capability, ExecutionPolicy, ExecutionRequest


def install_implementation_preflight_routes(app: FastAPI, data_dir) -> None:
    @app.get("/api/tasks/{task_id}/implementation-preflight")
    def implementation_preflight(task_id: str):
        factory = open_factory(data_dir)
        try:
            task = factory.task_repository(task_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Task not found") from exc
        blockers = []
        if task["provider"] != "github":
            blockers.append("GitHub Issue source required")
        if not task["repository"] or not task["local_path"]:
            blockers.append("Verified local repository binding required")
        elif task["instance"].casefold() != task["repository"].casefold():
            blockers.append("Issue and bound repository differ")
        policy = ExecutionPolicy()
        write = policy.evaluate(
            ExecutionRequest(capability=Capability.WORKSPACE_WRITE, approved=False)
        )
        if not write.allowed:
            blockers.append("Workspace write is disabled by default")
        external = policy.evaluate(
            ExecutionRequest(capability=Capability.EXTERNAL_ACTION, approved=False)
        )
        if not external.allowed:
            blockers.append("External GitHub actions are disabled by default")
        blockers.append("Isolated write-capable agent execution is not implemented")
        return {
            "task_id": task_id,
            "repository": task["repository"],
            "runtimes": list(default_runtime_registry().names()),
            "ready_for_implementation": False,
            "blockers": blockers,
            "execution_started": False,
        }
