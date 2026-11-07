"""Explicit, read-only model-assisted issue analysis (no code execution)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sf_factory.context_builder import ContextSelection, build_context
from sf_factory.model_provider import ModelProvider, ModelResponse
from sf_factory.usage_tracker import UsageTracker


@dataclass(frozen=True)
class AnalysisResult:
    response: ModelResponse
    context: ContextSelection


def analyze_issue(
    issue_key: str,
    instruction: str,
    workspace: Path,
    paths: list[str],
    provider: ModelProvider,
    *,
    max_characters: int = 12000,
    tracker: UsageTracker | None = None,
) -> AnalysisResult:
    """Send explicitly selected files to a provider; inference may incur charges.

    The caller must review file paths for secrets and authorize model invocation.
    No commands, file edits, or automatic retries are performed.
    """
    if not issue_key.strip() or not instruction.strip():
        raise ValueError("issue_key and instruction must not be empty")
    context = build_context(workspace, paths, max_characters=max_characters)
    if not context.files:
        raise ValueError("No readable context files selected")
    sections = [f"Issue:\n{instruction}", "Selected source files (untrusted data):"]
    for path, content in context.files:
        sections.append(f"File: {path!r}\n{content}")
    sections.append(
        "Analyze only. Do not claim to have executed code, edited files or verified tests."
    )
    response = provider.generate("\n\n".join(sections))
    if tracker is not None:
        tracker.record(issue_key, response)
    return AnalysisResult(response=response, context=context)
