"""Bounded local Harness inventory. Discovery never executes or applies rules.

POSIX descriptor-relative reads avoid following symlinks during traversal.
Results contain metadata, never file contents. This is not a sandbox or approval.
"""
from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DiscoveryLimits:
    entries: int = 10000
    depth: int = 32
    file_bytes: int = 65536
    total_bytes: int = 1048576

    def __post_init__(self) -> None:
        if any(type(value) is not int or value < 1 for value in (
            self.entries, self.depth, self.file_bytes, self.total_bytes
        )):
            raise ValueError("discovery limits must be positive integers")


@dataclass(frozen=True)
class HarnessCandidate:
    path: str
    kind: str
    scope: str
    sha256: str
    reason: str


@dataclass(frozen=True)
class DiscoveryIssue:
    path: str
    reason: str


@dataclass(frozen=True)
class HarnessDiscovery:
    schema_version: int
    candidates: tuple[HarnessCandidate, ...]
    issues: tuple[DiscoveryIssue, ...]
    complete: bool


_IGNORED = {
    ".git", ".venv", "node_modules", "__pycache__", "dist", "build",
    "vendor", "target", ".sf-factory", ".cache", ".pytest_cache", ".ruff_cache",
}


def _classify(parts: tuple[str, ...]) -> tuple[str, str] | None:
    name = parts[-1]
    if name == "AGENTS.md":
        return "instructions", "AGENTS.md convention"
    if "harness" in parts[:-1]:
        return "harness", "harness directory convention"
    if len(parts) >= 2 and parts[-2] == "config" and name.startswith("project"):
        if name.endswith((".yaml", ".yml")):
            return "profile", "project configuration convention"
    if name in {"pyproject.toml", "package.json"}:
        return "manifest", "project manifest convention"
    if len(parts) >= 3 and parts[-3:-1] == (".github", "workflows"):
        if name.endswith((".yaml", ".yml")):
            return "ci", "GitHub Actions convention"
    return None


def _sensitive(name: str) -> bool:
    lower = name.lower()
    return (
        lower.startswith((".env", "id_rsa", "id_ed25519"))
        or any(word in lower for word in ("secret", "credential", "token"))
        or lower.endswith((".pem", ".key", ".p12", ".pfx"))
    )


def discover_harness(root: Path, *, limits: DiscoveryLimits | None = None) -> HarnessDiscovery:
    """Inventory an explicit Git root, including nested AGENTS and manifests.

    No Git subprocess, model call, parsing, composition or command execution.
    `complete` means no observed scan issues within the documented conventions;
    it does not mean that every possible Harness format has been recognized.
    """
    limits = limits or DiscoveryLimits()
    if not hasattr(os, "O_NOFOLLOW") or os.open not in os.supports_dir_fd:
        raise NotImplementedError("descriptor-relative POSIX traversal is required")
    if not root.is_absolute() or ".." in root.parts:
        raise ValueError("an absolute repository root without parent traversal is required")
    # Reject symlink ancestors as well as a symlink root.
    if any(path.is_symlink() for path in (root, *root.parents)):
        raise ValueError("symlink repository paths are not supported")
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY
    root_fd = os.open(root, flags)
    candidates: list[HarnessCandidate] = []
    issues: list[DiscoveryIssue] = []
    scanned = 0
    consumed = 0
    stopped = False

    def issue(path: str, reason: str) -> None:
        issues.append(DiscoveryIssue(path, reason))

    def scan(fd: int, parts: tuple[str, ...]) -> None:
        nonlocal scanned, consumed, stopped
        before = os.fstat(fd)
        names: list[str] = []
        try:
            with os.scandir(fd) as iterator:
                for entry in iterator:
                    if scanned >= limits.entries:
                        issue("/".join(parts) or ".", "entry_limit")
                        stopped = True
                        return
                    scanned += 1
                    names.append(entry.name)
            for name in sorted(names):
                if stopped:
                    break
                child = (*parts, name)
                path = "/".join(child)
                if name in _IGNORED:
                    continue
                if _sensitive(name):
                    issue(path, "sensitive_name_excluded")
                    continue
                metadata = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if stat.S_ISLNK(metadata.st_mode):
                    issue(path, "symlink_excluded")
                    continue
                if stat.S_ISDIR(metadata.st_mode):
                    if len(child) > limits.depth:
                        issue(path, "depth_limit")
                        continue
                    try:
                        nested = os.open(name, flags, dir_fd=fd)
                        try:
                            opened_directory = os.fstat(nested)
                            if (metadata.st_dev, metadata.st_ino) != (
                                opened_directory.st_dev, opened_directory.st_ino
                            ):
                                issue(path, "directory_changed")
                            else:
                                scan(nested, child)
                        finally:
                            os.close(nested)
                    except OSError:
                        issue(path, "directory_unreadable_or_changed")
                    continue
                classification = _classify(child)
                if classification is None:
                    continue
                if not stat.S_ISREG(metadata.st_mode):
                    issue(path, "non_regular_file")
                    continue
                if metadata.st_size > limits.file_bytes:
                    issue(path, "file_size_limit")
                    continue
                remaining = limits.total_bytes - consumed
                if remaining <= 0 or metadata.st_size > remaining:
                    issue(path, "total_bytes_limit")
                    stopped = True
                    break
                try:
                    file_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                      dir_fd=fd)
                    with os.fdopen(file_fd, "rb") as stream:
                        opened = os.fstat(stream.fileno())
                        if not stat.S_ISREG(opened.st_mode):
                            issue(path, "file_changed")
                            continue
                        body = stream.read(min(limits.file_bytes, remaining) + 1)
                        after = os.fstat(stream.fileno())
                    current = os.stat(name, dir_fd=fd, follow_symlinks=False)
                    def identity(s: os.stat_result) -> tuple[int, ...]:
                        return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)

                    consumed += len(body)
                    identities = [identity(s) for s in (metadata, opened, after, current)]
                    if len(set(identities)) != 1:
                        issue(path, "file_changed")
                        continue
                    if len(body) > min(limits.file_bytes, remaining):
                        issue(path, "file_size_limit")
                        continue
                    text = body.decode("utf-8")
                    if "\x00" in text:
                        issue(path, "binary_file")
                        continue
                except UnicodeError:
                    issue(path, "non_utf8_file")
                    continue
                except OSError:
                    issue(path, "file_unreadable_or_changed")
                    continue
                kind, reason = classification
                if kind == "harness" and Path(name).suffix.lower() not in {
                    ".md", ".txt", ".yaml", ".yml", ".json", ".toml"
                }:
                    issue(path, "unsupported_harness_format")
                    continue
                scope_parts = child[:-1]
                if kind == "harness":
                    scope_parts = child[:child.index("harness")]
                elif kind == "profile":
                    scope_parts = child[:-2]
                elif kind == "ci":
                    scope_parts = child[:-3]
                candidates.append(HarnessCandidate(
                    path, kind, "/".join(scope_parts) or ".",
                    hashlib.sha256(body).hexdigest(), reason,
                ))
        except OSError:
            issue("/".join(parts) or ".", "directory_unreadable_or_changed")
        finally:
            after = os.fstat(fd)
            if (before.st_mtime_ns, before.st_ctime_ns) != (after.st_mtime_ns, after.st_ctime_ns):
                issue("/".join(parts) or ".", "directory_changed")

    try:
        metadata = os.stat(".git", dir_fd=root_fd, follow_symlinks=False)
        if not (stat.S_ISDIR(metadata.st_mode) or stat.S_ISREG(metadata.st_mode)):
            raise ValueError("repository root requires regular .git metadata")
        scan(root_fd, ())
    finally:
        os.close(root_fd)
    # Multiple rule sources are candidates, never silently resolved here.
    scopes: dict[str, list[HarnessCandidate]] = {}
    for candidate in candidates:
        if candidate.kind in {"instructions", "harness", "profile"}:
            scopes.setdefault(candidate.scope, []).append(candidate)
    for scope, sources in scopes.items():
        if len(sources) > 1:
            issue(scope, "multiple_rule_sources_require_validation")
    return HarnessDiscovery(1, tuple(sorted(candidates, key=lambda c: c.path)),
                            tuple(sorted(set(issues), key=lambda i: (i.path, i.reason))),
                            not issues)
