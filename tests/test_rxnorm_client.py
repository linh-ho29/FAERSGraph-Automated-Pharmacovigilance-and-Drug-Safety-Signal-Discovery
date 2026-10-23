import httpx
import respx

from faersgraph.config import Settings
from faersgraph.normalization.rxnorm_client import RxNormClient


def _settings() -> Settings:
    return Settings(rxnorm_base_url="https://rxnav.nlm.nih.gov/REST")


@respx.mock
def test_approximate_match_parses_and_sorts_by_score() -> None:
    respx.get("https://rxnav.nlm.nih.gov/REST/approximateTerm.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "approximateGroup": {
                    "inputTerm": "patisiran",
                    "candidate": [
                        {"rxcui": "1991660", "score": "80", "rxaui": "111"},
                        {"rxcui": "1991661", "score": "100", "rxaui": "222"},
                    ],
                }
            },
        )
    )

    client = RxNormClient(_settings())
    candidates = client.approximate_match("patisiran")

    assert [c.rxcui for c in candidates] == ["1991661", "1991660"]
    assert candidates[0].score == 100


@respx.mock
def test_approximate_match_handles_no_candidates() -> None:
    respx.get("https://rxnav.nlm.nih.gov/REST/approximateTerm.json").mock(
        return_value=httpx.Response(200, json={"approximateGroup": {"inputTerm": "zzz"}})
    )

    client = RxNormClient(_settings())
    candidates = client.approximate_match("zzz")

    assert candidates == []


@respx.mock
def test_get_ingredient_name() -> None:
    respx.get("https://rxnav.nlm.nih.gov/REST/rxcui/1991661/property.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "propConceptGroup": {
                    "propConcept": [
                        {"propCategory": "NAMES", "propName": "RxNorm Name", "propValue": "Patisiran"}
                    ]
                }
            },
        )
    )

    client = RxNormClient(_settings())
    name = client.get_ingredient_name("1991661")

    assert name == "Patisiran"


@respx.mock
def test_get_ingredient_name_returns_none_when_absent() -> None:
    respx.get("https://rxnav.nlm.nih.gov/REST/rxcui/0/property.json").mock(
        return_value=httpx.Response(200, json={"propConceptGroup": {}})
    )

    client = RxNormClient(_settings())
    assert client.get_ingredient_name("0") is None


@respx.mock
def test_approximate_match_retries_on_transient_error() -> None:
    route = respx.get("https://rxnav.nlm.nih.gov/REST/approximateTerm.json")
    route.side_effect = [
        httpx.TransportError("boom"),
        httpx.Response(
            200,
            json={
                "approximateGroup": {
                    "candidate": [{"rxcui": "1", "score": "50"}],
                }
            },
        ),
    ]

    client = RxNormClient(_settings())
    candidates = client.approximate_match("x")

    assert route.call_count == 2
    assert candidates[0].rxcui == "1"
