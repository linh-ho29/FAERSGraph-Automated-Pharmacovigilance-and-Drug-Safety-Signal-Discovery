import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

_DDL = """
CREATE TABLE IF NOT EXISTS rxnorm_cache (
    query_term    TEXT PRIMARY KEY,
    rxcui         TEXT,
    rxnorm_name   TEXT,
    match_score   INTEGER,
    status        TEXT NOT NULL,
    cached_at     TEXT NOT NULL
);
"""

CacheStatus = Literal["matched", "unmatched"]


@dataclass(frozen=True)
class RxNormCacheEntry:
    query_term: str
    rxcui: str | None
    rxnorm_name: str | None
    match_score: int | None
    status: CacheStatus


class RxNormCache:
    """SQLite-backed cache keyed on normalized (lowercased/trimmed) query term. Caches BOTH
    positive matches and negative ("unmatched") results, so re-running normalization never
    re-queries RxNav for drug names already known to have no match."""

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(_DDL)

    @staticmethod
    def _normalize_key(term: str) -> str:
        return term.strip().lower()

    def get(self, term: str) -> RxNormCacheEntry | None:
        row = self._conn.execute(
            "SELECT * FROM rxnorm_cache WHERE query_term=?", (self._normalize_key(term),)
        ).fetchone()
        if row is None:
            return None
        return RxNormCacheEntry(
            query_term=row["query_term"],
            rxcui=row["rxcui"],
            rxnorm_name=row["rxnorm_name"],
            match_score=row["match_score"],
            status=row["status"],
        )

    def put(
        self,
        term: str,
        *,
        rxcui: str | None,
        rxnorm_name: str | None,
        match_score: int | None,
    ) -> None:
        status: CacheStatus = "matched" if rxcui else "unmatched"
        key = self._normalize_key(term)
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT INTO rxnorm_cache (query_term, rxcui, rxnorm_name, match_score, status, cached_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(query_term) DO UPDATE SET
                rxcui=excluded.rxcui, rxnorm_name=excluded.rxnorm_name,
                match_score=excluded.match_score, status=excluded.status, cached_at=excluded.cached_at
            """,
            (key, rxcui, rxnorm_name, match_score, status, now),
        )

    def close(self) -> None:
        self._conn.close()
