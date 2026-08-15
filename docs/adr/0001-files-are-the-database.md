# ADR-0001 — Files are the database

**Status** Accepted · Phase 0

## Context

LifeOS must be inspectable, portable, diffable and repairable by hand, decades from now, by someone who is not a programmer — a spouse, an executor, an attorney. It must also survive the disappearance of any particular tool, including Claude Code itself. A database process is a dependency, a migration burden and an opaque box; none of those are acceptable for a system whose whole purpose is to be *legible when it matters most*.

## Decision

Plain files on disk are the only source of truth.

| Format | Role | Mutability |
|---|---|---|
| Markdown | narrative, reports, memory, journal | human-editable |
| YAML | profile, config, budgets | human-editable |
| JSONL | ledgers, events, audit | append-only |
| JSON | state, indices, cursors | rewritten atomically |
| CSV / HTML | exports, dashboards | derived, disposable |

Every derived artefact must be reproducible from source documents plus config. Deleting every report and every ledger and re-running the pipeline must yield byte-identical output.

## Consequences

- Any editor, any `grep`, any `git diff` works. No client, no driver, no schema migration tool at runtime.
- Ledger scans are O(n) — acceptable at personal scale (a decade of transactions is single-digit MB), and revisited only if measurement says otherwise.
- Concurrent writes need explicit discipline, addressed in [ADR-0007](0007-single-writer-atomic-writes.md).
- Referential integrity is not enforced by a database, so it is enforced by schema validation at write time and by `/audit` afterwards.
- The vault survives LifeOS. If the system is abandoned, the files remain a usable Life File.

## Alternatives considered

**SQLite as source of truth** — fast and transactional, but opaque to a non-technical reader, awkward to diff, and a hard dependency for anyone inheriting the vault. Rejected on legibility.

**A document store or a graph database** — a graph database in particular fits the relationship model well, but it is a running process and a much larger dependency than the problem justifies at one-family scale.

**JSON per record as individual files** — maximally diffable, but produces tens of thousands of tiny files and makes append-only history awkward. JSONL gets most of the benefit with none of that.
