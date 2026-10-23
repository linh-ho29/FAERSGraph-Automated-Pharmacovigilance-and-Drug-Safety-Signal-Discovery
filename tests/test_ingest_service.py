from pathlib import Path

import httpx
import respx

from faersgraph.classification.types import DrugClass
from faersgraph.config import Settings
from faersgraph.ingestion.ingest_service import IngestService
from faersgraph.lineage.ledger import LineageLedger
from faersgraph.openfda.client import OpenFDAClient
from faersgraph.openfda.rate_limiter import DailyQuotaTracker, RateLimiter, SlidingWindowRateLimiter
from faersgraph.storage.raw_writer import RawBatchWriter


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        openfda_base_url="https://api.fda.gov/drug/event.json",
        openfda_page_size=2,
        raw_dir=tmp_path / "raw",
        db_path=tmp_path / "db" / "faersgraph.sqlite",
    )


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


def _report(report_id: str, version: str = "1", substance: str = "PATISIRAN") -> dict:
    return {
        "safetyreportid": report_id,
        "safetyreportversion": version,
        "patient": {
            "drug": [
                {
                    "medicinalproduct": substance,
                    "openfda": {"substance_name": [substance]},
                }
            ],
            "reaction": [{"reactionmeddrapt": "Nausea"}],
        },
    }


@respx.mock
def test_ingest_run_writes_raw_pages_and_lineage(tmp_path: Path) -> None:
    respx.get("https://api.fda.gov/drug/event.json").mock(
        return_value=httpx.Response(
            200, json=_page_body([_report("1"), _report("2")], 0, 2, 2)
        )
    )

    settings = _settings(tmp_path)
    sliding = SlidingWindowRateLimiter(limit_per_min=10_000, sleep_fn=lambda s: None)
    daily = DailyQuotaTracker(settings.db_path, limit_per_day=10_000)
    rate_limiter = RateLimiter(sliding, daily)
    client = OpenFDAClient(settings, rate_limiter)
    writer = RawBatchWriter(settings.raw_dir)
    ledger = LineageLedger(settings.db_path)

    service = IngestService(client, writer, ledger)
    summary = service.run(drug_class=DrugClass.SIRNA)

    assert summary.reports_seen == 2
    assert summary.new_versions == 2
    assert summary.duplicate_versions == 0
    assert ledger.get_latest("1") is not None
    raw_files = list((settings.raw_dir / summary.batch_id).glob("*.jsonl"))
    assert len(raw_files) == 1


@respx.mock
def test_rerunning_ingest_is_idempotent_in_the_ledger(tmp_path: Path) -> None:
    route = respx.get("https://api.fda.gov/drug/event.json")
    route.mock(return_value=httpx.Response(200, json=_page_body([_report("1")], 0, 2, 1)))

    settings = _settings(tmp_path)
    sliding = SlidingWindowRateLimiter(limit_per_min=10_000, sleep_fn=lambda s: None)
    daily = DailyQuotaTracker(settings.db_path, limit_per_day=10_000)
    rate_limiter = RateLimiter(sliding, daily)
    client = OpenFDAClient(settings, rate_limiter)
    writer = RawBatchWriter(settings.raw_dir)
    ledger = LineageLedger(settings.db_path)

    service = IngestService(client, writer, ledger)
    first = service.run(drug_class=DrugClass.SIRNA)
    second = service.run(drug_class=DrugClass.SIRNA)

    assert first.new_versions == 1
    assert second.duplicate_versions == 1
    assert second.new_versions == 0


@respx.mock
def test_max_pages_caps_pagination(tmp_path: Path) -> None:
    route = respx.get("https://api.fda.gov/drug/event.json")
    route.side_effect = [
        httpx.Response(200, json=_page_body([_report("1"), _report("2")], 0, 2, 100)),
        httpx.Response(200, json=_page_body([_report("3"), _report("4")], 2, 2, 100)),
    ]

    settings = _settings(tmp_path)
    sliding = SlidingWindowRateLimiter(limit_per_min=10_000, sleep_fn=lambda s: None)
    daily = DailyQuotaTracker(settings.db_path, limit_per_day=10_000)
    rate_limiter = RateLimiter(sliding, daily)
    client = OpenFDAClient(settings, rate_limiter)
    writer = RawBatchWriter(settings.raw_dir)
    ledger = LineageLedger(settings.db_path)

    service = IngestService(client, writer, ledger)
    summary = service.run(drug_class=DrugClass.SIRNA, max_pages=1)

    assert summary.pages_fetched == 1
    assert summary.reports_seen == 2
