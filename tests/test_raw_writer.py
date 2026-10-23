from datetime import datetime, timezone
from pathlib import Path

import pytest

from faersgraph.models.raw import OpenFDAMetaSnapshot, ProvenanceEnvelope
from faersgraph.openfda.models import OpenFDAMeta, OpenFDAResponse, OpenFDAResultsMeta
from faersgraph.storage.raw_writer import RawBatchWriter


def _envelope(batch_id: str = "batch-1", skip: int = 0) -> ProvenanceEnvelope:
    return ProvenanceEnvelope(
        batch_id=batch_id,
        query_search="substance_name:patisiran",
        query_limit=100,
        query_skip=skip,
        retrieved_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        openfda_meta=OpenFDAMetaSnapshot(
            disclaimer="d", license="l", last_updated="2026-01-01", results_total=2
        ),
        source_url="https://api.fda.gov/drug/event.json?search=substance_name:patisiran",
    )


def _response(reports: list[dict]) -> OpenFDAResponse:
    return OpenFDAResponse(
        meta=OpenFDAMeta(results=OpenFDAResultsMeta(skip=0, limit=100, total=len(reports))),
        results=reports,
    )


def test_write_page_creates_jsonl_and_meta(tmp_path: Path) -> None:
    writer = RawBatchWriter(tmp_path)
    reports = [{"safetyreportid": "1", "safetyreportversion": "1"}]
    ref = writer.write_page(_envelope(), _response(reports))

    assert ref.file_path.exists()
    assert ref.meta_path.exists()
    assert ref.file_path.name == "page_000000.jsonl"
    assert ref.meta_path.name == "page_000000.meta.json"


def test_write_page_refuses_to_overwrite(tmp_path: Path) -> None:
    writer = RawBatchWriter(tmp_path)
    reports = [{"safetyreportid": "1", "safetyreportversion": "1"}]
    writer.write_page(_envelope(), _response(reports))

    with pytest.raises(FileExistsError):
        writer.write_page(_envelope(), _response(reports))


def test_iter_reports_with_offsets_round_trips(tmp_path: Path) -> None:
    writer = RawBatchWriter(tmp_path)
    reports = [
        {"safetyreportid": "1", "safetyreportversion": "1"},
        {"safetyreportid": "2", "safetyreportversion": "1"},
    ]
    ref = writer.write_page(_envelope(), _response(reports))

    pairs = list(ref.iter_reports_with_offsets())
    assert [offset for offset, _ in pairs] == [0, 1]
    assert [report["safetyreportid"] for _, report in pairs] == ["1", "2"]


def test_different_batches_or_skips_do_not_collide(tmp_path: Path) -> None:
    writer = RawBatchWriter(tmp_path)
    writer.write_page(_envelope(batch_id="batch-1", skip=0), _response([{"safetyreportid": "1", "safetyreportversion": "1"}]))
    ref2 = writer.write_page(_envelope(batch_id="batch-1", skip=100), _response([{"safetyreportid": "2", "safetyreportversion": "1"}]))
    ref3 = writer.write_page(_envelope(batch_id="batch-2", skip=0), _response([{"safetyreportid": "3", "safetyreportversion": "1"}]))

    assert ref2.file_path != ref3.file_path
