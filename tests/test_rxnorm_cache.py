from pathlib import Path

from faersgraph.normalization.rxnorm_cache import RxNormCache


def test_cache_miss_returns_none(tmp_path: Path) -> None:
    cache = RxNormCache(tmp_path / "cache.sqlite")
    assert cache.get("patisiran") is None


def test_put_then_get_round_trips_match(tmp_path: Path) -> None:
    cache = RxNormCache(tmp_path / "cache.sqlite")
    cache.put("Patisiran", rxcui="1991661", rxnorm_name="Patisiran", match_score=100)

    entry = cache.get("  patisiran  ")  # key normalization: trim/lowercase
    assert entry is not None
    assert entry.rxcui == "1991661"
    assert entry.status == "matched"


def test_put_unmatched_result_round_trips_without_rxcui(tmp_path: Path) -> None:
    cache = RxNormCache(tmp_path / "cache.sqlite")
    cache.put("totally made up drug", rxcui=None, rxnorm_name=None, match_score=None)

    entry = cache.get("totally made up drug")
    assert entry is not None
    assert entry.rxcui is None
    assert entry.status == "unmatched"


def test_put_overwrites_existing_entry(tmp_path: Path) -> None:
    cache = RxNormCache(tmp_path / "cache.sqlite")
    cache.put("x", rxcui=None, rxnorm_name=None, match_score=None)
    cache.put("x", rxcui="123", rxnorm_name="X Ingredient", match_score=90)

    entry = cache.get("x")
    assert entry is not None
    assert entry.rxcui == "123"
    assert entry.status == "matched"
