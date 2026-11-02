from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from sf_factory.repo_analysis import analyze_repository
from sf_factory.runtime import RuntimeResult


def _git_repo(path: Path) -> Path:
    path.mkdir()
    (path / ".git").mkdir()
    return path


def test_analysis_sends_only_bounded_snapshot_in_empty_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _git_repo(tmp_path / "repo")
    (repo / "README.md").write_text("# Example\n", encoding="utf-8")
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("print('hello')\n", encoding="utf-8")
    (repo / ".env").write_text("TOKEN=do-not-send", encoding="utf-8")
    (repo / "private.key").write_text("private-key", encoding="utf-8")
    (repo / "notes.bin").write_bytes(b"\x00secret")
    (repo / "node_modules").mkdir()
    (repo / "node_modules" / "module.py").write_text("not included", encoding="utf-8")

    outside = tmp_path / "outside.py"
    outside.write_text("outside the selected repository", encoding="utf-8")
    (repo / "linked.py").symlink_to(outside)
    (repo / "linked-dir").symlink_to(tmp_path, target_is_directory=True)

    calls: list[tuple[str, Path, int]] = []

    def fake_execute(
        self: Any, *, prompt: str, workspace: Path, timeout_seconds: int = 600
    ) -> RuntimeResult:
        assert list(workspace.iterdir()) == []
        calls.append((prompt, workspace, timeout_seconds))
        return RuntimeResult(
            runtime="copilot",
            status="succeeded",
            output="Repository overview",
            exit_code=0,
        )

    monkeypatch.setattr("sf_factory.copilot_sdk.CopilotSdkRuntime.execute", fake_execute)

    result = analyze_repository(repo, timeout_seconds=23, confirm_send=True)

    assert result.files_included == ("README.md", "src/app.py")
    assert set(result.exclusions) >= {
        "directories",
        "sensitive_names",
        "symlinks",
        "unsupported_files",
    }
    prompt, workspace, timeout = calls[0]
    snapshot = json.loads(prompt.split("The JSON snapshot follows:\n", maxsplit=1)[1])
    assert [item["path"] for item in snapshot["files"]] == ["README.md", "src/app.py"]
    assert "do-not-send" not in prompt
    assert "outside the selected repository" not in prompt
    assert timeout == 23
    assert workspace.name.startswith("sf-repo-analysis-")


def test_analysis_requires_explicit_send_confirmation(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path / "repo")
    (repo / "README.md").write_text("read me", encoding="utf-8")

    with pytest.raises(ValueError, match="--confirm-send"):
        analyze_repository(repo)


def test_analysis_rejects_non_repository_root(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Git repository root"):
        analyze_repository(tmp_path, confirm_send=True)


def test_analysis_excludes_oversized_files_and_reports_limits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _git_repo(tmp_path / "repo")
    (repo / "a.md").write_text("small", encoding="utf-8")
    (repo / "b.py").write_text("x" * 20, encoding="utf-8")
    calls: list[str] = []

    def fake_execute(
        self: Any, *, prompt: str, workspace: Path, timeout_seconds: int = 600
    ) -> RuntimeResult:
        calls.append(prompt)
        return RuntimeResult(
            runtime="copilot",
            status="succeeded",
            output="Analysis",
            exit_code=0,
        )

    monkeypatch.setattr("sf_factory.repo_analysis.MAX_FILE_BYTES", 10)
    monkeypatch.setattr("sf_factory.copilot_sdk.CopilotSdkRuntime.execute", fake_execute)

    result = analyze_repository(repo, confirm_send=True)

    assert result.files_included == ("a.md",)
    assert result.exclusions["oversized_files"] == 1
    snapshot = json.loads(calls[0].split("The JSON snapshot follows:\n", maxsplit=1)[1])
    assert snapshot["exclusions"]["oversized_files"] == 1


def test_analysis_reports_file_count_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _git_repo(tmp_path / "repo")
    (repo / "a.md").write_text("a", encoding="utf-8")
    (repo / "b.md").write_text("b", encoding="utf-8")

    def fake_execute(
        self: Any, *, prompt: str, workspace: Path, timeout_seconds: int = 600
    ) -> RuntimeResult:
        return RuntimeResult(
            runtime="copilot",
            status="succeeded",
            output="Analysis",
            exit_code=0,
        )

    monkeypatch.setattr("sf_factory.repo_analysis.MAX_FILES", 1)
    monkeypatch.setattr("sf_factory.copilot_sdk.CopilotSdkRuntime.execute", fake_execute)

    result = analyze_repository(repo, confirm_send=True)

    assert result.files_included == ("a.md",)
    assert result.limits_reached == ("file_count",)


def test_analysis_reports_total_byte_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _git_repo(tmp_path / "repo")
    (repo / "a.md").write_text("abc", encoding="utf-8")
    (repo / "b.md").write_text("de", encoding="utf-8")

    def fake_execute(
        self: Any, *, prompt: str, workspace: Path, timeout_seconds: int = 600
    ) -> RuntimeResult:
        return RuntimeResult(
            runtime="copilot",
            status="succeeded",
            output="Analysis",
            exit_code=0,
        )

    monkeypatch.setattr("sf_factory.repo_analysis.MAX_TOTAL_BYTES", 4)
    monkeypatch.setattr("sf_factory.copilot_sdk.CopilotSdkRuntime.execute", fake_execute)

    result = analyze_repository(repo, confirm_send=True)

    assert result.files_included == ("a.md",)
    assert result.bytes_included == 3
    assert result.limits_reached == ("total_bytes",)


def test_analysis_does_not_follow_symlinked_git_metadata(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").symlink_to(tmp_path, target_is_directory=True)

    with pytest.raises(ValueError, match="invalid .git entry"):
        analyze_repository(repo, confirm_send=True)


@pytest.mark.skipif(not hasattr(os, "O_NOFOLLOW"), reason="no-follow open is unavailable")
def test_analysis_does_not_include_symlink_targets(tmp_path: Path, monkeypatch) -> None:
    repo = _git_repo(tmp_path / "repo")
    target = tmp_path / "outside.md"
    target.write_text("outside content", encoding="utf-8")
    (repo / "link.md").symlink_to(target)
    (repo / "inside.md").write_text("inside content", encoding="utf-8")
    prompts: list[str] = []

    def fake_execute(
        self: Any, *, prompt: str, workspace: Path, timeout_seconds: int = 600
    ) -> RuntimeResult:
        prompts.append(prompt)
        return RuntimeResult(
            runtime="copilot",
            status="succeeded",
            output="Analysis",
            exit_code=0,
        )

    monkeypatch.setattr("sf_factory.copilot_sdk.CopilotSdkRuntime.execute", fake_execute)

    result = analyze_repository(repo, confirm_send=True)

    assert result.files_included == ("inside.md",)
    assert result.exclusions["symlinks"] == 1
    assert "outside content" not in prompts[0]
