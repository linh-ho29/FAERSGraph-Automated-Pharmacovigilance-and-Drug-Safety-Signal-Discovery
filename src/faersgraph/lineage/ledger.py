import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

SCHEMA_PATH = Path(__file__).parent / "schema.sql"

RecordResult = Literal["inserted_new", "duplicate_skip", "inserted_new_version_amendment"]
RunStatus = Literal["completed", "failed"]


@dataclass(frozen=True)
class LatestVersionInfo:
    safetyreportid: str
    latest_version: str
    latest_batch_id: str
    updated_at: str


@dataclass(frozen=True)
class ReportVersionRecord:
    safetyreportid: str
    safetyreportversion: str
    batch_id: str
    raw_file_path: str
    line_offset: int
    retrieved_at: str
    drug_class_hint: str | None
    first_observed_at: str


def _version_sort_key(version: str) -> tuple[int, object]:
    """Numeric-first key so '10' sorts after '9'; falls back to lexical string compare."""
    try:
        return (0, int(version))
    except ValueError:
        return (1, version)


def _is_newer(candidate: str, existing: str) -> bool:
    return _version_sort_key(candidate) > _version_sort_key(existing)


class LineageLedger:
    """SQLite-backed provenance/versioning ledger.

    Primary key (safetyreportid, safetyreportversion) on report_version makes re-recording an
    already-seen exact version a no-op, so re-running ingestion is idempotent. report_latest is a
    derived pointer updated only when a numerically newer version arrives.
    """

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(SCHEMA_PATH.read_text())

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "LineageLedger":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def record_version(
        self,
        *,
        safetyreportid: str,
        safetyreportversion: str,
        batch_id: str,
        raw_file_path: str,
        line_offset: int,
        retrieved_at: datetime,
        drug_class_hint: str | None = None,
    ) -> RecordResult:
        retrieved_at_iso = retrieved_at.astimezone(timezone.utc).isoformat()
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            existing = conn.execute(
                "SELECT 1 FROM report_version WHERE safetyreportid=? AND safetyreportversion=?",
                (safetyreportid, safetyreportversion),
            ).fetchone()
            if existing is not None:
                conn.execute("COMMIT")
                return "duplicate_skip"

            conn.execute(
                """
                INSERT INTO report_version
                    (safetyreportid, safetyreportversion, batch_id, raw_file_path,
                     line_offset, retrieved_at, drug_class_hint, first_observed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    safetyreportid,
                    safetyreportversion,
                    batch_id,
                    raw_file_path,
                    line_offset,
                    retrieved_at_iso,
                    drug_class_hint,
                    retrieved_at_iso,
                ),
            )

            latest_row = conn.execute(
                "SELECT latest_version FROM report_latest WHERE safetyreportid=?",
                (safetyreportid,),
            ).fetchone()

            if latest_row is None:
                conn.execute(
                    """
                    INSERT INTO report_latest (safetyreportid, latest_version, latest_batch_id, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (safetyreportid, safetyreportversion, batch_id, retrieved_at_iso),
                )
                result: RecordResult = "inserted_new"
            elif _is_newer(safetyreportversion, latest_row["latest_version"]):
                conn.execute(
                    """
                    UPDATE report_latest
                    SET latest_version=?, latest_batch_id=?, updated_at=?
                    WHERE safetyreportid=?
                    """,
                    (safetyreportversion, batch_id, retrieved_at_iso, safetyreportid),
                )
                result = "inserted_new_version_amendment"
            else:
                # Out-of-order older version arriving after a newer one is already known:
                # history is preserved above, but the latest pointer is left untouched.
                result = "inserted_new"

            conn.execute("COMMIT")
            return result
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def get_latest(self, safetyreportid: str) -> LatestVersionInfo | None:
        row = self._conn.execute(
            "SELECT safetyreportid, latest_version, latest_batch_id, updated_at "
            "FROM report_latest WHERE safetyreportid=?",
            (safetyreportid,),
        ).fetchone()
        return LatestVersionInfo(**dict(row)) if row else None

    def has_been_amended_since(self, safetyreportid: str, known_version: str) -> bool:
        latest = self.get_latest(safetyreportid)
        if latest is None:
            return False
        return _is_newer(latest.latest_version, known_version)

    def all_versions(self, safetyreportid: str) -> list[ReportVersionRecord]:
        rows = self._conn.execute(
            """
            SELECT safetyreportid, safetyreportversion, batch_id, raw_file_path,
                   line_offset, retrieved_at, drug_class_hint, first_observed_at
            FROM report_version
            WHERE safetyreportid=?
            ORDER BY first_observed_at ASC
            """,
            (safetyreportid,),
        ).fetchall()
        return sorted(
            (ReportVersionRecord(**dict(row)) for row in rows),
            key=lambda r: _version_sort_key(r.safetyreportversion),
        )

    def start_run(self, batch_id: str, drug_class: str | None, search_query: str) -> None:
        self._conn.execute(
            """
            INSERT INTO ingestion_run (batch_id, started_at, drug_class, search_query, status)
            VALUES (?, ?, ?, ?, 'running')
            """,
            (batch_id, datetime.now(timezone.utc).isoformat(), drug_class, search_query),
        )

    def finish_run(self, batch_id: str, status: RunStatus) -> None:
        self._conn.execute(
            "UPDATE ingestion_run SET finished_at=?, status=? WHERE batch_id=?",
            (datetime.now(timezone.utc).isoformat(), status, batch_id),
        )

    def recent_runs(self, limit: int = 10) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM ingestion_run ORDER BY started_at DESC LIMIT ?", (limit,)
        ).fetchall()
