from faersgraph.models.enums import ReactionOutcome, TermSourceStatus
from faersgraph.normalization.indication_normalizer import normalize_indication
from faersgraph.normalization.reaction_normalizer import normalize_reaction, normalize_surface_form


def test_surface_form_trims_and_lowercases() -> None:
    assert normalize_surface_form("  Nausea ") == "nausea"


def test_surface_form_collapses_internal_whitespace() -> None:
    assert normalize_surface_form("Peripheral   neuropathy") == "peripheral neuropathy"


def test_differently_cased_terms_dedupe_to_same_normalized_form() -> None:
    a = normalize_reaction("NAUSEA")
    b = normalize_reaction("  nausea ")
    assert a.meddrapt_normalized == b.meddrapt_normalized == "nausea"


def test_normalize_reaction_without_hierarchy_provider() -> None:
    reaction = normalize_reaction("Nausea", outcome_code="5")
    assert reaction.term_source_status == TermSourceStatus.MEDDRA_HIERARCHY_UNAVAILABLE
    assert reaction.outcome == ReactionOutcome.FATAL


class _StubHierarchyProvider:
    def lookup_pt(self, pt_term: str) -> object | None:
        return {"soc": "General disorders"} if pt_term == "nausea" else None


def test_normalize_reaction_with_hierarchy_provider_hit() -> None:
    reaction = normalize_reaction("Nausea", hierarchy_provider=_StubHierarchyProvider())
    assert reaction.term_source_status == TermSourceStatus.MEDDRA_HIERARCHY_LOCAL


def test_normalize_reaction_with_hierarchy_provider_miss() -> None:
    reaction = normalize_reaction("Unmapped term", hierarchy_provider=_StubHierarchyProvider())
    assert reaction.term_source_status == TermSourceStatus.MEDDRA_HIERARCHY_UNAVAILABLE


def test_normalize_indication_surface_form() -> None:
    assert normalize_indication("  Type 2 Diabetes Mellitus ") == "type 2 diabetes mellitus"


def test_normalize_indication_none_or_empty() -> None:
    assert normalize_indication(None) is None
    assert normalize_indication("") is None
