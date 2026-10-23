"""Heuristic drug-class classification over openFDA drug-event `patient.drug[]` entries.

No single openFDA field cleanly identifies peptide / protein / siRNA / small molecule, so
`classify()` applies rules in order of confidence and returns not just a label but a confidence
level and the specific rule that matched -- useful for debugging and for tests to assert *why*
something classified a given way, not just the final label.
"""

from typing import Any

from . import seed_data
from .types import ClassificationResult, DrugClass

__all__ = ["DrugClass", "ClassificationResult", "classify"]


def _openfda_field(drug_entry: dict[str, Any], field: str) -> list[str]:
    openfda = drug_entry.get("openfda")
    if not isinstance(openfda, dict):
        return []
    values = openfda.get(field)
    if not isinstance(values, list):
        return []
    return [v.lower() for v in values if isinstance(v, str)]


def _name_candidates(drug_entry: dict[str, Any]) -> list[str]:
    names: list[str] = []
    medicinalproduct = drug_entry.get("medicinalproduct")
    if isinstance(medicinalproduct, str) and medicinalproduct:
        names.append(medicinalproduct.lower())
    names.extend(_openfda_field(drug_entry, "generic_name"))
    names.extend(_openfda_field(drug_entry, "substance_name"))
    return names


def _match_pharm_class_keywords(values: list[str]) -> ClassificationResult | None:
    for drug_class, keywords in seed_data.PHARM_CLASS_KEYWORDS:
        for value in values:
            for keyword in keywords:
                if keyword in value:
                    return ClassificationResult(
                        drug_class=drug_class,
                        confidence="high",
                        matched_rule=f"pharm_class_keyword:{keyword}",
                    )
    return None


def _match_name_suffix(names: list[str]) -> ClassificationResult | None:
    for name in names:
        for suffix in seed_data.SIRNA_NAME_SUFFIXES:
            if name.endswith(suffix):
                return ClassificationResult(
                    drug_class=DrugClass.SIRNA,
                    confidence="medium",
                    matched_rule=f"name_suffix:{suffix}",
                )
        for suffix in seed_data.PROTEIN_NAME_SUFFIXES:
            if name.endswith(suffix):
                return ClassificationResult(
                    drug_class=DrugClass.PROTEIN,
                    confidence="medium",
                    matched_rule=f"name_suffix:{suffix}",
                )
        for suffix in seed_data.PEPTIDE_NAME_SUFFIXES:
            if name.endswith(suffix):
                return ClassificationResult(
                    drug_class=DrugClass.PEPTIDE,
                    confidence="medium",
                    matched_rule=f"name_suffix:{suffix}",
                )
    return None


def classify(drug_entry: dict[str, Any]) -> ClassificationResult:
    names = _name_candidates(drug_entry)

    # 1. Exact/substring substance-name match against the exhaustive siRNA list -- highest
    #    confidence since this list is short and unambiguous.
    for name in names:
        for sirna_name in seed_data.SIRNA_SUBSTANCE_NAMES:
            if sirna_name in name:
                return ClassificationResult(
                    drug_class=DrugClass.SIRNA,
                    confidence="high",
                    matched_rule=f"substance_name_exact:{sirna_name}",
                )

    # 2. openfda.pharm_class_cs keyword match (structured chemical-structure classification).
    pharm_class_cs = _openfda_field(drug_entry, "pharm_class_cs")
    result = _match_pharm_class_keywords(pharm_class_cs)
    if result is not None:
        return result

    # 3. Name-suffix heuristics on medicinalproduct / generic_name / substance_name.
    result = _match_name_suffix(names)
    if result is not None:
        return result

    # 4. openfda.pharm_class_epc keyword fallback (established pharmacologic class).
    pharm_class_epc = _openfda_field(drug_entry, "pharm_class_epc")
    result = _match_pharm_class_keywords(pharm_class_epc)
    if result is not None:
        return result

    # 5. Weak application-number tiebreak, only when no structured pharm_class signal exists at
    #    all (checked above) -- BLA is a weak prior for protein, never for peptide/siRNA, since
    #    many peptides and siRNA therapeutics are also BLA- or NDA-filed.
    application_numbers = _openfda_field(drug_entry, "application_number")
    if not pharm_class_cs and not pharm_class_epc:
        for app_number in application_numbers:
            if app_number.startswith("bla"):
                return ClassificationResult(
                    drug_class=DrugClass.PROTEIN,
                    confidence="low",
                    matched_rule="application_number_bla_weak_prior",
                )

    # 6. Default: if there is *any* identifying information at all, assume small molecule (the
    #    large majority of drugs), rather than UNKNOWN. UNKNOWN is reserved for entries with no
    #    recognizable fields whatsoever.
    if names or application_numbers:
        return ClassificationResult(
            drug_class=DrugClass.SMALL_MOLECULE,
            confidence="low",
            matched_rule="default_small_molecule_fallback",
        )

    return ClassificationResult(
        drug_class=DrugClass.UNKNOWN,
        confidence="low",
        matched_rule="no_identifying_fields",
    )
