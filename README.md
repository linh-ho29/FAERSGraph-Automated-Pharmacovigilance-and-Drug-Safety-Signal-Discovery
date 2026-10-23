# FAERSGraph

Automated pharmacovigilance and drug safety signal discovery over openFDA/FAERS adverse event
data, focused on four drug classes: **peptides**, **proteins**, **siRNA**, and **small
molecules**.

## Roadmap

1. **Ingest** openFDA Drug Adverse Event reports, focused on the four drug classes above. ✅ implemented
2. **Preserve** report versions and provenance. ✅ implemented
3. **Normalize** drug and reaction terminology. ✅ implemented
4. Compute standard pharmacovigilance disproportionality statistics (PRR, ROR, chi-square). 🚧 future phase
5. Represent reports/drugs/reactions/indications/outcomes in Neo4j. 🚧 future phase (see `docker-compose.yml`, not yet wired up)
6. Expose reproducible queries through a FastAPI service. 🚧 future phase
7. Add graph-based link prediction, only after the statistical baseline (#4) is validated. 🚧 future phase

This repo currently implements **phases 1-3 only**. Phases 4-7 are intentionally not designed or
implemented yet.

## Setup

```bash
brew install uv
uv python install 3.12
uv sync --extra dev
cp .env.example .env   # fill in FAERSGRAPH_OPENFDA_API_KEY if you have one; optional
```

## Running ingestion

```bash
uv run faersgraph ingest --drug-class sirna --max-pages 5
uv run faersgraph ingest --drug-class peptide --start-date 2024-01-01 --end-date 2024-03-31
```

Without an API key, openFDA allows **240 requests/minute and 1000 requests/day per IP**. The CLI
enforces both limits automatically:

- A per-minute sliding window throttles outgoing requests in-process.
- A SQLite-persisted daily counter (keyed by UTC date) survives process restarts, so repeated
  `ingest` invocations across a day correctly share the same quota, and the quota resets itself
  at UTC midnight with no extra bookkeeping.
- If the daily cap is hit, the command exits with an error rather than sleeping until tomorrow --
  just re-run it (e.g. via cron/launchd) the next day, or supply `FAERSGRAPH_OPENFDA_API_KEY` in
  `.env` to raise the limits (no code changes required).

`--drug-class` narrows the openFDA `search=` query server-side to conserve the quota, but every
fetched report is still re-classified client-side (see **Drug classification taxonomy** below) --
the server-side narrowing is an optimization, not the source of truth.

## Running normalization

```bash
uv run faersgraph normalize --out data/processed/normalized.jsonl
uv run faersgraph normalize --batch-id <batch-id>   # normalize just one ingestion run
```

Writes one `NormalizedReport` JSON object per line, combining RxNorm-normalized drug identities,
drug-class tags, surface-normalized reaction/indication terms, and outcome/seriousness enums.

## Inspecting lineage and provenance

```bash
uv run faersgraph lineage --status                    # remaining daily quota + recent runs
uv run faersgraph lineage --safetyreportid <id>        # full version history for one report
```

Every raw page fetched from openFDA is written once to `data/raw/<batch_id>/page_NNNNNN.jsonl`
(never overwritten) alongside a `.meta.json` provenance sidecar recording the exact `search=`
query, retrieval timestamp, and openFDA's own `meta` envelope (license/disclaimer/last_updated).
A SQLite ledger (`data/db/faersgraph.sqlite`) tracks every `(safetyreportid, safetyreportversion)`
ever seen, so re-running `ingest` is idempotent and amendments to existing reports (FAERS reports
are frequently revised) are tracked rather than silently overwritten.

## Drug classification taxonomy and its limits

No single openFDA field cleanly identifies peptide vs. protein vs. siRNA vs. small molecule.
`faersgraph.classification.drug_class.classify()` applies an ordered set of heuristics (exact
substance-name matches for the small, unambiguous siRNA class; `pharm_class_cs`/`pharm_class_epc`
keyword matches; USAN name-suffix stems; a weak application-number tiebreak) and returns a
confidence level and the specific rule that matched, not just a label. The seed dictionaries live
in `faersgraph.classification.seed_data` and are deliberately short and high-precision --
extend them as new drugs are identified, but verify each addition against a real FAERS record
first. `UNKNOWN` is reserved for entries with no identifying fields at all; everything else that
doesn't match a biologic/siRNA signal defaults to `SMALL_MOLECULE` (the large majority of drugs).

## MedDRA hierarchy limitation

openFDA exposes only the MedDRA **Preferred Term** string per reaction (`reactionmeddrapt`) -- it
does **not** expose the PT→HLT→HLGT→SOC hierarchy, which is licensed/proprietary and not
redistributable. Reaction (and indication) normalization in this MVP is therefore limited to
surface-form hygiene (trim/lowercase/whitespace-collapse, for stable deduplication), not hierarchy
mapping. `faersgraph.normalization.reaction_normalizer.MedDRAHierarchyProvider` is a `Protocol`
extension hook for users who have their own MedDRA license and want to plug in a real hierarchy
lookup later -- no implementation ships here, by design.

## Data model

- **Raw storage** (`data/raw/`): immutable JSONL pages exactly as returned by openFDA, plus a
  provenance sidecar per page.
- **Lineage ledger** (`data/db/faersgraph.sqlite`, table `report_version`/`report_latest`):
  append-only version history plus a derived "latest version" pointer per report, designed so a
  future Neo4j loader can map it directly onto `(:SafetyReport {id, version})` nodes and
  version-chain edges.
- **Normalized output** (`data/processed/normalized.jsonl`): one `NormalizedReport` per line
  (`faersgraph.models.normalized`), shaped so drugs/reactions map directly onto future graph
  nodes/edges without redesign.

## Testing

```bash
uv run pytest
uv run ruff check .
```

