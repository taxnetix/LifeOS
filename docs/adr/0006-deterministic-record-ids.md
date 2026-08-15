# ADR-0006 — Deterministic record IDs give idempotency

**Status** Accepted · Phase 0

## Context

The brief names "redoing work already done" as one of two failure modes to design against explicitly, and requires that `/heartbeat` be idempotent and safe to run hourly forever.

The natural approach — track what has been processed in a cursor — breaks in ordinary situations: the same statement arrives twice under different filenames; a document is re-filed after a correction; a parser is improved and the file is re-processed deliberately; a run dies after writing half a ledger. In each case a cursor either loses data or duplicates it. Detecting duplicates by comparing field values is fuzzy and gets slower as the ledger grows.

## Decision

Every ledger record's identity is derived from its origin, not assigned at write time:

```
id = "sha256:" + sha256( source.doc_hash + "|" + source.locator + "|" + natural_key )
```

- `source.doc_hash` — SHA-256 of the filed original.
- `source.locator` — the exact position within it: `page=3;row=17`, `sheet=Summary;cell=B14`.
- `natural_key` — the ledger's own identity fields (for a transaction: account ref, posting date, amount, raw description).

Writing is therefore an upsert-by-identity: a record whose `id` already exists is a no-op. Re-ingesting the same statement produces byte-identical records and writes nothing.

Corrections never mutate. A superseding record is appended and a tombstone sets `superseded_by` on the original, so history remains complete.

## Consequences

- Idempotency is a property of the data model rather than a behaviour the agent must remember. This is the strongest of the three mechanisms; cursors and work-item identity are the other two, and the design deliberately does not rely on any one alone.
- Duplicate detection is an exact hash lookup, not a fuzzy comparison.
- A half-written ledger from a crashed run self-heals: the re-run rewrites the records it already wrote as no-ops and continues.
- Provenance is not an add-on — the ID *is* the provenance, so a record without traceable origin cannot exist.
- Re-processing with an improved parser produces new IDs when the locator or natural key changes, which is correct: the old records are superseded rather than silently overwritten, and the change is visible.
- The cost is that `doc_hash` must be stable, so `documents/` originals are strictly immutable. That is a rule the system wanted anyway.
- Records with no document source — a human-entered fact, an inference — use `doc_hash: "human"` or `"inferred"` plus a stable natural key, and are rendered differently in reports.

## Alternatives considered

**UUIDs assigned at write** — trivially duplicates on re-ingestion. Rejected.

**Cursor-only tracking** — fails on renamed files, deliberate re-processing and crash recovery. Kept as a complementary mechanism, not the primary one.

**Content hash of the whole record** — nearly equivalent, but changes whenever any field is enriched, which would break identity every time a transaction is categorised. Anchoring on origin plus natural key keeps identity stable across enrichment.
