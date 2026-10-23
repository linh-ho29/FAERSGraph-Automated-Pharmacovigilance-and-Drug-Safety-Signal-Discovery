from faersgraph.models.enums import ReactionOutcome, SeriousnessReason
from faersgraph.normalization.outcome_normalizer import normalize_outcome_code, normalize_seriousness


def test_normalize_outcome_code_known_values() -> None:
    assert normalize_outcome_code("5") == ReactionOutcome.FATAL
    assert normalize_outcome_code("1") == ReactionOutcome.RECOVERED_RESOLVED


def test_normalize_outcome_code_missing_or_invalid() -> None:
    assert normalize_outcome_code(None) is None
    assert normalize_outcome_code("not-a-code") is None


def test_normalize_seriousness_true_with_reasons() -> None:
    report = {"serious": "1", "seriousnesshospitalization": "1", "seriousnessdeath": "1"}
    serious, reasons = normalize_seriousness(report)
    assert serious is True
    assert set(reasons) == {SeriousnessReason.HOSPITALIZATION, SeriousnessReason.DEATH}


def test_normalize_seriousness_false_no_reasons() -> None:
    serious, reasons = normalize_seriousness({"serious": "2"})
    assert serious is False
    assert reasons == []


def test_normalize_seriousness_missing_field() -> None:
    serious, reasons = normalize_seriousness({})
    assert serious is None
    assert reasons == []
