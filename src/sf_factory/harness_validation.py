"""Read-only syntax and ProjectProfile validation; never approval or execution."""
from __future__ import annotations

import hashlib
import json
import os
import stat
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import yaml

from sf_factory.harness_discovery import (
    HarnessCandidate,
    HarnessDiscovery,
    _sensitive,
    discover_harness,
)


@dataclass(frozen=True)
class ValidationIssue:
    path: str
    code: str


@dataclass(frozen=True)
class ProfileCandidate:
    path: str
    scope: str
    sha256: str
    command_names: tuple[str, ...]
    references: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class HarnessValidation:
    schema_version: int
    discovery: HarnessDiscovery
    profiles: tuple[ProfileCandidate, ...]
    issues: tuple[ValidationIssue, ...]
    valid: bool


class _StrictLoader(yaml.SafeLoader):
    """Reject aliases and duplicate keys rather than silently composing rules."""

    def compose_node(self, parent, index):
        if self.check_event(yaml.AliasEvent):
            raise ValueError("aliases are not supported")
        return super().compose_node(parent, index)

    def construct_mapping(self, node, deep=False):
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, (str, int, float, bool, type(None))):
                raise ValueError("unsupported mapping key")
            if key in result:
                raise ValueError("duplicate mapping key")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def _unique_json(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate mapping key")
        result[key] = value
    return result


def _read(root_fd: int, relative: str, budget: list[int]) -> bytes:
    """Open each path component relative to a pinned directory, without symlinks."""
    remaining = budget[0]
    path = PurePosixPath(relative)
    if path.is_absolute() or not path.parts or '..' in path.parts or '\\' in relative:
        raise ValueError("unsafe reference")
    directory = os.dup(root_fd)
    try:
        for part in path.parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        fd = os.open(path.parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=directory)
        with os.fdopen(fd, 'rb') as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size > min(65536, remaining):
                raise ValueError("reference size or type")
            body = stream.read(min(65536, remaining) + 1)
            budget[0] -= len(body)
            after = os.fstat(stream.fileno())
        current = os.stat(path.parts[-1], dir_fd=directory, follow_symlinks=False)
        signatures = {(s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
                      for s in (before, after, current)}
        if len(signatures) != 1 or len(body) > min(65536, remaining):
            raise ValueError("reference changed or exceeded budget")
        body.decode('utf-8')
        if b'\x00' in body:
            raise ValueError("binary reference")
        return body
    finally:
        os.close(directory)


def _parse(candidate: HarnessCandidate, body: bytes):
    suffix = PurePosixPath(candidate.path).suffix
    if suffix in {'.yaml', '.yml'}:
        # Bound syntax depth before constructing objects, including unused anchors.
        depth = 0
        for event in yaml.parse(body, Loader=_StrictLoader):
            if isinstance(event, (yaml.SequenceStartEvent, yaml.MappingStartEvent)):
                depth += 1
                if depth > 32:
                    raise ValueError("structure too deep")
            elif isinstance(event, (yaml.SequenceEndEvent, yaml.MappingEndEvent)):
                depth -= 1
        return yaml.load(body, Loader=_StrictLoader)
    if suffix == '.json':
        return json.loads(body, object_pairs_hook=_unique_json,
                          parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    if suffix == '.toml':
        return tomllib.loads(body.decode('utf-8'))
    return None


def _profile(document) -> tuple[dict, list[str]]:
    if not isinstance(document, dict) or document.get('kind') != 'ProjectProfile':
        raise ValueError("invalid profile")
    if document.get('apiVersion') != 'generic-software-factory/v1alpha1':
        raise ValueError("unsupported profile version")
    metadata, spec = document.get('metadata'), document.get('spec')
    if not isinstance(metadata, dict) or not isinstance(metadata.get('name'), str):
        raise ValueError("missing name")
    if not metadata['name'].strip() or not isinstance(spec, dict):
        raise ValueError("missing spec")
    language = spec.get('language')
    if (not isinstance(language, str) or not language.strip() or '<configure-' in language):
        raise ValueError("language required")
    done = spec.get('definitionOfDone')
    if (not isinstance(done, list) or not done
            or any(not isinstance(v, str) or not v.strip() for v in done)):
        raise ValueError("definition of done required")
    if spec.get('repositoryRoot') != '.':
        raise ValueError("only explicit local scope is supported")
    commands = spec.get('commands')
    if not isinstance(commands, dict) or not commands.get('test'):
        raise ValueError("test command required")
    for key, value in commands.items():
        if (key not in {'test', 'lint', 'build', 'security'}
                or not isinstance(value, str) or not value.strip()
                or '<configure-' in value or '\x00' in value):
            raise ValueError("invalid command proposal")
    references = []
    for field in ('architectureDocs', 'conventions'):
        values = spec.get(field, [])
        if not isinstance(values, list) or any(not isinstance(v, str) or not v for v in values):
            raise ValueError("invalid references")
        references.extend(values)
    if len(references) > 64:
        raise ValueError("too many references")
    return commands, references


def validate_harness(root: Path) -> HarnessValidation:
    """Validate a fresh inventory. Output contains no file or command contents.

    Multiple sources remain unresolved; `valid` is never execution permission.
    Reads are bounded to 1 MiB in addition to the bounded discovery scan.
    """
    discovery = discover_harness(root)
    issues = [ValidationIssue(i.path, i.reason) for i in discovery.issues]
    profiles: list[ProfileCandidate] = []
    budget = [1048576]
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for candidate in discovery.candidates:
            try:
                body = _read(root_fd, candidate.path, budget)
                if hashlib.sha256(body).hexdigest() != candidate.sha256:
                    raise ValueError("candidate changed since discovery")
                document = _parse(candidate, body)
                if (candidate.kind in {'manifest', 'ci', 'profile'}
                        and not isinstance(document, dict)):
                    raise ValueError("mapping required")
                if candidate.kind != 'profile':
                    continue
                if '.example.' in candidate.path:
                    issues.append(ValidationIssue(candidate.path, 'example_profile_not_active'))
                    continue
                commands, references = _profile(document)
                resolved = []
                for relative in dict.fromkeys(references):
                    if (PurePosixPath(relative).is_absolute() or '..' in relative.split('/')
                            or '\\' in relative or relative in {'.', ''}):
                        raise ValueError("unsafe reference")
                    reference_parts = PurePosixPath(relative).parts
                    if (any(_sensitive(p) or p.startswith('.') for p in reference_parts)
                            or PurePosixPath(relative).suffix not in {
                                '.md', '.txt', '.rst', '.adoc'
                            }):
                        raise ValueError("unsupported or sensitive reference")
                    scope = '' if candidate.scope == '.' else candidate.scope + '/'
                    reference_path = scope + relative
                    content = _read(root_fd, reference_path, budget)
                    resolved.append((reference_path, hashlib.sha256(content).hexdigest()))
                profiles.append(ProfileCandidate(
                    candidate.path, candidate.scope, candidate.sha256,
                    tuple(sorted(commands)), tuple(sorted(resolved)),
                ))
            except (OSError, ValueError, TypeError, yaml.YAMLError, RecursionError):
                issues.append(ValidationIssue(candidate.path, 'invalid_or_changed_candidate'))
    finally:
        os.close(root_fd)
    # Keep original issues: validation does not silently resolve competing rules.
    return HarnessValidation(1, discovery, tuple(profiles),
                             tuple(sorted(set(issues), key=lambda i: (i.path, i.code))),
                             not issues)
