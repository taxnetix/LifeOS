# ADR-0003 — SENSE is a deterministic script, not an agent turn

**Status** Accepted · Phase 0

## Context

The brief promises that `/heartbeat` can run hourly, indefinitely, and that when nothing has changed it "costs almost nothing and says so". It also names the opposite failure explicitly: doing nothing because nothing *obviously* changed.

If SENSE is a reasoning step, every hourly run loads state, walks the vault, considers the calendar and concludes "nothing to do" — at full token cost, with non-deterministic thoroughness, forever. Twenty-four times a day, most of them concluding nothing. The promise of a cheap idle loop cannot be kept by an agent that has to think its way to idleness.

## Decision

SENSE is `tools/py/sense.py` — pure Python, no model call. It compares `state/cursors.json` against the filesystem and the SA fiscal calendar and emits a JSON change report on stdout.

```json
{ "run_id": "…", "now": {…}, "changes": [], "due": [], "quiet": true }
```

When `quiet` is true, the heartbeat agent writes one journal line, touches the cursor and stops — one turn, no delegation, no analysis.

Detection is exhaustive by enumeration rather than by judgment: `inbox.new`, `inbox.unreadable`, `cadence.due`, `ledger.stale`, `obligation.due`, `rule.expired`, `proposal.pending`, `question.open`, `gap.blocking`, `run.failed`, `variance.breach`, and the four `github.*` kinds. Adding a new signal kind means adding a detector and a test, not hoping the model notices.

## Consequences

- The idle path is milliseconds of Python plus a single short model turn. The hourly promise is affordable in practice, not just in principle.
- Change detection is deterministic, unit-testable, and identical on every run — no drift in what counts as a signal.
- "Nothing obviously changed" is no longer a judgment call: elapsed cadences and stale ledgers are signals whether or not anything visibly moved, which is precisely the failure mode the brief warns about.
- Signal coverage becomes a testable property. A detector that does not exist is a visible gap in a table, not an invisible omission in a prompt.
- The cost is that a genuinely novel signal type needs code. That is the right trade: novel signal types are rare, and silently missing them is expensive.
- Judgment moves to where it belongs — TRIAGE and PLAN decide what *matters*; SENSE only reports what *changed*.

## Alternatives considered

**Agent-driven SENSE** — maximally flexible, but expensive per run, non-deterministic in coverage, and unable to keep the cheap-idle promise. Rejected.

**Hybrid: script first, agent only on ambiguity** — attractive, and effectively what happens, since TRIAGE is an agent step operating on the script's output. Adding a second model call *inside* SENSE would reintroduce the cost on exactly the idle path we are protecting.

**Filesystem watcher** — catches new files instantly but cannot see elapsed cadences, expiring obligations or stale rules, which are most of the signals that matter. Complementary at best; insufficient alone.
