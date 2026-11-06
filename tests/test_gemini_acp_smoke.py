"""Offline checks for the opt-in Gemini ACP smoke command."""

from pathlib import Path
from unittest.mock import patch

import pytest

from sf_factory.gemini_acp_smoke import run_gemini_acp_smoke
from sf_factory.runtime import RuntimeResult


def test_missing_gemini_returns_setup_error() -> None:
    with patch("sf_factory.gemini_acp_smoke.shutil.which", return_value=None):
        assert run_gemini_acp_smoke() == 2


def test_rejects_invalid_timeout() -> None:
    with pytest.raises(ValueError, match="timeout"):
        run_gemini_acp_smoke(timeout_seconds=0)


def test_smoke_uses_disposable_workspace() -> None:
    workspaces: list[Path] = []

    def execute(self, *, prompt, workspace, timeout_seconds=600):
        workspaces.append(workspace)
        assert workspace.is_dir()
        assert (workspace / "README.txt").is_file()
        assert "GEMINI_ACP_OK" in prompt
        assert self.command.argv == ("gemini", "--acp", "--approval-mode", "plan")
        return RuntimeResult(
            runtime="gemini-acp", status="succeeded", output="GEMINI_ACP_OK",
            exit_code=0,
        )

    with (
        patch("sf_factory.gemini_acp_smoke.shutil.which", return_value="/bin/gemini"),
        patch("sf_factory.gemini_acp_smoke.AcpRuntime.execute", execute),
    ):
        assert run_gemini_acp_smoke() == 0
    assert len(workspaces) == 1
    assert not workspaces[0].exists()
