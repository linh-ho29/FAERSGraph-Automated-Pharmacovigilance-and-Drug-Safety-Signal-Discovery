from pathlib import Path

import httpx
import respx

from faersgraph.classification.types import DrugClass
from faersgraph.config import Settings
from faersgraph.models.enums import TermSourceStatus
from faersgraph.normalization.drug_normalizer import normalize_drug
from faersgraph.normalization.rxnorm_cache import RxNormCache
from faersgraph.normalization.rxnorm_client import RxNormClient


def _settings() -> Settings:
    return Settings(rxnorm_base_url="https://rxnav.nlm.nih.gov/REST")


def _drug_entry() -> dict:
    return {
        "medicinalproduct": "ONPATTRO",
        "drugcharacterization": "1",
        "drugindication": "Hereditary transthyretin amyloidosis",
        "openfda": {"substance_name": ["PATISIRAN"], "pharm_class_cs": ["Small Interfering RNA [EPC]"]},
    }


@respx.mock
def test_normalize_drug_cache_hit_makes_no_http_call(tmp_path: Path) -> None:
    cache = RxNormCache(tmp_path / "cache.sqlite")
    cache.put("PATISIRAN", rxcui="1991661", rxnorm_name="Patisiran", match_score=100)
    client = RxNormClient(_settings())

    result = normalize_drug(_drug_entry(), client, cache)

    assert result.rxcui == "1991661"
    assert result.rxnorm_normalized_name == "Patisiran"
    assert result.normalization_status == TermSourceStatus.RXNORM_MATCHED
    assert result.drug_class == DrugClass.SIRNA
    assert result.indication_normalized == "hereditary transthyretin amyloidosis"


@respx.mock
def test_normalize_drug_cache_miss_calls_rxnav_and_populates_cache(tmp_path: Path) -> None:
    respx.get("https://rxnav.nlm.nih.gov/REST/approximateTerm.json").mock(
        return_value=httpx.Response(
            200,
            json={"approximateGroup": {"candidate": [{"rxcui": "1991661", "score": "100"}]}},
        )
    )
    respx.get("https://rxnav.nlm.nih.gov/REST/rxcui/1991661/property.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "propConceptGroup": {
                    "propConcept": [{"propName": "RxNorm Name", "propValue": "Patisiran"}]
                }
            },
        )
    )
    cache = RxNormCache(tmp_path / "cache.sqlite")
    client = RxNormClient(_settings())

    result = normalize_drug(_drug_entry(), client, cache)

    assert result.rxcui == "1991661"
    cached = cache.get("PATISIRAN")
    assert cached is not None and cached.rxcui == "1991661"


@respx.mock
def test_normalize_drug_unmatched_term_preserves_raw_and_marks_unmatched(tmp_path: Path) -> None:
    respx.get("https://rxnav.nlm.nih.gov/REST/approximateTerm.json").mock(
        return_value=httpx.Response(200, json={"approximateGroup": {}})
    )
    cache = RxNormCache(tmp_path / "cache.sqlite")
    client = RxNormClient(_settings())

    entry = {
        "medicinalproduct": "MADE UP DRUG XYZ",
        "openfda": {"substance_name": ["MADEUPDRUGXYZ"]},
    }
    result = normalize_drug(entry, client, cache)

    assert result.rxcui is None
    assert result.normalization_status == TermSourceStatus.RXNORM_UNMATCHED
    assert result.raw_substance_name == "MADEUPDRUGXYZ"
