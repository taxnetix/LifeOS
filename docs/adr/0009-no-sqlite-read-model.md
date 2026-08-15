# ADR-0009 — No SQLite read-model

**Status** Accepted · Phase 0

## Context

The brief permits SQLite as a derived read-model, rebuildable from the JSONL ledgers, never a source of truth. The motivation would be query performance and ad-hoc analysis over transactions.

The realistic data volume argues against it. A decade of a household's transactions across several accounts is on the order of 10⁵ records and single-digit megabytes. `pandas` reads that from JSONL in well under a second. Meanwhile a cache that exists must be invalidated, rebuilt, versioned, tested and kept honest, and every reader must decide whether to trust it — which is the expensive part, and it is paid whether or not the cache is ever needed.

## Decision

No SQLite read-model is built in phases 0–7. Analysis reads JSONL directly via `pandas` in `tools/py/analyse/`.

The rebuild contract stays documented so the option remains open: any read-model must be reconstructible in full from `ledgers/*.jsonl` plus config by running a single pipeline, must never be read when its source is newer, and must never be a write target.

**Revisit when** a measured analysis run exceeds ~2 seconds on real data, or a genuine ad-hoc SQL need appears that `pandas` serves badly. Both are measurements, not guesses.

## Consequences

- One less artefact to keep consistent, and one less question — "is the cache stale?" — that every reader would otherwise have to answer.
- Analysis code reads the same files a human reads, so a discrepancy between a report and the ledger is directly inspectable.
- `sqlite3` is present on the machine, so adopting it later costs nothing in setup.
- If a ledger ever does grow beyond comfortable full scans, the first response is a materialised summary in JSON — `networth-snapshots.jsonl` is already exactly that — before reaching for a database.
- The cost is that a genuinely complex ad-hoc query is more awkward in `pandas` than in SQL. Acceptable, and reversible.

## Alternatives considered

**Build it now, per the brief's permission** — speculative optimisation against a load that has not been measured and probably will not arrive. Rejected as YAGNI.

**DuckDB over the JSONL directly** — attractive, since it queries files in place with no cache to invalidate, and it would be the first thing to try if the revisit trigger fires. Not adopted now because it is a dependency serving no present need.
