"""Non-invasive local checks for registered agent runtimes."""

from __future__ import annotations

import importlib.util
import shutil

from sf_factory.agent_registry import default_runtime_registry


def list_runtimes() -> list[dict[str, str | bool]]:
    """Check local prerequisites, not authentication or actual operability."""
    installed = {
        "codex": shutil.which("codex") is not None,
        "grok": shutil.which("grok") is not None,
        "copilot": (
            shutil.which("copilot") is not None
            and importlib.util.find_spec("copilot") is not None
        ),
    }
    return [
        {
            "name": name,
            "prerequisites_found": installed.get(name, False),
        }
        for name in default_runtime_registry().names()
    ]
