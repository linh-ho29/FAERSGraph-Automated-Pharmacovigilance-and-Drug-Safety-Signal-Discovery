from typing import Any

from faersgraph.classification.drug_class import classify
from faersgraph.models.enums import DrugCharacterization, TermSourceStatus
from faersgraph.models.normalized import NormalizedDrug

from .indication_normalizer import normalize_indication
from .rxnorm_cache import RxNormCache
from .rxnorm_client import RxNormClient


def _candidate_term(drug_entry: dict[str, Any]) -> str | None:
    """openfda.substance_name is preferred as the closest field to true ingredient identity;
    falls back to generic_name, then the raw medicinalproduct string."""
    openfda = drug_entry.get("openfda") or {}
    for field in ("substance_name", "generic_name"):
        values = openfda.get(field) or []
        if values:
            return values[0]
    medicinalproduct = drug_entry.get("medicinalproduct")
    return medicinalproduct or None


def normalize_drug(
    drug_entry: dict[str, Any],
    rxnorm_client: RxNormClient,
    rxnorm_cache: RxNormCache,
) -> NormalizedDrug:
    classification = classify(drug_entry)

    openfda = drug_entry.get("openfda") or {}
    substance_names = openfda.get("substance_name") or []
    generic_names = openfda.get("generic_name") or []

    term = _candidate_term(drug_entry)
    rxcui: str | None = None
    rxnorm_name: str | None = None

    if term:
        cached = rxnorm_cache.get(term)
        if cached is not None:
            rxcui = cached.rxcui
            rxnorm_name = cached.rxnorm_name
        else:
            candidates = rxnorm_client.approximate_match(term)
            best_score = candidates[0].score if candidates else None
            if candidates:
                rxcui = candidates[0].rxcui
                rxnorm_name = rxnorm_client.get_ingredient_name(rxcui)
            rxnorm_cache.put(term, rxcui=rxcui, rxnorm_name=rxnorm_name, match_score=best_score)

    normalization_status = (
        TermSourceStatus.RXNORM_MATCHED if rxcui else TermSourceStatus.RXNORM_UNMATCHED
    )

    characterization_raw = drug_entry.get("drugcharacterization")
    characterization: DrugCharacterization | None = None
    if characterization_raw:
        try:
            characterization = DrugCharacterization(str(characterization_raw))
        except ValueError:
            characterization = None

    indication_raw = drug_entry.get("drugindication")

    return NormalizedDrug(
        raw_medicinalproduct=drug_entry.get("medicinalproduct"),
        raw_generic_name=generic_names[0] if generic_names else None,
        raw_substance_name=substance_names[0] if substance_names else None,
        rxcui=rxcui,
        rxnorm_normalized_name=rxnorm_name,
        normalization_status=normalization_status,
        drug_class=classification.drug_class,
        drug_class_confidence=classification.confidence,
        drug_class_matched_rule=classification.matched_rule,
        drugcharacterization=characterization,
        indication_raw=indication_raw,
        indication_normalized=normalize_indication(indication_raw),
    )
