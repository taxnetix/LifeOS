---
description: The nightly memory ritual — promote, expire, deduplicate, surface contradictions.
argument-hint: "[--dry-run]"
allowed-tools: Bash, Read, Write, Grep, Glob, Task
---

# /consolidate $ARGUMENTS

!`.venv/bin/python -m lifeos.memory --consolidate --dry-run`

Show the dry run, then apply. Delegate to `memory-keeper` for the judgment: which facts are durable, which are transient, and which are duplicates saying the same thing twice.

## The two rules that matter

**Contradictions are surfaced, never resolved.** If long-term memory says *"rejects anything with a lock-in period"* and today's decision was a 24-month contract, write both, flag the conflict, and ask. The resolution might be "the preference was wrong" or "this was a deliberate exception", and only the user knows which. Silently picking one is how a memory system becomes untrustworthy — and an untrustworthy memory is worse than none, because it is consulted with confidence.

**Hand edits outrank the horizon.** These files are meant to be edited. A file marked `hand_edited` is preserved even when stale. A consolidation that mangles a human's edit is a **failed run**, and should be reported as one.

## What it does

1. Promote durable facts to `long/` — preferences, risk appetite, standing instructions, decisions with rationale, observed patterns.
2. Age `short/` past 7 days and `medium/` past 90 — demote, never delete.
3. Deduplicate near-identical statements.
4. Flag contradictions.
5. Compress verbosity. Long-term memory earns its place by being short.
6. Audit every change to `memory/audit.jsonl`.
7. Regenerate the `CLAUDE.md` block **between the delimiters only** — everything outside is the user's constitution, and a memory ritual that edited it would be rewriting its own instructions.
8. Write tomorrow's brief.

## Rules

- Memory is not a ledger. A fact with a source document belongs in a ledger.
- Never write outside the `LIFEOS:MEMORY` delimiters.
- Report contradictions to the user in the summary; do not bury them in a file.
