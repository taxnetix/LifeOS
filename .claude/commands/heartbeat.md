---
description: Run one pass of the LifeOS loop. Idempotent. Safe to run hourly forever.
argument-hint: "[--dry-run] [--max-items N]"
allowed-tools: Bash, Read, Write, Edit, Grep, Glob, Task
---

# /heartbeat $ARGUMENTS

Run **one** full pass of the loop, then stop. See `docs/loop.md`.

## Step 1 — SENSE

!`.venv/bin/python -m lifeos.sense`

## Step 2 — decide, from that output alone

**If `uninitialised` is true** → tell the user to run `/lifeos-init`. Stop.

**If `quiet` is true** →
1. Append exactly one line to `$VAULT/journal/<today>.md`:
   `HH:MM — heartbeat <run_id>: nothing to do.`
2. Update the `hourly` cadence cursor in `$VAULT/state/cursors.json`.
3. Append one record to `$VAULT/state/run-log.jsonl` with `"quiet": true, "outcome": "committed"`.
4. Tell the user, in **one sentence**, that there was nothing to do.

**Do not** spawn an agent. **Do not** summarise what you considered. **Do not** explain why there was nothing to do. One line in the journal, one sentence to the user. This cheap idle path is the whole reason `/heartbeat` can run hourly forever, and narrating around it defeats it.

**Otherwise** → delegate the full loop to the `orchestrator` agent via Task, passing the sense report verbatim. Let it run TRIAGE → PLAN → DISPATCH → INTEGRATE → REFLECT → COMMIT.

## Step 3 — report back

Obey `profile.communication.report_length` (default **short**):

- what changed
- what it means
- what's next
- **what I need from you** — proposals, open questions, missing documents, unfiled issue drafts, PRs awaiting review. If empty, say so in one line.

## Non-negotiable

- Never send, submit, transact, publish, or delete an original. Draft to `$VAULT/proposed/` and wait.
- **If the run cannot complete, do not advance cursors.** The next SENSE emits `run.failed` and the work retries. A partial run reported honestly beats a clean-looking lie.
- A second consecutive run on unchanged inputs must produce no ledger diff.
