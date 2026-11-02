import pytest

from sf_factory.quality import (
    GateStatus,
    QualityEvidence,
    QualityGate,
    evaluate_quality,
)


def test_all_required_evidence_passes() -> None:
    report = evaluate_quality(
        (QualityGate("tests"), QualityGate("lint")),
        (QualityEvidence("tests", True, source="ci"), QualityEvidence("lint", True)),
    )
    assert report.passed
    assert all(item.status is GateStatus.PASSED for item in report.gates)


def test_missing_required_evidence_fails_closed() -> None:
    report = evaluate_quality((QualityGate("tests"),), ())
    assert not report.passed
    assert report.gates[0].status is GateStatus.MISSING
    assert "tests: missing" in report.feedback


def test_failed_required_check_returns_feedback() -> None:
    report = evaluate_quality(
        (QualityGate("tests"),),
        (QualityEvidence("tests", False, "2 tests failed", "pytest"),),
    )
    assert not report.passed
    assert "2 tests failed" in report.feedback


def test_optional_check_does_not_block() -> None:
    report = evaluate_quality(
        (QualityGate("tests"), QualityGate("docs", required=False)),
        (QualityEvidence("tests", True),),
    )
    assert report.passed
    assert report.gates[1].status is GateStatus.MISSING


@pytest.mark.parametrize(
    ("gates", "evidence"),
    [
        ((QualityGate("x"), QualityGate("x")), ()),
        ((QualityGate(""),), ()),
        ((), (QualityEvidence("x", True), QualityEvidence("x", False))),
        ((), (QualityEvidence("", True),)),
    ],
)
def test_invalid_gate_or_evidence_ids_are_rejected(gates, evidence) -> None:
    with pytest.raises(ValueError):
        evaluate_quality(gates, evidence)


def test_gate_order_is_configuration_order() -> None:
    report = evaluate_quality(
        (QualityGate("lint"), QualityGate("tests")),
        (QualityEvidence("tests", True), QualityEvidence("lint", False)),
    )
    assert [item.id for item in report.gates] == ["lint", "tests"]


def test_no_required_gates_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least one required"):
        evaluate_quality((QualityGate("docs", required=False),), ())
