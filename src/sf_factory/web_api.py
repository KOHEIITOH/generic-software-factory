"""Opt-in localhost API for the Software Factory dashboard.

This module deliberately exposes read-only endpoints first. No agent execution,
filesystem browsing, or task mutation is available over HTTP.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from sf_factory.agent_registry import default_runtime_registry
from sf_factory.factory import Factory


def create_app(static_dir: Path | None = None, data_dir: Path | None = None) -> FastAPI:
    app = FastAPI(
        title="Software Factory Local API",
        description="Read-only local dashboard API (experimental)",
        version="0.1.0",
        docs_url="/docs",
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/runtimes")
    def runtimes() -> dict[str, list[str]]:
        return {"runtimes": list(default_runtime_registry().names())}

    @app.get('/api/tasks')
    def tasks() -> dict[str, list[dict]]:
        return {'tasks': Factory(data_dir or Path('.sf-factory')).list_tasks()}

    @app.get('/api/runs')
    def runs() -> dict[str, list[dict]]:
        return {'runs': Factory(data_dir or Path('.sf-factory')).list_runs()}

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
