# ADR-0007 — One writer per ledger; all writes atomic

**Status** Accepted · Phase 0

## Context

Within a heartbeat wave several agents run concurrently. Files are the database ([ADR-0001](0001-files-are-the-database.md)), so there is no transaction manager, no row locking and no isolation level. Two agents appending to the same JSONL can interleave a partial line; two agents rewriting the same JSON state file can lose one another's changes entirely; a process killed mid-write leaves a truncated file that fails to parse on the next read.

The brief already requires that exactly one agent own write access to any given ledger. That handles the logical conflict. It does not handle the physical one.

## Decision

**Logical — sole ownership.** Every ledger names exactly one writing agent, declared in charter part 3 and tabulated in `docs/agent-catalogue.md`. Everyone else reads. `/selftest` parses the charters and fails if any ledger has zero or two owners. Cross-domain updates are requests, not writes: `tax` needing a correction in `holdings` asks `investments` for it.

**Physical — atomic writes.** `tools/py/atomic.py` is the only sanctioned write path:

- **JSON state** — write to `<file>.tmp.<pid>`, `fsync`, `os.replace()` onto the target. `os.replace` is atomic on POSIX, so a reader sees either the old file or the new one, never a partial.
- **JSONL append** — open `O_APPEND`, one `write()` per record, record smaller than `PIPE_BUF`. Appends do not interleave.
- **Multi-file updates** — write all temps, then rename in a documented order, with the operation logged so a crash mid-sequence is detectable and recoverable.

**Exceptions, both deliberate.** `state/queue.json` is written by the **orchestrator alone**; agents return proposed work items which the orchestrator merges. `state/gaps.jsonl` and `state/audit.jsonl` are append-only with many writers, which is safe precisely because they are append-only.

## Consequences

- No reader ever sees a torn file, so no run fails on a parse error caused by a concurrent write.
- Merge conflicts become impossible by construction rather than by retry logic.
- Ownership is a checkable property, so a refactor that accidentally introduces a second writer fails the test suite rather than corrupting data months later.
- Cross-domain writes require a round-trip through the owning agent. This is a real cost in latency and a real gain in traceability: every change to a ledger has exactly one accountable author.
- Records larger than `PIPE_BUF` (4 KiB on macOS) need the temp-and-rename path. `atomic.py` selects the strategy by size rather than trusting the caller.
- The system does not attempt multi-file transactions. Where a logical change spans ledgers, it is applied in dependency order and made idempotent, so a partial application is completed rather than rolled back.

## Alternatives considered

**File locking (`flock`)** — works, but adds a failure mode (stale locks after a kill) and does not solve lost updates on read-modify-write. Atomic replace is simpler and stronger.

**Serialise all writes through the orchestrator** — safest, and a bottleneck that would erase the benefit of concurrent waves. Applied only to `queue.json`, where contention is genuine.

**SQLite for the write path** — real transactions, at the cost of the property that makes the vault legible. Rejected; see [ADR-0009](0009-no-sqlite-read-model.md).
