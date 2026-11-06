"""Sandbox preflight must never treat unavailable Docker as isolated."""

from __future__ import annotations

import subprocess
from unittest.mock import patch

from sf_factory.sandbox_preflight import docker_preflight


def test_missing_cli() -> None:
    with patch("sf_factory.sandbox_preflight.shutil.which", return_value=None):
        assert not docker_preflight().available


def test_daemon_failure() -> None:
    with (
        patch("sf_factory.sandbox_preflight.shutil.which", return_value="/usr/bin/docker"),
        patch(
            "sf_factory.sandbox_preflight.subprocess.run",
            return_value=subprocess.CompletedProcess([], 1, "", "denied"),
        ),
    ):
        assert not docker_preflight().available


def test_daemon_timeout() -> None:
    with (
        patch("sf_factory.sandbox_preflight.shutil.which", return_value="/usr/bin/docker"),
        patch(
            "sf_factory.sandbox_preflight.subprocess.run",
            side_effect=subprocess.TimeoutExpired("docker", 5),
        ),
    ):
        assert not docker_preflight().available


def test_daemon_reachable_does_not_claim_isolation() -> None:
    with (
        patch("sf_factory.sandbox_preflight.shutil.which", return_value="/usr/bin/docker"),
        patch(
            "sf_factory.sandbox_preflight.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, "27.0.0\n", ""),
        ),
    ):
        result = docker_preflight()
        assert result.available
        assert "not verified" in result.reason


def test_invalid_timeout_fails_closed() -> None:
    assert not docker_preflight(timeout_seconds=0).available
