"""Preflight is pure, conservative, and never performs an action."""
from pathlib import Path

from sf_factory.execution_guard import GuardStatus, preflight
from sf_factory.risk_policy import ActionContext, Environment, Operation


def safe_action(operation=Operation.WRITE_FILE):
    return ActionContext(operation, Environment.ISOLATED, True, True, True)


def test_safe_workspace_file_is_preflight_ready(tmp_path: Path):
    result = preflight(safe_action(), workspace=tmp_path, target=tmp_path / "new.txt")
    assert result.status is GuardStatus.READY
    assert result.executable
    assert not (tmp_path / "new.txt").exists()


def test_reject_missing_target(tmp_path: Path):
    result = preflight(safe_action(), workspace=tmp_path)
    assert result.status is GuardStatus.DENIED


def test_reject_path_traversal(tmp_path: Path):
    result = preflight(safe_action(), workspace=tmp_path, target=tmp_path / ".." / "escape")
    assert result.status is GuardStatus.DENIED


def test_reject_symlink_escape(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)
    result = preflight(safe_action(), workspace=root, target=root / "link" / "file")
    assert result.status is GuardStatus.DENIED


def test_reject_relative_path(tmp_path: Path):
    result = preflight(safe_action(), workspace=tmp_path, target=Path("file"))
    assert result.status is GuardStatus.DENIED


def test_reject_workspace_root(tmp_path: Path):
    result = preflight(safe_action(), workspace=tmp_path, target=tmp_path)
    assert result.status is GuardStatus.DENIED


def test_sensitive_operation_never_auto(tmp_path: Path):
    result = preflight(
        ActionContext(Operation.MERGE_PR, Environment.PRODUCTION),
        workspace=tmp_path,
    )
    assert result.status is GuardStatus.APPROVAL_REQUIRED
    assert not result.executable


def test_unknown_command_denied(tmp_path: Path):
    result = preflight(safe_action(Operation.RUN_COMMAND), workspace=tmp_path)
    assert result.status is GuardStatus.DENIED
