"""One registry for all provider-neutral AgentRuntime implementations.

A registry chooses adapters; it does not grant additional permissions or
provide OS isolation. Callers must still enforce execution policy.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeAlias

from sf_factory.runtime import AgentRuntime

RuntimeFactory: TypeAlias = Callable[[], AgentRuntime]


class AgentRuntimeRegistry:
    """Map runtime names to lazily constructed adapters."""

    def __init__(self) -> None:
        self._factories: dict[str, RuntimeFactory] = {}

    def register(self, name: str, factory: RuntimeFactory) -> None:
        if not name or not name.strip() or name != name.strip():
            raise ValueError("runtime name must be non-empty and trimmed")
        if name in self._factories:
            raise ValueError(f"runtime already registered: {name}")
        self._factories[name] = factory

    def create(self, name: str) -> AgentRuntime:
        try:
            factory = self._factories[name]
        except KeyError:
            raise ValueError(f"unsupported runtime: {name}") from None
        return factory()

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories))


def default_runtime_registry() -> AgentRuntimeRegistry:
    """Register existing adapters without importing optional SDKs eagerly."""
    from sf_factory.codex_cli import CodexCliRuntime
    from sf_factory.copilot_sdk import CopilotSdkRuntime
    from sf_factory.grok_cli import GrokBuildCliRuntime

    registry = AgentRuntimeRegistry()
    registry.register("codex", lambda: CodexCliRuntime(sandbox="read-only"))
    registry.register("grok", GrokBuildCliRuntime)
    registry.register("copilot", CopilotSdkRuntime)
    return registry
