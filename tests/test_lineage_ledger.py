from datetime import datetime, timezone
from pathlib import Path

import pytest

from faersgraph.lineage.ledger import LineageLedger


@pytest.fixture
def ledger(tmp_path: Path) -> LineageLedger:
    with LineageLedger(tmp_path / "test.sqlite") as ledger:
        yield ledger


def _now() -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_insert_new_report(ledger: LineageLedger) -> None:
    result = ledger.record_version(
        safetyreportid="X",
        safetyreportversion="1",
        batch_id="batch-1",
        raw_file_path="page_0.jsonl",
        line_offset=0,
        retrieved_at=_now(),
    )
    assert result == "inserted_new"
    latest = ledger.get_latest("X")
    assert latest is not None
    assert latest.latest_version == "1"


def test_duplicate_exact_version_is_skipped(ledger: LineageLedger) -> None:
    kwargs = dict(
        safetyreportid="X",
        safetyreportversion="1",
        batch_id="batch-1",
        raw_file_path="page_0.jsonl",
        line_offset=0,
        retrieved_at=_now(),
    )
    assert ledger.record_version(**kwargs) == "inserted_new"
    assert ledger.record_version(**kwargs) == "duplicate_skip"
    latest = ledger.get_latest("X")
    assert latest is not None and latest.latest_version == "1"


def test_newer_version_is_an_amendment(ledger: LineageLedger) -> None:
    ledger.record_version(
        safetyreportid="X",
        safetyreportversion="1",
        batch_id="batch-1",
        raw_file_path="page_0.jsonl",
        line_offset=0,
        retrieved_at=_now(),
    )
    result = ledger.record_version(
        safetyreportid="X",
        safetyreportversion="2",
        batch_id="batch-2",
        raw_file_path="page_0.jsonl",
        line_offset=1,
        retrieved_at=_now(),
    )
    assert result == "inserted_new_version_amendment"
    latest = ledger.get_latest("X")
    assert latest is not None and latest.latest_version == "2"
    assert ledger.has_been_amended_since("X", "1") is True
    assert ledger.has_been_amended_since("X", "2") is False


def test_out_of_order_older_version_does_not_move_latest(ledger: LineageLedger) -> None:
    ledger.record_version(
        safetyreportid="X",
        safetyreportversion="2",
        batch_id="batch-1",
        raw_file_path="page_0.jsonl",
        line_offset=0,
        retrieved_at=_now(),
    )
    result = ledger.record_version(
        safetyreportid="X",
        safetyreportversion="1",
        batch_id="batch-2",
        raw_file_path="page_1.jsonl",
        line_offset=0,
        retrieved_at=_now(),
    )
    assert result == "inserted_new"
    latest = ledger.get_latest("X")
    assert latest is not None and latest.latest_version == "2"
    versions = ledger.all_versions("X")
    assert [v.safetyreportversion for v in versions] == ["1", "2"]


def test_numeric_version_comparison_not_lexical(ledger: LineageLedger) -> None:
    ledger.record_version(
        safetyreportid="X",
        safetyreportversion="9",
        batch_id="batch-1",
        raw_file_path="page_0.jsonl",
        line_offset=0,
        retrieved_at=_now(),
    )
    result = ledger.record_version(
        safetyreportid="X",
        safetyreportversion="10",
        batch_id="batch-2",
        raw_file_path="page_1.jsonl",
        line_offset=0,
        retrieved_at=_now(),
    )
    assert result == "inserted_new_version_amendment"
    latest = ledger.get_latest("X")
    assert latest is not None and latest.latest_version == "10"


def test_get_latest_unknown_report_returns_none(ledger: LineageLedger) -> None:
    assert ledger.get_latest("does-not-exist") is None


def test_run_lifecycle(ledger: LineageLedger) -> None:
    ledger.start_run("batch-1", "sirna", "substance_name:patisiran")
    runs = ledger.recent_runs()
    assert runs[0]["status"] == "running"
    ledger.finish_run("batch-1", "completed")
    runs = ledger.recent_runs()
    assert runs[0]["status"] == "completed"
    assert runs[0]["finished_at"] is not None
