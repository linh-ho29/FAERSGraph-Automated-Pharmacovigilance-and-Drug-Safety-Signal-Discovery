import json
from collections.abc import Iterator
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from faersgraph.models.normalized import NormalizedReport

from .drug_normalizer import normalize_drug
from .outcome_normalizer import normalize_seriousness
from .reaction_normalizer import MedDRAHierarchyProvider, normalize_reaction
from .rxnorm_cache import RxNormCache
from .rxnorm_client import RxNormClient


def _parse_fda_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except ValueError:
        return None


class NormalizationPipeline:
    """Walks a raw openFDA report's patient.drug[]/patient.reaction[] and assembles a
    NormalizedReport, shaped so a future Neo4j loader can map it directly to graph nodes/edges
    without redesign."""

    def __init__(
        self,
        rxnorm_client: RxNormClient,
        rxnorm_cache: RxNormCache,
        hierarchy_provider: MedDRAHierarchyProvider | None = None,
    ):
        self._rxnorm_client = rxnorm_client
        self._rxnorm_cache = rxnorm_cache
        self._hierarchy_provider = hierarchy_provider

    def normalize_report(self, raw_report: dict[str, Any], batch_id: str) -> NormalizedReport:
        patient = raw_report.get("patient") or {}
        drug_entries = patient.get("drug") or []
        reaction_entries = patient.get("reaction") or []

        drugs = [
            normalize_drug(entry, self._rxnorm_client, self._rxnorm_cache) for entry in drug_entries
        ]
        reactions = [
            normalize_reaction(
                entry["reactionmeddrapt"],
                outcome_code=entry.get("reactionoutcome"),
                hierarchy_provider=self._hierarchy_provider,
            )
            for entry in reaction_entries
            if entry.get("reactionmeddrapt")
        ]

        serious, seriousness_reasons = normalize_seriousness(raw_report)

        return NormalizedReport(
            safetyreportid=raw_report["safetyreportid"],
            safetyreportversion=raw_report.get("safetyreportversion") or "1",
            receivedate=_parse_fda_date(raw_report.get("receivedate")),
            receiptdate=_parse_fda_date(raw_report.get("receiptdate")),
            serious=serious,
            seriousness_reasons=seriousness_reasons,
            drugs=drugs,
            reactions=reactions,
            batch_id=batch_id,
            normalized_at=datetime.now(timezone.utc),
        )

    def normalize_raw_file(self, raw_file_path: Path | str, batch_id: str) -> Iterator[NormalizedReport]:
        """Streams a JSONL raw page one report at a time -- does not load the whole file."""
        with Path(raw_file_path).open("r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                yield self.normalize_report(json.loads(stripped), batch_id)
