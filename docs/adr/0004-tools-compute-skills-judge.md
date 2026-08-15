# ADR-0004 — Tools compute, skills judge

**Status** Accepted · Phase 0

## Context

The brief specifies seven pipeline stages — INGEST, EXTRACT, NORMALISE, ENRICH, ANALYSE, VISUALISE, RECOMMEND — and says to "implement as skills so any agent can invoke them, with a standard stage contract and resumability".

This does not match what a Claude Code skill is. A skill is a bundle of instructions surfaced to the model when its description matches the situation; it is model-selected context, not a callable function with a signature, a return value and an exit code. A pipeline stage that must parse a 40-page PDF into 200 exact transaction records, deterministically, every time, cannot be a probabilistic context injection. Building the flagship money pipeline that way would produce a system that mostly works, which for financial records is worse than one that visibly fails.

## Decision

Split by nature of the work.

**`tools/` — determinism.** Every pipeline stage is a leaf script with a strict JSON in/out contract, an exit code, and unit tests. `tools/py/parse_statement.py --bank absa --in <pdf>` emits records or fails loudly. Same input, same output, always.

**`.claude/skills/` — judgment.** Skills describe *when* to reach for a tool, *which* variant applies, what a low-confidence result means, when to escalate to `proposed/` instead of writing, and how to interpret what comes back. The `statement-ingestion` skill knows that an unrecognised layout means "open an adapter issue and route to `proposed/`", not "guess".

Resumability comes from stage outputs being written to disk and keyed by content hash, so a re-run skips completed stages — a property of the file layout, not of the skill mechanism.

## Consequences

- Numbers in ledgers come from code that can be tested, profiled and debugged. A parsing bug is reproducible.
- Model judgment is applied where judgment is actually required: classification, categorisation ambiguity, conflict resolution, recommendation.
- Skills stay small and readable, because they carry procedure rather than implementation.
- The boundary is auditable: `source.method` on every record names the tool and version that produced it, so it is always clear whether a figure was computed or inferred.
- The cost is two artefacts per capability — a tool and a skill. Worth it; they change at different rates and for different reasons.
- No agent is obliged to run all seven stages. Most domains use only the first three.

## Alternatives considered

**Everything as skills, per the brief's wording** — no deterministic guarantee on financial extraction. Rejected on correctness.

**Everything as tools, no skills** — the judgment calls (is this a duplicate? is this categorisation safe? should this be escalated?) get hard-coded into brittle heuristics, or disappear. Rejected.

**Tools as MCP servers** — a cleaner calling convention, but adds a running process and a transport to a system whose central constraint is that it is just files and scripts. Revisit only if the number of tools makes direct invocation unwieldy.
