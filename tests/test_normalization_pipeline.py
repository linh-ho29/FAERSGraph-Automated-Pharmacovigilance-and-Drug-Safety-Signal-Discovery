import json
from pathlib import Path

import httpx
import respx

from faersgraph.classification.types import DrugClass
from faersgraph.config import Settings
from faersgraph.normalization.pipeline import NormalizationPipeline
from faersgraph.normalization.rxnorm_cache import RxNormCache
from faersgraph.normalization.rxnorm_client import RxNormClient

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "openfda"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text())


def _settings() -> Settings:
    return Settings(rxnorm_base_url="https://rxnav.nlm.nih.gov/REST")


def _pipeline(tmp_path: Path) -> NormalizationPipeline:
    cache = RxNormCache(tmp_path / "cache.sqlite")
    client = RxNormClient(_settings())
    return NormalizationPipeline(client, cache)


@respx.mock
def test_sirna_fixture_normalizes_correctly(tmp_path: Path) -> None:
    respx.get("https://rxnav.nlm.nih.gov/REST/approximateTerm.json").mock(
        return_value=httpx.Response(200, json={"approximateGroup": {"candidate": [{"rxcui": "1", "score": "100"}]}})
    )
    respx.get(url__regex=r"https://rxnav\.nlm\.nih\.gov/REST/rxcui/1/property\.json").mock(
        return_value=httpx.Response(200, json={"propConceptGroup": {"propConcept": [{"propName": "RxNorm Name", "propValue": "Patisiran"}]}})
    )

    report = _load_fixture("sirna_patisiran_report.json")
    normalized = _pipeline(tmp_path).normalize_report(report, batch_id="batch-1")

    assert normalized.safetyreportid == "10000001"
    assert normalized.drugs[0].drug_class == DrugClass.SIRNA
    assert normalized.serious is True
    assert len(normalized.reactions) == 2
    assert normalized.batch_id == "batch-1"


@respx.mock
def test_peptide_fixture_normalizes_correctly(tmp_path: Path) -> None:
    respx.get("https://rxnav.nlm.nih.gov/REST/approximateTerm.json").mock(
        return_value=httpx.Response(200, json={"approximateGroup": {}})
    )

    report = _load_fixture("peptide_hormone_report.json")
    normalized = _pipeline(tmp_path).normalize_report(report, batch_id="batch-1")

    assert normalized.drugs[0].drug_class == DrugClass.PEPTIDE
    assert normalized.serious is False


@respx.mock
def test_protein_fixture_normalizes_correctly(tmp_path: Path) -> None:
    respx.get("https://rxnav.nlm.nih.gov/REST/approximateTerm.json").mock(
        return_value=httpx.Response(200, json={"approximateGroup": {}})
    )

    report = _load_fixture("protein_mab_report.json")
    normalized = _pipeline(tmp_path).normalize_report(report, batch_id="batch-1")

    assert normalized.drugs[0].drug_class == DrugClass.PROTEIN


@respx.mock
def test_small_molecule_fixture_normalizes_correctly(tmp_path: Path) -> None:
    respx.get("https://rxnav.nlm.nih.gov/REST/approximateTerm.json").mock(
        return_value=httpx.Response(200, json={"approximateGroup": {}})
    )

    report = _load_fixture("small_molecule_report.json")
    normalized = _pipeline(tmp_path).normalize_report(report, batch_id="batch-1")

    assert normalized.drugs[0].drug_class == DrugClass.SMALL_MOLECULE


@respx.mock
def test_multi_version_amendment_fixtures_normalize_independently(tmp_path: Path) -> None:
    respx.get("https://rxnav.nlm.nih.gov/REST/approximateTerm.json").mock(
        return_value=httpx.Response(200, json={"approximateGroup": {}})
    )

    v1 = _load_fixture("multi_version_report_v1.json")
    v2 = _load_fixture("multi_version_report_v2.json")
    pipeline = _pipeline(tmp_path)

    normalized_v1 = pipeline.normalize_report(v1, batch_id="batch-1")
    normalized_v2 = pipeline.normalize_report(v2, batch_id="batch-2")

    assert normalized_v1.safetyreportid == normalized_v2.safetyreportid == "10000005"
    assert normalized_v1.safetyreportversion == "1"
    assert normalized_v2.safetyreportversion == "2"
    assert len(normalized_v1.reactions) == 1
    assert len(normalized_v2.reactions) == 2
    assert normalized_v1.serious is False
    assert normalized_v2.serious is True
