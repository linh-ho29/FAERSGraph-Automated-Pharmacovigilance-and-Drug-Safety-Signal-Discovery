import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone

from faersgraph.classification.drug_class import classify
from faersgraph.classification.types import DrugClass
from faersgraph.lineage.ledger import LineageLedger
from faersgraph.models.raw import OpenFDAMetaSnapshot, ProvenanceEnvelope
from faersgraph.openfda.client import OpenFDAClient
from faersgraph.openfda.query_builder import (
    build_date_range_fragment,
    build_search_fragment,
    combine_fragments,
)
from faersgraph.storage.raw_writer import RawBatchWriter

logger = logging.getLogger(__name__)


@dataclass
class IngestRunSummary:
    batch_id: str
    pages_fetched: int = 0
    reports_seen: int = 0
    new_versions: int = 0
    duplicate_versions: int = 0
    amended_versions: int = 0


class IngestService:
    """Orchestrates a single ingestion run: builds the search query, paginates openFDA, writes
    immutable raw pages, and records every (safetyreportid, version) in the lineage ledger."""

    def __init__(self, client: OpenFDAClient, writer: RawBatchWriter, ledger: LineageLedger):
        self._client = client
        self._writer = writer
        self._ledger = ledger

    def run(
        self,
        drug_class: DrugClass | None = None,
        date_range: tuple[date, date] | None = None,
        max_pages: int | None = None,
    ) -> IngestRunSummary:
        batch_id = str(uuid.uuid4())
        fragments = []
        if drug_class is not None:
            fragments.append(build_search_fragment(drug_class))
        if date_range is not None:
            fragments.append(build_date_range_fragment(*date_range))
        search = combine_fragments(*fragments)

        self._ledger.start_run(batch_id, drug_class.value if drug_class else None, search)
        summary = IngestRunSummary(batch_id=batch_id)
        status = "failed"
        try:
            for page in self._client.iter_reports(search=search):
                retrieved_at = datetime.now(timezone.utc)
                envelope = ProvenanceEnvelope(
                    batch_id=batch_id,
                    query_search=search,
                    query_limit=self._client.settings.openfda_page_size,
                    query_skip=page.meta.results.skip,
                    retrieved_at=retrieved_at,
                    openfda_meta=OpenFDAMetaSnapshot(
                        disclaimer=page.meta.disclaimer,
                        license=page.meta.license,
                        last_updated=page.meta.last_updated,
                        results_total=page.meta.results.total,
                    ),
                    source_url=self._client.settings.openfda_base_url,
                )

                if page.results:
                    page_ref = self._writer.write_page(envelope, page)
                    for line_offset, report in page_ref.iter_reports_with_offsets():
                        summary.reports_seen += 1
                        self._record_report(
                            report, batch_id, str(page_ref.file_path), line_offset,
                            retrieved_at, summary,
                        )

                summary.pages_fetched += 1
                if max_pages is not None and summary.pages_fetched >= max_pages:
                    break
            status = "completed"
        finally:
            self._ledger.finish_run(batch_id, status)
        return summary

    def _record_report(
        self,
        report: dict,
        batch_id: str,
        raw_file_path: str,
        line_offset: int,
        retrieved_at: datetime,
        summary: IngestRunSummary,
    ) -> None:
        safetyreportid = report.get("safetyreportid")
        safetyreportversion = report.get("safetyreportversion") or "1"
        if not safetyreportid:
            logger.warning("Skipping report with no safetyreportid at %s:%s", raw_file_path, line_offset)
            return

        drug_class_hint = self._best_effort_class_hint(report)
        result = self._ledger.record_version(
            safetyreportid=safetyreportid,
            safetyreportversion=safetyreportversion,
            batch_id=batch_id,
            raw_file_path=raw_file_path,
            line_offset=line_offset,
            retrieved_at=retrieved_at,
            drug_class_hint=drug_class_hint.value if drug_class_hint else None,
        )
        if result == "duplicate_skip":
            summary.duplicate_versions += 1
        elif result == "inserted_new_version_amendment":
            summary.amended_versions += 1
        else:
            summary.new_versions += 1

    @staticmethod
    def _best_effort_class_hint(report: dict) -> DrugClass | None:
        """classify() is client-side ground truth (see classification.drug_class), applied here
        per-report (not per-drug) just to tag a single representative hint on the lineage row.
        The full per-drug classification lives in the normalized output, not here."""
        patient = report.get("patient") or {}
        drugs = patient.get("drug") or []
        if not drugs:
            return None
        counts: dict[DrugClass, int] = {}
        for drug_entry in drugs:
            result = classify(drug_entry)
            counts[result.drug_class] = counts.get(result.drug_class, 0) + 1
        for preferred in (DrugClass.SIRNA, DrugClass.PROTEIN, DrugClass.PEPTIDE):
            if preferred in counts:
                return preferred
        if counts:
            return max(counts, key=lambda k: counts[k])
        return None
