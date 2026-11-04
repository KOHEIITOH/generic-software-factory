"""Opt-in localhost API for the Software Factory dashboard.

This module deliberately exposes read-only endpoints first. No agent execution,
filesystem browsing, or task mutation is available over HTTP.
"""

from __future__ import annotations

from fastapi import FastAPI

from sf_factory.agent_registry import default_runtime_registry


def create_app() -> FastAPI:
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

    return app


app = create_app()
