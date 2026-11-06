"""Strict, bounded review-response parsing; no model or tool calls."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sf_factory.run_evidence import EvidenceSubject


@dataclass(frozen=True)
class ReviewSummary:
    status: str
    complete: bool
    truncated: bool
    must_fix: int
    should: int
    nit: int
    report_sha256: str


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate review fields')
        result[key] = value
    return result


def parse_review(
    raw: str, *, run_id: str, subject: EvidenceSubject, required_paths: tuple[str, ...],
) -> ReviewSummary:
    """Recount findings; malformed/unknown output never becomes 'no findings'.

    Model text carries no trusted producer identity. The recording controller
    must verify provenance separately. Only counts and a hash are retained.
    """
    if not isinstance(raw, str) or len(raw.encode('utf-8')) > 65536:
        raise ValueError('review exceeds response budget')
    try:
        report = json.loads(raw, object_pairs_hook=_unique)
    except (ValueError, RecursionError) as exc:
        raise ValueError('invalid review JSON') from exc
    expected = {'schema_version', 'run_id', 'revision', 'bundle_hash', 'diff_sha256',
                'status', 'complete', 'truncated', 'reviewed_paths', 'findings'}
    if not isinstance(report, dict) or set(report) != expected:
        raise ValueError('review schema fields do not match')
    if type(report['schema_version']) is not int or report['schema_version'] != 1:
        raise ValueError('unsupported review schema')
    if (report['run_id'] != run_id or report['revision'] != subject.revision
            or report['bundle_hash'] != subject.bundle_hash
            or report['diff_sha256'] != subject.diff_sha256):
        raise ValueError('review subject mismatch')
    if not isinstance(report['status'], str) or report['status'] not in {'completed', 'failed'}:
        raise ValueError('unknown review status')
    if type(report['complete']) is not bool or type(report['truncated']) is not bool:
        raise ValueError('explicit review coverage flags required')
    paths = report['reviewed_paths']
    if (not isinstance(paths, list) or any(not isinstance(p, str) for p in paths)
            or len(paths) != len(set(paths)) or not set(paths) <= set(required_paths)):
        raise ValueError('invalid review coverage')
    findings = report['findings']
    if not isinstance(findings, list) or len(findings) > 100:
        raise ValueError('bounded findings required')
    counts = {'must-fix': 0, 'should': 0, 'nit': 0}
    for finding in findings:
        if not isinstance(finding, dict) or set(finding) != {
            'severity', 'path', 'line', 'summary', 'evidence'
        }:
            raise ValueError('finding fields do not match')
        severity = finding['severity']
        if not isinstance(severity, str) or severity not in counts:
            raise ValueError('unknown finding severity')
        if finding['path'] not in required_paths:
            raise ValueError('finding outside reviewed change scope')
        if type(finding['line']) is not int or finding['line'] < 1:
            raise ValueError('positive finding line required')
        for field in ('summary', 'evidence'):
            value = finding[field]
            if not isinstance(value, str) or len(value) > 2000:
                raise ValueError('bounded finding text required')
        if not finding['summary'].strip() or (severity == 'must-fix'
                                             and not finding['evidence'].strip()):
            raise ValueError('must-fix findings require evidence')
        counts[severity] += 1
    return ReviewSummary(
        report['status'], report['complete'] and set(paths) == set(required_paths),
        report['truncated'], counts['must-fix'], counts['should'], counts['nit'],
        hashlib.sha256(raw.encode('utf-8')).hexdigest(),
    )
