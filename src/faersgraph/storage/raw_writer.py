import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from faersgraph.models.raw import ProvenanceEnvelope
from faersgraph.openfda.models import OpenFDAResponse


@dataclass(frozen=True)
class RawPageRef:
    file_path: Path
    meta_path: Path
    batch_id: str
    skip: int

    def iter_reports_with_offsets(self) -> Iterator[tuple[int, dict[str, Any]]]:
        with self.file_path.open("r", encoding="utf-8") as f:
            for line_offset, line in enumerate(f):
                stripped = line.strip()
                if not stripped:
                    continue
                yield line_offset, json.loads(stripped)


class RawBatchWriter:
    """Writes immutable raw openFDA pages as JSONL + a provenance sidecar.

    Filenames are deterministic per (batch_id, skip). `write_page` refuses to overwrite an
    existing page -- raw data, once written, is never mutated. JSONL (not a single JSON array)
    is used so a report's position can be addressed by a stable, cheap line offset without
    re-parsing the whole page.
    """

    def __init__(self, raw_dir: Path | str):
        self.raw_dir = Path(raw_dir)

    def write_page(self, envelope: ProvenanceEnvelope, response: OpenFDAResponse) -> RawPageRef:
        batch_dir = self.raw_dir / envelope.batch_id
        batch_dir.mkdir(parents=True, exist_ok=True)
        skip = envelope.query_skip
        file_path = batch_dir / f"page_{skip:06d}.jsonl"
        meta_path = batch_dir / f"page_{skip:06d}.meta.json"
        if file_path.exists() or meta_path.exists():
            raise FileExistsError(f"Raw page already exists and is immutable: {file_path}")

        with file_path.open("w", encoding="utf-8") as f:
            for report in response.results:
                f.write(json.dumps(report, sort_keys=True))
                f.write("\n")

        meta_path.write_text(envelope.model_dump_json(indent=2), encoding="utf-8")

        return RawPageRef(
            file_path=file_path, meta_path=meta_path, batch_id=envelope.batch_id, skip=skip
        )
