"""Operator-authenticated jobs; all public dashboard routes remain non-executing."""
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from sf_factory.state_store import StateConflict, StatePermissionDenied
from sf_factory.web_jobs import WebJobs
from sf_factory.web_operator import OperatorProfiles, WebOperator


class SubmitStep(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    profile_id: str = Field(pattern='^[a-f0-9]{32}$')
    config_fingerprint: str = Field(pattern='^[a-f0-9]{64}$')
    request_id: str = Field(pattern='^[a-f0-9]{32}$')
    action: str = Field(pattern='^(plan|advance|review)$')
    confirm_run: bool
    confirm_bedrock: bool = False
    run_id: str | None = Field(default=None, pattern='^[a-f0-9]{32}$')
    reviewers: list[str] = Field(default_factory=list, max_length=16)


def install_execution_routes(app: FastAPI, root: Path, operator: WebOperator | None) -> None:
    def auth(request: Request):
        if operator is None:
            raise HTTPException(403, 'Execution disabled; start the local sf web launcher')
        operator.require(request)

    @app.get('/api/operator/status')
    def status():
        return {'enabled': operator is not None}

    @app.post('/api/operator/session')
    def session(request: Request, response: Response):
        if operator is None:
            raise HTTPException(403, 'Execution disabled')
        operator.exchange(request, response)
        return {'authenticated': True}

    @app.post('/api/operator/logout')
    def logout(request: Request, response: Response):
        auth(request)
        assert operator is not None
        operator.logout(request, response)
        return {'authenticated': False}

    @app.get('/api/operator/profiles')
    def profiles(request: Request):
        auth(request)
        return {'profiles': OperatorProfiles(root).list()}

    @app.get('/api/operator/jobs')
    def jobs(request: Request):
        auth(request)
        store = WebJobs(root)
        return {'jobs': [{**j, 'progress': store.progress(j['id'])} for j in store.list()[:50]]}

    @app.post('/api/operator/jobs', status_code=202)
    def submit(payload: SubmitStep, request: Request):
        auth(request)
        if payload.confirm_run is not True:
            raise HTTPException(403, 'Explicit scoped run consent required')
        store = WebJobs(root)
        try:
            job, created = store.enqueue(profile_id=payload.profile_id,
                config_fingerprint=payload.config_fingerprint, request_id=payload.request_id,
                action=payload.action, confirm_bedrock=payload.confirm_bedrock,
                run_id=payload.run_id, reviewers=tuple(payload.reviewers))
        except (StatePermissionDenied, ValueError, OSError) as exc:
            raise HTTPException(403, 'Registered scope or consent check failed') from exc
        if created:
            store.spawn(job['id'])
        return {'job': store.get(job['id'])}

    @app.post('/api/operator/jobs/{key}/stop')
    def stop(key: str, request: Request):
        auth(request)
        if len(key) != 32 or any(c not in '0123456789abcdef' for c in key):
            raise HTTPException(422, 'Exact job ID required')
        try:
            return {'job': WebJobs(root).stop(key)}
        except StateConflict as exc:
            raise HTTPException(409, 'Unknown job') from exc

    @app.middleware('http')
    async def private_operator_responses(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith('/api/operator'):
            response.headers['Cache-Control'] = 'no-store'
            response.headers['Referrer-Policy'] = 'no-referrer'
        return response
