"""Builds openFDA `search=` query fragments per drug class, to narrow ingestion volume

server-side and conserve the keyless daily request quota. These fragments are an optimization,
not a substitute for `classification.drug_class.classify()`: openFDA's own `pharm_class_*`
indexing is sparse/inconsistent, so the ingestion service always re-classifies every fetched
report client-side regardless of which fragment was used to find it.

Built from the SAME seed dictionaries as the classifier (`classification.seed_data`) -- single
source of truth, not duplicated here.
"""

from datetime import date

from faersgraph.classification import seed_data
from faersgraph.classification.types import DrugClass

_DRUG_PREFIX = "patient.drug.openfda"


def _keywords_for(drug_class: DrugClass) -> frozenset[str]:
    for candidate_class, keywords in seed_data.PHARM_CLASS_KEYWORDS:
        if candidate_class == drug_class:
            return keywords
    return frozenset()


def _quote(term: str) -> str:
    return f'"{term}"' if " " in term else term


def _or_group(field: str, terms: list[str]) -> str:
    joined = " OR ".join(_quote(t) for t in terms)
    return f"{field}:({joined})"


def build_search_fragment(drug_class: DrugClass) -> str:
    """Returns an openFDA `search=` fragment for the given class, or "" if the class has no
    reliable positive inclusion predicate (small molecule -- see note below).
    """
    if drug_class == DrugClass.SIRNA:
        substance_clause = _or_group(
            f"{_DRUG_PREFIX}.substance_name", sorted(seed_data.SIRNA_SUBSTANCE_NAMES)
        )
        cs_clause = _or_group(
            f"{_DRUG_PREFIX}.pharm_class_cs", sorted(_keywords_for(DrugClass.SIRNA))
        )
        return f"({substance_clause} OR {cs_clause})"

    if drug_class == DrugClass.PROTEIN:
        suffix_clause = _or_group(
            f"{_DRUG_PREFIX}.substance_name",
            [f"*{suffix}" for suffix in seed_data.PROTEIN_NAME_SUFFIXES],
        )
        cs_clause = _or_group(
            f"{_DRUG_PREFIX}.pharm_class_cs", sorted(_keywords_for(DrugClass.PROTEIN))
        )
        return f"({suffix_clause} OR {cs_clause})"

    if drug_class == DrugClass.PEPTIDE:
        suffix_clause = _or_group(
            f"{_DRUG_PREFIX}.substance_name",
            [f"*{suffix}" for suffix in seed_data.PEPTIDE_NAME_SUFFIXES],
        )
        cs_clause = _or_group(
            f"{_DRUG_PREFIX}.pharm_class_cs", sorted(_keywords_for(DrugClass.PEPTIDE))
        )
        return f"({suffix_clause} OR {cs_clause})"

    if drug_class == DrugClass.SMALL_MOLECULE:
        # No clean positive inclusion predicate exists for "small molecule" in openFDA's schema
        # (it's the default/residual bucket). Returning "" means "fetch unfiltered" -- the
        # ingestion service relies entirely on client-side classify() to tag these.
        return ""

    raise ValueError(f"No search fragment strategy for {drug_class!r}")


def build_date_range_fragment(start: date, end: date) -> str:
    return f"receivedate:[{start.strftime('%Y%m%d')} TO {end.strftime('%Y%m%d')}]"


def combine_fragments(*fragments: str) -> str:
    """Joins non-empty fragments with AND. Empty fragments (e.g. small molecule's "") are skipped."""
    non_empty = [f for f in fragments if f]
    return " AND ".join(non_empty)
