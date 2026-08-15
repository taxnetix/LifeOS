# ADR-0012 — Schema versioning and migration

**Status** Accepted · Phase 0

## Context

Ledgers are append-only and intended to last decades. Schemas will change: a field is added when a new document type reveals it, a field is split when one value turns out to be two, an enum gains a member. Meanwhile records written years earlier must remain readable, and `/audit` must still be able to trace a 2026 figure in 2036.

Without an explicit version on each record, a reader has to infer the shape from the fields present. That works until two changes overlap, and then it silently misreads old data.

## Decision

**Every record carries `"schema": "<ledger>/<major>"`** — for example `"transaction/1"`. The version is on the record, not on the file, because a JSONL ledger accumulates records written across many versions and must stay readable as a whole.

**Major version only.** A change that old readers can safely ignore — adding an optional field — does not bump. A change that would make an old reader wrong — removing a field, changing a type, changing the meaning of a value, changing the `id` derivation — bumps the major version.

**A bump requires three things:**
1. An ADR recording what changed and why.
2. A migration step in `tools/py/migrate.py`, which reads old-version records and emits new-version ones, appending supersessions rather than rewriting history.
3. A test fixture in `vault.example/` containing at least one record at each supported version, so backward compatibility is proven rather than assumed.

**Readers accept any version they have a handler for** and fail loudly on one they do not, rather than guessing. Schema files live in `templates/schemas/` as JSON Schema 2020-12, with historical versions retained.

## Consequences

- A record written in Phase 3 is still readable, and still auditable, after later schema evolution.
- Migration is explicit, reviewable and testable, and — because it appends supersessions rather than rewriting — the original records survive, so a bad migration is recoverable.
- The append-only discipline extends to schemas: a schema file is superseded, never edited to mean something new.
- The cost is ceremony on every breaking change. That is the point; breaking changes to financial records should be uncomfortable.
- Migrations are idempotent by construction, since supersession is keyed on deterministic IDs ([ADR-0006](0006-deterministic-record-ids.md)).
- Minor additive changes stay cheap, which keeps the discipline from being routed around.

## Alternatives considered

**Version the file, not the record** — simpler, but wrong for append-only ledgers, which by nature contain mixed-version records.

**Semantic versioning with minor and patch** — more precision than the decision actually needs; the only question a reader has is "can I read this?", which is a major-version question.

**Migrate the whole ledger in place on bump** — faster to read afterwards, but rewrites history and makes a bad migration unrecoverable. Rejected on the same grounds as mutable records.
