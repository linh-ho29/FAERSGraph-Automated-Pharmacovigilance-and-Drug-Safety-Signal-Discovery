-- Append-only history of every (safetyreportid, safetyreportversion) ever ingested.
-- Maps cleanly onto a future Neo4j (:SafetyReport {id, version}) node + version-chain edges.
CREATE TABLE IF NOT EXISTS report_version (
    safetyreportid      TEXT NOT NULL,
    safetyreportversion TEXT NOT NULL,
    batch_id            TEXT NOT NULL,
    raw_file_path       TEXT NOT NULL,
    line_offset         INTEGER NOT NULL,
    retrieved_at        TEXT NOT NULL,
    drug_class_hint     TEXT,
    first_observed_at   TEXT NOT NULL,
    PRIMARY KEY (safetyreportid, safetyreportversion)
);

-- Derived pointer to the numerically-latest known version per report, kept separate from
-- report_version so "what's the latest version of X" is O(1) instead of a history scan.
CREATE TABLE IF NOT EXISTS report_latest (
    safetyreportid  TEXT PRIMARY KEY,
    latest_version  TEXT NOT NULL,
    latest_batch_id TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

-- Persisted daily request counter for the openFDA keyless quota (UTC-dated so it survives
-- process restarts and resumes correctly across day boundaries with no extra logic).
CREATE TABLE IF NOT EXISTS daily_quota (
    date          TEXT PRIMARY KEY,
    request_count INTEGER NOT NULL DEFAULT 0
);

-- One row per `ingest` CLI invocation, for operational visibility (lineage --status).
CREATE TABLE IF NOT EXISTS ingestion_run (
    batch_id     TEXT PRIMARY KEY,
    started_at   TEXT NOT NULL,
    finished_at  TEXT,
    drug_class   TEXT,
    search_query TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'running'
);
