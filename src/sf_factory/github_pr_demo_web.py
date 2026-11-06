"""GitHub demo HTTP adapter: origin/confirmation and response/error mapping only."""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi import Request as BrowserRequest
from pydantic import BaseModel, Field, StrictBool

from sf_factory.draft_pr_demo import create_draft_pr_demo
from sf_factory.integration_defaults import source_control
from sf_factory.source_control import SourceControlError


class DraftPRDemoRequest(BaseModel):
    repository: str = Field(min_length=3, max_length=200)
    confirmed: StrictBool = False


def install_github_pr_demo_routes(app: FastAPI) -> None:
    @app.post('/api/github/demo/draft-pr', status_code=201)
    def create_demo_pr(payload: DraftPRDemoRequest, request: BrowserRequest):
        origin = request.headers.get('origin', '').rstrip('/')
        if (origin != str(request.base_url).rstrip('/')
                or request.headers.get('sec-fetch-site') == 'cross-site'
                or request.headers.get('content-type', '').split(';')[0].strip()
                != 'application/json'):
            raise HTTPException(403, 'Same-origin JSON request required')
        try:
            result = create_draft_pr_demo(source_control(), payload.repository,
                                          confirmed=payload.confirmed)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except SourceControlError as exc:
            status = {'not_configured': 503, 'access_denied': 403,
                      'unavailable': 502, 'invalid_response': 502}[exc.kind]
            raise HTTPException(status, str(exc)) from exc
        return {'url': result.pull_request.url, 'number': int(result.pull_request.external_id),
                'branch': result.branch}
