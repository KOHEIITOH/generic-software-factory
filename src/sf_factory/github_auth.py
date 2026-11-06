"""Shared GitHub adapter credentials; never serialize tokens into configuration."""
from __future__ import annotations

import os

CREDENTIAL_ENVIRONMENT = ('GH_TOKEN', 'GITHUB_TOKEN')


def environment_token() -> str | None:
    return os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN') or None


def credential_status() -> dict:
    return {'environment_variables': list(CREDENTIAL_ENVIRONMENT),
            'configured': bool(environment_token()), 'authenticated': 'not_checked'}
