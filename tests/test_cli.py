from pathlib import Path

import httpx
import pytest
import respx
from typer.testing import CliRunner

from faersgraph.cli import app
from faersgraph.config import get_settings

runner = CliRunner()


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FAERSGRAPH_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


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


def _report(report_id: str) -> dict:
    return {
        "safetyreportid": report_id,
        "safetyreportversion": "1",
        "serious": "1",
        "patient": {
            "drug": [{"medicinalproduct": "ONPATTRO", "openfda": {"substance_name": ["PATISIRAN"]}}],
            "reaction": [{"reactionmeddrapt": "Nausea", "reactionoutcome": "1"}],
        },
    }


@respx.mock
def test_ingest_command_runs_and_prints_summary(tmp_path: Path) -> None:
    respx.get("https://api.fda.gov/drug/event.json").mock(
        return_value=httpx.Response(200, json=_page_body([_report("1")], 0, 100, 1))
    )

    result = runner.invoke(app, ["ingest", "--drug-class", "sirna", "--max-pages", "1"])

    assert result.exit_code == 0, result.output
    assert "Ingest run" in result.output
    assert "Reports seen" in result.output


@respx.mock
def test_normalize_command_after_ingest(tmp_path: Path) -> None:
    respx.get("https://api.fda.gov/drug/event.json").mock(
        return_value=httpx.Response(200, json=_page_body([_report("1")], 0, 100, 1))
    )
    respx.get("https://rxnav.nlm.nih.gov/REST/approximateTerm.json").mock(
        return_value=httpx.Response(200, json={"approximateGroup": {}})
    )

    ingest_result = runner.invoke(app, ["ingest", "--drug-class", "sirna", "--max-pages", "1"])
    assert ingest_result.exit_code == 0, ingest_result.output

    out_path = tmp_path / "normalized.jsonl"
    normalize_result = runner.invoke(app, ["normalize", "--out", str(out_path)])

    assert normalize_result.exit_code == 0, normalize_result.output
    assert "Reports normalized" in normalize_result.output
    assert out_path.exists()
    lines = out_path.read_text().strip().splitlines()
    assert len(lines) == 1


@respx.mock
def test_lineage_status_command(tmp_path: Path) -> None:
    respx.get("https://api.fda.gov/drug/event.json").mock(
        return_value=httpx.Response(200, json=_page_body([_report("1")], 0, 100, 1))
    )
    runner.invoke(app, ["ingest", "--drug-class", "sirna", "--max-pages", "1"])

    result = runner.invoke(app, ["lineage", "--status"])

    assert result.exit_code == 0, result.output
    assert "Remaining openFDA requests today" in result.output
    assert "Recent ingestion runs" in result.output


@respx.mock
def test_lineage_safetyreportid_command(tmp_path: Path) -> None:
    respx.get("https://api.fda.gov/drug/event.json").mock(
        return_value=httpx.Response(200, json=_page_body([_report("42")], 0, 100, 1))
    )
    runner.invoke(app, ["ingest", "--drug-class", "sirna", "--max-pages", "1"])

    result = runner.invoke(app, ["lineage", "--safetyreportid", "42"])

    assert result.exit_code == 0, result.output
    assert "Version history for report 42" in result.output


def test_lineage_requires_safetyreportid_or_status() -> None:
    result = runner.invoke(app, ["lineage"])
    assert result.exit_code == 1
