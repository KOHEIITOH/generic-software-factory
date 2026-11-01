from pathlib import Path

from sf_factory.dev_smoke import run_dev_smoke
from sf_factory.runtime import RuntimeResult


class FakeRuntime:
    def __init__(self, *, unexpected: bool = False):
        self.unexpected = unexpected

    def execute(self, *, prompt: str, workspace: Path, timeout_seconds: int = 180):
        assert workspace.name.startswith("sf-dev-smoke-")
        assert (workspace / "test_calculator.py").exists()
        (workspace / "calculator.py").write_text(
            "def add(a: int, b: int) -> int:\\n    return a + b\\n".replace("\\n", "\n")
        )
        if self.unexpected:
            (workspace / "unexpected.txt").write_text("unapproved")
        return RuntimeResult(runtime="codex", status="succeeded", output="done", exit_code=0)


def test_dev_smoke_passes_with_single_allowed_edit() -> None:
    assert run_dev_smoke(runtime=FakeRuntime()) == 0


def test_dev_smoke_rejects_unexpected_edit() -> None:
    assert run_dev_smoke(runtime=FakeRuntime(unexpected=True)) == 1
