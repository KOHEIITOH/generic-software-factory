"""Operator-authenticated jobs; all public dashboard routes remain non-executing."""
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from sf_factory.state_store import StateConflict, StatePermissionDenied
from sf_factory.web_jobs import WebJobs
from sf_factory.web_operator import OperatorProfiles, WebOperator


class SubmitStep(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    profile_id: str = Field(pattern='^[a-f0-9]{32}$')
    config_fingerprint: str = Field(pattern='^[a-f0-9]{64}$')
    request_id: str = Field(pattern='^[a-f0-9]{32}$')
    action: str = Field(pattern='^(plan|advance|review|approve|develop)$')
    issue_id: str | None = Field(default=None, pattern='^[1-9][0-9]{0,18}$')
    approved_plan: str | None = Field(default=None, pattern='^[a-f0-9]{64}$')
    confirm_run: bool
    confirm_bedrock: bool = False
    run_id: str | None = Field(default=None, pattern='^[a-f0-9]{32}$')
    reviewers: list[str] = Field(default_factory=list, max_length=16)


class DiagnoseProfile(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    config_fingerprint: str = Field(pattern='^[a-f0-9]{64}$')
    check_remote: bool = False


class InspectSetup(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    root: str = Field(min_length=1, max_length=1000)
    repository: str = Field(default='', max_length=200)


class SetupCheck(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    id: str = Field(min_length=1, max_length=64)
    argv: list[str] = Field(min_length=1, max_length=128)
    stdout: str = Field(max_length=16384)


class CreateSetup(InspectSetup):
    name: str = Field(min_length=1, max_length=100)
    provider: str = Field(pattern='^(bedrock|copilot)$')
    image: str = Field(min_length=70, max_length=300)
    allowed_paths: list[str] = Field(min_length=1, max_length=32)
    checks: list[SetupCheck] = Field(min_length=1, max_length=16)
    issue: str = Field(default='1', pattern='^[1-9][0-9]{0,18}$')


class ApproveSetup(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    fingerprint: str = Field(pattern='^[a-f0-9]{64}$')
    confirmed: bool


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

    @app.post('/api/operator/setup/inspect')
    def inspect_setup(payload: InspectSetup, request: Request):
        auth(request)
        from sf_factory.operator_setup import inspect_repository
        try:
            return inspect_repository(Path(payload.root), payload.repository, root)
        except (ValueError, OSError) as exc:
            raise HTTPException(422, 'Clean Git root, origin and safe files required') from exc

    @app.post('/api/operator/setup/proposals', status_code=201)
    def create_setup(payload: CreateSetup, request: Request):
        auth(request)
        from sf_factory.behavioral_check import BehavioralCheck
        from sf_factory.operator_setup import SetupProposals
        try:
            return SetupProposals(root).initial(root=Path(payload.root),
                repository=payload.repository, name=payload.name, provider=payload.provider,
                image=payload.image, allowed_paths=tuple(payload.allowed_paths),
                checks=tuple(BehavioralCheck(c.id, tuple(c.argv), c.stdout)
                             for c in payload.checks), issue=payload.issue)
        except (ValueError, OSError) as exc:
            raise HTTPException(422, 'Invalid setup scope, Harness or checks') from exc

    @app.get('/api/operator/setup/proposals')
    def setup_proposals(request: Request):
        auth(request)
        from sf_factory.operator_setup import SetupProposals
        return {'proposals': SetupProposals(root).list()}

    @app.post('/api/operator/setup/proposals/{key}/approve')
    def approve_setup(key: str, payload: ApproveSetup, request: Request):
        auth(request)
        if payload.confirmed is not True:
            raise HTTPException(403, 'Explicit configuration and Harness approval required')
        from sf_factory.operator_setup import SetupProposals
        try:
            return SetupProposals(root).approve(key, payload.fingerprint)
        except (ValueError, OSError) as exc:
            raise HTTPException(422, 'Proposal cannot be installed; inspect again') from exc

    @app.post('/api/operator/profiles/{key}/diagnostics')
    def diagnostics(key: str, payload: DiagnoseProfile, request: Request):
        auth(request)
        if len(key) != 32 or any(c not in '0123456789abcdef' for c in key):
            raise HTTPException(422, 'Exact profile ID required')
        from sf_factory.operator_diagnostics import diagnose_profile
        return diagnose_profile(root, key, payload.config_fingerprint,
                                check_remote=payload.check_remote)

    @app.get('/api/operator/profiles/{key}/issues')
    def issues(key: str, request: Request, page: int = Query(default=1, ge=1, le=10000)):
        auth(request)
        from sf_factory.integration_defaults import list_open_issues
        try:
            _, config = OperatorProfiles(root).get(key)
            values, has_more = list_open_issues(config.repository, page)
        except (ValueError, StatePermissionDenied, OSError) as exc:
            raise HTTPException(403, 'Registered repository required') from exc
        except RuntimeError as exc:
            raise HTTPException(502, 'Issue list unavailable') from exc
        return {'page': page, 'has_more': has_more, 'issues': [
            {'id': issue.external_id, 'title': issue.prompt.splitlines()[0][:200],
             'url': issue.external_url} for issue in values]}

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
                run_id=payload.run_id, reviewers=tuple(payload.reviewers),
                approved_plan=payload.approved_plan, issue_id=payload.issue_id)
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
