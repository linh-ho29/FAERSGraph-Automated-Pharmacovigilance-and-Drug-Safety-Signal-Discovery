import unicodedata
from typing import Any, Protocol

from faersgraph.models.enums import TermSourceStatus
from faersgraph.models.normalized import NormalizedReaction

from .outcome_normalizer import normalize_outcome_code


def normalize_surface_form(text: str) -> str:
    """Unicode-normalize, trim, collapse internal whitespace, lowercase. MedDRA PTs are
    conventionally lowercase in FAERS already; lowercasing here just guarantees stable dedup
    keys regardless of casing inconsistencies in the source data."""
    normalized = unicodedata.normalize("NFKC", text)
    normalized = " ".join(normalized.strip().split())
    return normalized.lower()


class MedDRAHierarchyProvider(Protocol):
    """Extension hook for users with their own MedDRA license. openFDA exposes only the PT
    (Preferred Term) string -- no PT->HLT->SOC hierarchy, since that hierarchy is licensed and
    proprietary. No implementation ships in this MVP; this Protocol exists so a real provider
    can be plugged in later WITHOUT faking a hierarchy in the meantime."""

    def lookup_pt(self, pt_term: str) -> Any | None: ...


def normalize_reaction(
    raw_pt: str,
    outcome_code: str | None = None,
    hierarchy_provider: MedDRAHierarchyProvider | None = None,
) -> NormalizedReaction:
    normalized_pt = normalize_surface_form(raw_pt)

    term_source_status = TermSourceStatus.MEDDRA_HIERARCHY_UNAVAILABLE
    if hierarchy_provider is not None and hierarchy_provider.lookup_pt(normalized_pt) is not None:
        term_source_status = TermSourceStatus.MEDDRA_HIERARCHY_LOCAL

    return NormalizedReaction(
        meddrapt_raw=raw_pt,
        meddrapt_normalized=normalized_pt,
        term_source_status=term_source_status,
        outcome=normalize_outcome_code(outcome_code),
    )
