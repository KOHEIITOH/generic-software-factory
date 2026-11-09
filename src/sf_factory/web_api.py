"""Opt-in localhost API for the Software Factory dashboard.

Local dashboard endpoints. Mutations require same-origin browser requests.
Execution uses separately authenticated local operator routes and approved profiles.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from sf_factory.agent_registry import default_runtime_registry
from sf_factory.factory_selection import data_directory, open_factory
from sf_factory.repository_contracts import Project, Repository, Visibility
from sf_factory.state_store import StateConflict, StateUnavailable
from sf_factory.web_operator import WebOperator


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


def create_app(static_dir: Path | None = None, data_dir: Path | None = None,
               operator: WebOperator | None = None) -> FastAPI:
    data_dir = data_directory(data_dir)
    app = FastAPI(
        title="Software Factory Local API",
        description="Local dashboard API (experimental)",
        version="0.1.0",
        docs_url="/docs",
    )

    @app.exception_handler(StateUnavailable)
    def state_unavailable(request: Request, exc: StateUnavailable):
        return JSONResponse(status_code=503, content={
            "detail": "State storage is unavailable; existing data was not reset"
        })

    @app.exception_handler(StateConflict)
    def state_conflict(request: Request, exc: StateConflict):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.get("/api/integrations")
    def integrations() -> dict:
        from sf_factory.integration_defaults import describe_integrations

        return describe_integrations()

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/runtimes")
    def runtimes() -> dict[str, list[str]]:
        return {"runtimes": list(default_runtime_registry().names())}

    @app.get('/api/issues')
    def imported_issues() -> dict:
        return {'issues': open_factory(data_dir).issue_history()}

    @app.get('/api/runs')
    def runs() -> dict[str, list[dict]]:
        return {'runs': open_factory(data_dir or Path('.sf-factory')).list_runs()}

    @app.get("/api/projects")
    def projects() -> dict[str, list[dict[str, str]]]:
        factory = open_factory(data_dir or Path(".sf-factory"))
        registry = factory.project_registry()
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
        registry = open_factory(data_dir or Path(".sf-factory")).project_registry()
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
        registry = open_factory(data_dir or Path(".sf-factory")).project_registry()
        if not any(p.id == project_id for p in registry.list_projects("local")):
            raise HTTPException(status_code=404, detail="Project not found")
        repo = Repository(
            id=uuid4().hex, project_id=project_id, provider_id=provider_id,
            external_id=external_id, visibility=payload.visibility,
        )
        try:
            registry.add_repository(repo)
        except (sqlite3.IntegrityError, StateConflict):
            raise HTTPException(status_code=409, detail="Repository already registered")
        return {
            "id": repo.id, "project_id": repo.project_id,
            "provider_id": repo.provider_id, "external_id": repo.external_id,
            "visibility": repo.visibility.value,
        }

    @app.get("/api/projects/{project_id}/repositories")
    def project_repositories(project_id: str) -> dict[str, list[dict[str, str]]]:
        factory = open_factory(data_dir or Path(".sf-factory"))
        registry = factory.project_registry()
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

    from sf_factory.web_execution import install_execution_routes
    install_execution_routes(app, data_dir.resolve(), operator)

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
