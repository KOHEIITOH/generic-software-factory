"""Browser capabilities cannot approve paths or mutate registered scope."""
import json
from dataclasses import asdict

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient
from test_issue_development import flow as flow

from sf_factory.state_store import StatePermissionDenied
from sf_factory.web_operator import OperatorProfiles, WebOperator

ORIGIN = 'http://127.0.0.1:8000'
HEADERS = {'origin': ORIGIN, 'x-sf-operator': '1'}


def operator_app(auth):
    app = FastAPI()
    @app.post('/api/operator/session')
    def session(request: Request, response: Response):
        auth.exchange(request, response)
        return {'authenticated': True}
    @app.post('/api/operator/logout')
    def logout(request: Request, response: Response):
        auth.logout(request, response)
        return {'authenticated': False}
    @app.get('/api/operator/profiles')
    def profiles(request: Request):
        auth.require(request)
        return {'profiles': []}
    return app


def test_short_lived_cookie_session_logout_and_restart_revoke_capability():
    now = [0]
    auth = WebOperator(ORIGIN, clock=lambda: now[0])
    with TestClient(operator_app(auth), base_url=ORIGIN) as client:
        assert client.get('/api/operator/profiles', headers=HEADERS).status_code == 401
        login = client.post('/api/operator/session', headers={**HEADERS,
                             'authorization': 'Bearer ' + auth.token})
        cookie = login.headers['set-cookie'].lower()
        assert 'httponly' in cookie and 'samesite=strict' in cookie
        assert 'no-store' == login.headers['cache-control']
        assert client.get('/api/operator/profiles', headers=HEADERS).status_code == 200
        auth._sessions.clear()  # A new server owns no previous browser sessions.
        assert client.get('/api/operator/profiles', headers=HEADERS).status_code == 401
        client.post('/api/operator/session', headers={**HEADERS,
                    'authorization': 'Bearer ' + auth.token})
        now[0] = 28801
        assert client.get('/api/operator/profiles', headers=HEADERS).status_code == 401
        client.post('/api/operator/session', headers={**HEADERS,
                    'authorization': 'Bearer ' + auth.token})
        assert client.post('/api/operator/logout', headers=HEADERS).status_code == 200
        assert client.get('/api/operator/profiles', headers=HEADERS).status_code == 401


@pytest.mark.parametrize('headers', [
    {}, {'origin': 'https://evil.invalid', 'x-sf-operator': '1'},
    {'origin': ORIGIN}, {**HEADERS, 'sec-fetch-site': 'cross-site'},
    {**HEADERS, 'host': 'evil.invalid'},
])
def test_even_root_token_cannot_bypass_host_origin_and_custom_header(headers):
    auth = WebOperator(ORIGIN)
    with TestClient(operator_app(auth), base_url=ORIGIN) as client:
        response = client.post('/api/operator/session', headers={**headers,
                               'authorization': 'Bearer ' + auth.token})
        assert response.status_code == 403


def test_bad_tokens_are_rate_limited():
    auth = WebOperator(ORIGIN)
    with TestClient(operator_app(auth), base_url=ORIGIN) as client:
        for _ in range(10):
            assert client.post('/api/operator/session', headers=HEADERS).status_code == 403
        assert client.post('/api/operator/session', headers=HEADERS).status_code == 429


def config_file(flow):
    path = flow['config'].root.parent / 'operator.json'
    path.write_text(json.dumps(asdict(flow['config']), default=str))
    return path


def test_only_local_registration_allows_exact_unchanged_scope_and_revocation(flow):
    registry = OperatorProfiles(flow['factory'].root)
    path = config_file(flow)
    profile = registry.register(path, 'My repository')
    assert registry.get(profile['id'])[1] == flow['config']
    assert 'path' not in registry.list()[0]
    value = json.loads(path.read_text())
    value['issue'] = '2'
    path.write_text(json.dumps(value))
    with pytest.raises(StatePermissionDenied):
        registry.get(profile['id'])
    assert registry.list()[0]['available'] is False
    registry.register(path, 'Updated locally')
    registry.revoke(profile['id'])
    with pytest.raises(StatePermissionDenied):
        registry.get(profile['id'])


def test_other_dashboard_root_cannot_use_profile_and_repo_cannot_supply_config(flow):
    path = config_file(flow)
    with pytest.raises(StatePermissionDenied):
        OperatorProfiles(path.parent / 'other').register(path, 'Wrong data root')
    inside = flow['config'].root / 'config.json'
    inside.write_text(path.read_text())
    with pytest.raises(PermissionError):
        OperatorProfiles(flow['factory'].root).register(inside, 'Untrusted')


def test_real_browser_same_origin_get_without_origin_header_uses_cookie():
    auth = WebOperator(ORIGIN)
    with TestClient(operator_app(auth), base_url=ORIGIN) as client:
        client.post('/api/operator/session', headers={**HEADERS,
                    'authorization': 'Bearer ' + auth.token})
        response = client.get('/api/operator/profiles', headers={
            'sec-fetch-site': 'same-origin', 'x-sf-operator': '1'})
        assert response.status_code == 200
        assert client.get('/api/operator/profiles', headers={
            'sec-fetch-site': 'cross-site', 'x-sf-operator': '1'}).status_code == 403


def test_reopening_operator_link_rotates_same_browser_without_leaking_session_slots():
    auth = WebOperator(ORIGIN)
    with TestClient(operator_app(auth), base_url=ORIGIN) as client:
        for _ in range(20):
            assert client.post('/api/operator/session', headers={**HEADERS,
                'authorization': 'Bearer ' + auth.token}).status_code == 200
        assert len(auth._sessions) == 1
        assert client.get('/api/operator/profiles', headers=HEADERS).status_code == 200
