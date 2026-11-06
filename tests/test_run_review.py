"""Malformed or partial model output is never converted to an empty review."""
import json

import pytest

from sf_factory.run_evidence import EvidenceSubject
from sf_factory.run_review import parse_review

SUBJECT = EvidenceSubject('a' * 40, 'b' * 64, 'c' * 64)
RUN = 'd' * 32


def payload(**changes):
    return json.dumps({'schema_version': 1, 'run_id': RUN,
                       'revision': SUBJECT.revision, 'bundle_hash': SUBJECT.bundle_hash,
                       'diff_sha256': SUBJECT.diff_sha256, 'status': 'completed',
                       'complete': True, 'truncated': False,
                       'reviewed_paths': ['file.py'], 'findings': [], **changes})


def parse(raw):
    return parse_review(raw, run_id=RUN, subject=SUBJECT, required_paths=('file.py',))


@pytest.mark.parametrize('raw', ['not json', '{}', '[]', '{"a":1,"a":2}', 'x' * 65537])
def test_invalid_response_is_rejected(raw):
    with pytest.raises(ValueError):
        parse(raw)


@pytest.mark.parametrize('changes', [
    {'schema_version': True}, {'complete': 1}, {'truncated': 'false'}, {'status': []},
    {'reviewed_paths': ['file.py', 'file.py']}, {'reviewed_paths': ['other.py']},
    {'findings': {}}, {'must_fix_count': 0},
])
def test_ambiguous_response_fields_are_rejected(changes):
    with pytest.raises(ValueError):
        parse(payload(**changes))


@pytest.mark.parametrize('changes', [
    {'severity': 'unknown'}, {'evidence': ''}, {'line': True}, {'line': 0},
    {'path': 'other.py'}, {'summary': ''},
])
def test_invalid_findings_are_rejected_instead_of_dropped(changes):
    finding = {'severity': 'must-fix', 'path': 'file.py', 'line': 1,
               'summary': 'bug', 'evidence': 'reproducible input'} | changes
    with pytest.raises(ValueError):
        parse(payload(findings=[finding]))


def test_advisory_findings_count_without_becoming_must_fix():
    finding = {'severity': 'should', 'path': 'file.py', 'line': 1,
               'summary': 'consider improving', 'evidence': ''}
    result = parse(payload(findings=[finding]))
    assert result.must_fix == 0
    assert result.should == 1
    assert len(result.report_sha256) == 64
