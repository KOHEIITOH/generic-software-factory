"""Deterministic, read-only context selection with a character budget.

This is a conservative pre-tokenizer MVP, not a token-count guarantee.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ContextSelection:
    files: tuple[tuple[str, str], ...]
    excluded: tuple[str, ...]
    characters: int


def build_context(
    workspace: Path,
    paths: list[str],
    *,
    max_characters: int = 12000,
) -> ContextSelection:
    """Select explicit workspace files; never follow symlinks or escape the root."""
    if max_characters < 0:
        raise ValueError("max_characters must be non-negative")
    root = workspace.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("workspace must be a directory")
    selected: list[tuple[str, str]] = []
    excluded: list[str] = []
    total = 0
    for raw in dict.fromkeys(paths):
        relative = Path(raw)
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            excluded.append(raw)
            continue
        candidate = root / relative
        if candidate.is_symlink() or any(parent.is_symlink() for parent in
                                         list(candidate.parents) if parent != root):
            excluded.append(raw)
            continue
        try:
            resolved = candidate.resolve(strict=True)
            if not resolved.is_relative_to(root) or not resolved.is_file():
                excluded.append(raw)
                continue
            size = resolved.stat().st_size
            if size > max_characters * 4 + 4:
                excluded.append(raw)
                continue
            body = resolved.read_text(encoding="utf-8")
            if chr(0) in body:
                excluded.append(raw)
                continue
        except (OSError, UnicodeError):
            excluded.append(raw)
            continue
        if total + len(body) > max_characters:
            excluded.append(raw)
            continue
        selected.append((relative.as_posix(), body))
        total += len(body)
    return ContextSelection(tuple(selected), tuple(excluded), total)
