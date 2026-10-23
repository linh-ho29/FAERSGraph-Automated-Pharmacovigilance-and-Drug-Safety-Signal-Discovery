import logging
from pathlib import Path

import httpx
import respx

from faersgraph.config import Settings
from faersgraph.openfda.client import OpenFDAClient
from faersgraph.openfda.rate_limiter import DailyQuotaTracker, RateLimiter, SlidingWindowRateLimiter


def _settings(**overrides) -> Settings:
    defaults = dict(
        openfda_base_url="https://api.fda.gov/drug/event.json",
        openfda_page_size=2,
        openfda_max_skip=25000,
        http_max_retries=3,
        http_timeout_seconds=5.0,
    )
    defaults.update(overrides)
    return Settings(**defaults)


def _rate_limiter(tmp_path: Path) -> RateLimiter:
    sliding = SlidingWindowRateLimiter(limit_per_min=10_000, sleep_fn=lambda s: None)
    daily = DailyQuotaTracker(tmp_path / "quota.sqlite", limit_per_day=10_000)
    return RateLimiter(sliding, daily)


def _page_body(results: list[dict], skip: int, limit: int, total: int) -> dict:
    return {
        "meta": {
            "disclaimer": "d",
            "license": "l",
            "last_updated": "2026-01-01",
            "results": {"skip": skip, "limit": limit, "total": total},
        },
        "results": results,
    }


@respx.mock
def test_iter_reports_paginates_until_exhausted(tmp_path: Path) -> None:
    route = respx.get("https://api.fda.gov/drug/event.json")
    route.side_effect = [
        httpx.Response(200, json=_page_body([{"safetyreportid": "1"}, {"safetyreportid": "2"}], 0, 2, 3)),
        httpx.Response(200, json=_page_body([{"safetyreportid": "3"}], 2, 2, 3)),
    ]

    client = OpenFDAClient(_settings(), _rate_limiter(tmp_path))
    pages = list(client.iter_reports(search="substance_name:x"))

    assert len(pages) == 2
    assert [r["safetyreportid"] for r in pages[0].results] == ["1", "2"]
    assert [r["safetyreportid"] for r in pages[1].results] == ["3"]


@respx.mock
def test_iter_reports_stops_on_empty_page(tmp_path: Path) -> None:
    route = respx.get("https://api.fda.gov/drug/event.json")
    route.side_effect = [
        httpx.Response(200, json=_page_body([{"safetyreportid": "1"}], 0, 2, 100)),
        httpx.Response(200, json=_page_body([], 2, 2, 100)),
    ]

    client = OpenFDAClient(_settings(), _rate_limiter(tmp_path))
    pages = list(client.iter_reports(search="substance_name:x"))

    assert len(pages) == 2
    assert pages[1].results == []


@respx.mock
def test_fetch_page_retries_on_transient_500(tmp_path: Path) -> None:
    route = respx.get("https://api.fda.gov/drug/event.json")
    route.side_effect = [
        httpx.Response(500, text="server error"),
        httpx.Response(200, json=_page_body([{"safetyreportid": "1"}], 0, 2, 1)),
    ]

    client = OpenFDAClient(_settings(), _rate_limiter(tmp_path))
    page = client.fetch_page("x", 2, 0)

    assert route.call_count == 2
    assert page.results[0]["safetyreportid"] == "1"


@respx.mock
def test_fetch_page_honors_retry_after_header(tmp_path: Path, monkeypatch) -> None:
    route = respx.get("https://api.fda.gov/drug/event.json")
    route.side_effect = [
        httpx.Response(429, headers={"Retry-After": "2"}),
        httpx.Response(200, json=_page_body([{"safetyreportid": "1"}], 0, 2, 1)),
    ]

    sleep_calls: list[float] = []
    monkeypatch.setattr("time.sleep", lambda s: sleep_calls.append(s))

    client = OpenFDAClient(_settings(), _rate_limiter(tmp_path))
    page = client.fetch_page("x", 2, 0)

    assert page.results[0]["safetyreportid"] == "1"
    assert 2.0 in sleep_calls


@respx.mock
def test_zero_results_not_found_treated_as_empty_page(tmp_path: Path) -> None:
    route = respx.get("https://api.fda.gov/drug/event.json")
    route.mock(
        return_value=httpx.Response(
            404, json={"error": {"code": "NOT_FOUND", "message": "No matches found!"}}
        )
    )

    client = OpenFDAClient(_settings(), _rate_limiter(tmp_path))
    page = client.fetch_page("substance_name:doesnotexist", 2, 0)

    assert page.results == []


@respx.mock
def test_max_skip_guard_stops_pagination_and_warns(tmp_path: Path, caplog) -> None:
    route = respx.get("https://api.fda.gov/drug/event.json")
    route.side_effect = [
        httpx.Response(200, json=_page_body([{"safetyreportid": "1"}, {"safetyreportid": "2"}], 0, 2, 100)),
        httpx.Response(200, json=_page_body([{"safetyreportid": "3"}, {"safetyreportid": "4"}], 2, 2, 100)),
    ]

    client = OpenFDAClient(_settings(), _rate_limiter(tmp_path))
    with caplog.at_level(logging.WARNING):
        pages = list(client.iter_reports(search="x", page_size=2, max_skip=2))

    assert len(pages) == 2
    assert any("max_skip" in record.message or "Stopping pagination" in record.message for record in caplog.records)
