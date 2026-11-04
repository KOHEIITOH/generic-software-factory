import importlib.util
import shutil

from sf_factory.cli import build_parser
from sf_factory.runtime_status import list_runtimes


def test_runtime_list_command_parses() -> None:
    args = build_parser().parse_args(["runtime", "list"])
    assert args.command == "runtime"
    assert args.runtime_command == "list"


def test_runtime_list_is_local_only(monkeypatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda executable: None)
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    runtimes = list_runtimes()
    assert {item["name"] for item in runtimes} == {"codex", "grok", "copilot"}
    assert all(item["prerequisites_found"] is False for item in runtimes)
