import logging
from datetime import date
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from faersgraph.classification.types import DrugClass
from faersgraph.config import Settings, get_settings
from faersgraph.ingestion.ingest_service import IngestService
from faersgraph.lineage.ledger import LineageLedger
from faersgraph.normalization.pipeline import NormalizationPipeline
from faersgraph.normalization.rxnorm_cache import RxNormCache
from faersgraph.normalization.rxnorm_client import RxNormClient
from faersgraph.openfda.client import OpenFDAClient
from faersgraph.openfda.rate_limiter import DailyQuotaTracker, RateLimiter, SlidingWindowRateLimiter
from faersgraph.storage.raw_writer import RawBatchWriter

app = typer.Typer(help="FAERSGraph: openFDA/FAERS ingestion, provenance, and normalization pipeline.")
console = Console()


def _configure_logging(settings: Settings) -> None:
    logging.basicConfig(level=settings.log_level, format="%(levelname)s %(name)s: %(message)s")


def _build_rate_limiter(settings: Settings) -> RateLimiter:
    sliding = SlidingWindowRateLimiter(limit_per_min=settings.openfda_rate_limit_per_min)
    daily = DailyQuotaTracker(settings.db_path, limit_per_day=settings.openfda_rate_limit_per_day)
    return RateLimiter(sliding, daily)


@app.command()
def ingest(
    drug_class: DrugClass | None = typer.Option(
        None, "--drug-class", help="Restrict to one drug class; omit to fetch unfiltered."
    ),
    start_date: str | None = typer.Option(None, "--start-date", help="YYYY-MM-DD"),
    end_date: str | None = typer.Option(None, "--end-date", help="YYYY-MM-DD"),
    max_pages: int | None = typer.Option(
        None, "--max-pages", help="Cap pages fetched this run (quota safety)."
    ),
) -> None:
    """Fetch openFDA drug-event reports, preserving provenance and version lineage."""
    settings = get_settings()
    _configure_logging(settings)

    rate_limiter = _build_rate_limiter(settings)
    client = OpenFDAClient(settings, rate_limiter)
    writer = RawBatchWriter(settings.raw_dir)

    date_range = None
    if start_date and end_date:
        date_range = (date.fromisoformat(start_date), date.fromisoformat(end_date))

    with LineageLedger(settings.db_path) as ledger:
        service = IngestService(client, writer, ledger)
        summary = service.run(drug_class=drug_class, date_range=date_range, max_pages=max_pages)

    table = Table(title=f"Ingest run {summary.batch_id}")
    table.add_column("Metric")
    table.add_column("Count", justify="right")
    table.add_row("Pages fetched", str(summary.pages_fetched))
    table.add_row("Reports seen", str(summary.reports_seen))
    table.add_row("New versions", str(summary.new_versions))
    table.add_row("Amended versions", str(summary.amended_versions))
    table.add_row("Duplicate (already known)", str(summary.duplicate_versions))
    console.print(table)


@app.command()
def normalize(
    batch_id: str | None = typer.Option(
        None, "--batch-id", help="Normalize only this batch; omit to normalize all raw batches."
    ),
    out: Path = typer.Option(Path("data/processed/normalized.jsonl"), "--out"),
) -> None:
    """Normalize raw ingested reports (drug/reaction/outcome terminology) into NormalizedReport JSONL."""
    settings = get_settings()
    _configure_logging(settings)

    client = RxNormClient(settings)
    cache = RxNormCache(settings.db_path)
    pipeline = NormalizationPipeline(client, cache)

    if batch_id:
        batch_dirs = [settings.raw_dir / batch_id]
    elif settings.raw_dir.exists():
        batch_dirs = [d for d in sorted(settings.raw_dir.iterdir()) if d.is_dir()]
    else:
        batch_dirs = []

    out.parent.mkdir(parents=True, exist_ok=True)
    total_reports = 0
    matched_drugs = 0
    unmatched_drugs = 0

    with out.open("w", encoding="utf-8") as out_file:
        for batch_dir in batch_dirs:
            if not batch_dir.exists():
                console.print(f"[yellow]No such batch directory: {batch_dir}[/yellow]")
                continue
            for raw_file in sorted(batch_dir.glob("page_*.jsonl")):
                for normalized_report in pipeline.normalize_raw_file(raw_file, batch_id=batch_dir.name):
                    out_file.write(normalized_report.model_dump_json())
                    out_file.write("\n")
                    total_reports += 1
                    for drug in normalized_report.drugs:
                        if drug.rxcui:
                            matched_drugs += 1
                        else:
                            unmatched_drugs += 1

    table = Table(title="Normalization summary")
    table.add_column("Metric")
    table.add_column("Count", justify="right")
    table.add_row("Reports normalized", str(total_reports))
    table.add_row("Drug entries RxNorm-matched", str(matched_drugs))
    table.add_row("Drug entries unmatched", str(unmatched_drugs))
    table.add_row("Output file", str(out))
    console.print(table)


@app.command()
def lineage(
    safetyreportid: str | None = typer.Option(None, "--safetyreportid"),
    status: bool = typer.Option(False, "--status", help="Show daily quota + recent run history."),
) -> None:
    """Inspect version lineage for a report, or show daily-quota/run status."""
    settings = get_settings()
    _configure_logging(settings)

    with LineageLedger(settings.db_path) as ledger:
        if status:
            daily = DailyQuotaTracker(settings.db_path, limit_per_day=settings.openfda_rate_limit_per_day)
            console.print(
                f"Remaining openFDA requests today: "
                f"{daily.remaining_today()} / {settings.openfda_rate_limit_per_day}"
            )
            table = Table(title="Recent ingestion runs")
            table.add_column("Batch ID")
            table.add_column("Drug class")
            table.add_column("Status")
            table.add_column("Started at")
            for run in ledger.recent_runs():
                table.add_row(run["batch_id"], run["drug_class"] or "-", run["status"], run["started_at"])
            console.print(table)
            return

        if not safetyreportid:
            console.print("[red]Provide --safetyreportid or --status[/red]")
            raise typer.Exit(code=1)

        versions = ledger.all_versions(safetyreportid)
        if not versions:
            console.print(f"No known versions for report {safetyreportid}")
            raise typer.Exit(code=1)

        table = Table(title=f"Version history for report {safetyreportid}")
        table.add_column("Version")
        table.add_column("Batch ID")
        table.add_column("Retrieved at")
        table.add_column("Drug class hint")
        for version in versions:
            table.add_row(
                version.safetyreportversion,
                version.batch_id,
                version.retrieved_at,
                version.drug_class_hint or "-",
            )
        console.print(table)


if __name__ == "__main__":
    app()
