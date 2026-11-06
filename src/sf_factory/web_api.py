"""Opt-in localhost API for the Software Factory dashboard.

Local dashboard endpoints. Mutations require same-origin browser requests.
Agent execution and arbitrary filesystem browsing are not exposed over HTTP.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from sf_factory.agent_registry import default_runtime_registry
from sf_factory.factory import Factory
from sf_factory.github_issue_web import install_github_issue_routes
from sf_factory.github_repository_web import install_github_repository_routes
from sf_factory.github_pr_demo_web import install_github_pr_demo_routes
from sf_factory.local_project_registry import LocalProjectRegistry
from sf_factory.repo_discovery import discover_git_root
from sf_factory.repository_contracts import Project, Repository, Visibility


class InspectRepositoryRequest(BaseModel):
    path: str = Field(min_length=1, max_length=1000)


class BindTaskRepositoryRequest(BaseModel):
    repository: str = Field(min_length=3, max_length=200)
    local_path: str = Field(min_length=1, max_length=1000)


class CreateTaskRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=10000)


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class CreateRepositoryRequest(BaseModel):
    provider_id: str = Field(min_length=1, max_length=80)
    external_id: str = Field(min_length=1, max_length=500)
    visibility: Visibility


def _check_local_origin(request: Request) -> None:
    # The local dashboard has no authentication. Reject browser cross-origin writes.
    origin = request.headers.get("origin")
    if not origin or origin.rstrip("/") != str(request.base_url).rstrip("/"):
        raise HTTPException(status_code=403, detail="Same-origin browser request required")
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(status_code=403, detail="Cross-site request rejected")


def create_app(static_dir: Path | None = None, data_dir: Path | None = None) -> FastAPI:
    app = FastAPI(
        title="Software Factory Local API",
        description="Local dashboard API (experimental)",
        version="0.1.0",
        docs_url="/docs",
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/quick/repository")
    def quick_repository() -> dict[str, str | bool | None]:
        # Only the directory where the server was launched is considered.
        # No user-supplied filesystem path or repository content is accepted.
        try:
            root = discover_git_root(Path.cwd())
        except (OSError, ValueError):
            return {"detected": False, "repository_root": None, "provider": None}
        return {"detected": True, "repository_root": str(root), "provider": "local-git"}

    @app.post("/api/quick/repository/inspect")
    def inspect_quick_repository(
        payload: InspectRepositoryRequest, request: Request
    ) -> dict[str, str]:
        _check_local_origin(request)
        try:
            root = discover_git_root(Path(payload.path))
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"repository_root": str(root), "provider": "local-git"}

    @app.get("/api/runtimes")
    def runtimes() -> dict[str, list[str]]:
        return {"runtimes": list(default_runtime_registry().names())}

    @app.get('/api/tasks')
    def tasks() -> dict[str, list[dict]]:
        return {'tasks': Factory(data_dir or Path('.sf-factory')).list_tasks()}

    @app.get('/api/runs')
    def runs() -> dict[str, list[dict]]:
        return {'runs': Factory(data_dir or Path('.sf-factory')).list_runs()}

    @app.post("/api/tasks", status_code=201)
    def create_task(payload: CreateTaskRequest, request: Request) -> dict[str, str]:
        _check_local_origin(request)
        prompt = payload.prompt.strip()
        if not prompt:
            raise HTTPException(status_code=422, detail="Task must not be blank")
        task_id = Factory(data_dir or Path(".sf-factory")).create_task(prompt)
        return {"task_id": task_id}


    @app.post("/api/tasks/{task_id}/repository")
    def bind_task_repository(
        task_id: str, payload: BindTaskRepositoryRequest, request: Request
    ) -> dict[str, str]:
        _check_local_origin(request)
        try:
            return Factory(data_dir or Path(".sf-factory")).bind_task_repository(
                task_id, payload.repository, Path(payload.local_path)
            )
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/projects")
    def projects() -> dict[str, list[dict[str, str]]]:
        factory = Factory(data_dir or Path(".sf-factory"))
        registry = LocalProjectRegistry(factory.db)
        return {
            "projects": [
                {"id": p.id, "name": p.name, "owner_id": p.owner_id}
                for p in registry.list_projects("local")
            ]
        }

    @app.post("/api/projects", status_code=201)
    def create_project(payload: CreateProjectRequest, request: Request) -> dict[str, str]:
        _check_local_origin(request)
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="Project name must not be blank")
        registry = LocalProjectRegistry(Factory(data_dir or Path(".sf-factory")).db)
        project = Project(id=uuid4().hex, name=name, owner_id="local")
        registry.add_project(project)
        return {"id": project.id, "name": project.name, "owner_id": project.owner_id}

    @app.post("/api/projects/{project_id}/repositories", status_code=201)
    def create_project_repository(
        project_id: str, payload: CreateRepositoryRequest, request: Request
    ) -> dict[str, str]:
        _check_local_origin(request)
        provider_id, external_id = payload.provider_id.strip(), payload.external_id.strip()
        if not provider_id or not external_id:
            raise HTTPException(status_code=422, detail="Repository fields must not be blank")
        registry = LocalProjectRegistry(Factory(data_dir or Path(".sf-factory")).db)
        if not any(p.id == project_id for p in registry.list_projects("local")):
            raise HTTPException(status_code=404, detail="Project not found")
        repo = Repository(
            id=uuid4().hex, project_id=project_id, provider_id=provider_id,
            external_id=external_id, visibility=payload.visibility,
        )
        try:
            registry.add_repository(repo)
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="Repository already registered")
        return {
            "id": repo.id, "project_id": repo.project_id,
            "provider_id": repo.provider_id, "external_id": repo.external_id,
            "visibility": repo.visibility.value,
        }

    @app.get("/api/projects/{project_id}/repositories")
    def project_repositories(project_id: str) -> dict[str, list[dict[str, str]]]:
        factory = Factory(data_dir or Path(".sf-factory"))
        registry = LocalProjectRegistry(factory.db)
        if not any(p.id == project_id for p in registry.list_projects("local")):
            raise HTTPException(status_code=404, detail="Project not found")
        return {
            "repositories": [
                {
                    "id": repo.id,
                    "project_id": repo.project_id,
                    "provider_id": repo.provider_id,
                    "external_id": repo.external_id,
                    "visibility": repo.visibility.value,
                }
                for repo in registry.list_repositories(project_id)
            ]
        }

    install_github_issue_routes(app, data_dir)
    install_github_repository_routes(app)
    install_github_pr_demo_routes(app)

    if static_dir is not None:
        project_root = Path(__file__).resolve().parents[2]

        @app.get("/guide", include_in_schema=False)
        def user_guide() -> FileResponse:
            return FileResponse(project_root / "USER_GUIDE.html", media_type="text/html")

        @app.get("/onboarding", include_in_schema=False)
        def onboarding() -> FileResponse:
            return FileResponse(project_root / "ONBOARDING.html", media_type="text/html")

    if static_dir is not None:
        if not (static_dir / 'index.html').is_file():
            raise ValueError('Dashboard build not found')
        app.mount('/assets', StaticFiles(directory=static_dir / 'assets'), name='assets')

        @app.get('/', include_in_schema=False)
        def dashboard() -> FileResponse:
            return FileResponse(static_dir / 'index.html')

    return app


app = create_app()
