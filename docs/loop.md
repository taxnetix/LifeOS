# LifeOS — The Perpetual Loop

> Status: Phase 0 (design). Nothing here is implemented yet.
> The design goal: **the same command, run repeatedly forever, always advances the system correctly — including when nothing has changed, in which case it costs almost nothing and says so.**

## 1. Two failure modes

Everything in this design exists to prevent one of two failures:

| Failure | Prevented by |
|---|---|
| **Doing nothing** because nothing obviously changed | Cadence triggers fire on elapsed time, not just on new files. A quiet inbox is not an idle system — it is a system that should be checking a deadline, refreshing a quote, or reviewing an open loop. |
| **Redoing work** already done | Deterministic record IDs make re-ingestion a byte-identical no-op; cursors mark what has been consumed; the queue carries dependencies so nothing runs twice in a wave. |

The cursor + queue + journal triad is the mechanism. `state/cursors.json` says *how far we got*. `state/queue.json` says *what is outstanding*. `journal/` says *why*, in prose, for the human.

## 2. Orientation: `/boot`

Run at the start of a working session. Read-only, cheap, no side effects beyond a journal line.

```
read  profile/profile.yaml            who you are, entities, preferences, enabled domains
read  state/cursors.json              where we got to
read  state/queue.json                what is outstanding
read  state/gaps.jsonl                what we know we don't know
read  memory/short/ + memory/medium/  what we were in the middle of
compute calendar position             SA fiscal calendar: what's near
report ≤ 1 page                       where you stand, what's next, what I need from you
```

`/boot` never mutates ledgers. If it finds the system in a broken state — a failed prior run, a corrupt cursor — it says so and proposes a repair rather than performing one.

## 3. The loop: `/heartbeat`

Seven stages. Idempotent. Safe to run hourly forever.

```
1. SENSE      detect change since last cursor
2. TRIAGE     convert every signal into a costed work item
3. PLAN       select the next coherent batch
4. DISPATCH   delegate to owning agents, in waves
5. INTEGRATE  collect, write, resolve cross-domain implications
6. REFLECT    journal: what changed, what it means, what's next, what I need from you
7. COMMIT     advance cursors; leave the system resumable
```

### 3.1 SENSE — deterministic, not conversational

**SENSE is a Python script, not an agent turn.** `tools/py/sense.py` reads `state/cursors.json`, walks the vault, consults the fiscal calendar, and emits a change report on stdout:

```json
{
  "run_id": "run_20260815T0914Z_7f3a",
  "now": { "utc": "2026-08-15T07:14:22Z", "local": "2026-08-15T09:14:22+02:00" },
  "changes": [
    { "kind": "inbox.new",        "path": "inbox/absa-jul-2026.pdf", "sha256": "41ab…" },
    { "kind": "ledger.stale",     "ledger": "holdings", "age_days": 97, "threshold": 90 },
    { "kind": "proposal.pending", "path": "proposed/2026-07-cancel-gym.md", "age_days": 12 },
    { "kind": "obligation.due",   "ref": "tax:provisional:IRP6-1", "due": "2026-08-31", "lead_days": 16 },
    { "kind": "run.failed",       "run_id": "run_20260814T0914Z_2b91", "agent": "finance" }
  ],
  "due": [
    { "cadence": "daily",   "last": "2026-08-14T18:00:00Z", "overdue_by": "PT3H" }
  ],
  "quiet": false
}
```

Signal kinds SENSE detects, all by comparing state against the clock and the filesystem:

| Kind | Meaning |
|---|---|
| `inbox.new` | a file in `inbox/` whose hash is not in `documents/index.jsonl` |
| `inbox.unreadable` | present but extraction previously failed |
| `cadence.due` | an elapsed cadence trigger (§4) |
| `ledger.stale` | a ledger older than its declared freshness threshold |
| `obligation.due` | a dated obligation inside its lead time |
| `rule.expired` | a cached rulebook past its `refresh_interval` |
| `proposal.pending` | an unanswered artefact in `proposed/` |
| `question.open` | an unanswered question in an agent state file |
| `gap.blocking` | a gap blocking a queued item |
| `run.failed` | a prior run that did not reach COMMIT |
| `variance.breach` | a threshold from `profile.yaml` crossed |
| `github.issue.open` | actionable **system** work in the GitHub mirror |
| `github.issue.needs_human` | a system issue blocked on your decision |
| `github.pr.review_requested` | a pull request waiting on you |
| `github.ci.failed` | a workflow run failed on the default branch |

The four `github.*` kinds come from `tools/py/gh_sync.py`, which refreshes `state/system/issues.jsonl` when the network is up and **degrades silently to the cached mirror when it is not** — setting `github.reachable: false` in the report. GitHub can never fail a heartbeat. These signals are system work, owned by `meta-architect`, and are deliberately capped below life work in priority: a failing CI run must not outrank a provisional tax deadline. See [github.md](github.md).

**The quiet path.** If `changes` is empty and `due` is empty, `quiet: true`. The agent writes one journal line, touches the cursor, and stops — one turn, no delegation, no analysis. This is what makes "costs almost nothing" true rather than aspirational: the system does not reason its way to *nothing changed*, it is told so by a script that ran in milliseconds ([ADR-0003](adr/0003-deterministic-sense.md)).

### 3.2 TRIAGE

Each signal becomes a work item in `state/queue.json`:

```json
{
  "id": "wi_20260815_0001",
  "signal": { "kind": "inbox.new", "path": "inbox/absa-jul-2026.pdf" },
  "domain": "finance",
  "owner": "librarian",
  "priority": 2,
  "cost_estimate": "medium",
  "depends_on": [],
  "blocks": ["wi_20260815_0004"],
  "state": "queued",
  "attempts": 0,
  "created_run": "run_20260815T0914Z_7f3a"
}
```

Priority is derived, not invented — deadline proximity, financial magnitude, whether it blocks something else, and whether it answers an open question from you. Items already present and unresolved are updated, not duplicated: work-item identity is `hash(signal)`, so the same unanswered proposal on twenty consecutive heartbeats is one item with an age, not twenty items.

Deduplication against `attempts` and a `max_attempts` ceiling is what stops a permanently-failing item from consuming every heartbeat forever. On exhaustion the item moves to `state: "parked"` with a gap record explaining why, and only a human or a changed input revives it.

### 3.3 PLAN

Select the next coherent batch, subject to:

- **Dependencies** — nothing runs before what it depends on.
- **Budget** — `profile.yaml` sets `heartbeat.max_items` and `heartbeat.max_waves`. A heartbeat is allowed to leave work queued; that is normal, not failure.
- **Coherence** — *one domain deep beats five domains shallow.* Prefer a batch that completes a domain's story over a batch that touches everything and finishes nothing.
- **Human-blocking first** — anything waiting on you gets surfaced this run, even if the work itself cannot proceed.

### 3.4 DISPATCH

The orchestrator spawns the owning agent for each selected item. Agents run concurrently within a wave and return a structured result:

```json
{
  "work_item": "wi_20260815_0001",
  "status": "done",
  "ledgers_written": ["transactions", "accounts"],
  "records": { "written": 214, "superseded": 0, "unchanged": 1180 },
  "gaps": [ { "kind": "field.unreadable", "detail": "page 4 balance smudged in scan" } ],
  "questions": [ "Is 'JHB PROPS CC' the Sandton rental? It is uncategorised." ],
  "proposals": ["proposed/2026-08-duplicate-subscriptions.md"],
  "dispatch_requests": [ { "agent": "analyst", "task": "recompute cashflow trend" } ],
  "self_review": {
    "learned": "ABSA changed column order in July 2026 statements",
    "missing": "June statement never arrived",
    "next_time": "add a fingerprint for the new ABSA layout"
  }
}
```

`dispatch_requests` is how the fractal survives without runtime recursion: a domain agent that needs a specialist asks for it, and the orchestrator runs it in the next wave, up to `max_waves`. See [ADR-0002](adr/0002-fractal-definition-flat-runtime.md).

### 3.5 INTEGRATE

Where the holistic claim actually gets paid off. The orchestrator collects every result and:

1. Confirms ledger writes landed and validate against schema.
2. Merges returned gaps into `state/gaps.jsonl` and questions into the pending-questions register.
3. **Resolves cross-domain implications** — the step no single domain agent could take:
   - a new life policy → does it change estate liquidity? does it duplicate group cover?
   - a salary change → RA contribution headroom, provisional tax estimate, budget baseline
   - a new bond → net worth, estate duty, short-term insurance adequacy
   - a trust distribution → personal taxable income, `s7C` exposure, conduit attribution
4. Queues the follow-up work those implications generate for the *next* heartbeat, so INTEGRATE stays bounded.

The cross-domain rules live in `.claude/rules/za/cross-domain.yaml` as declared triggers, so they are inspectable and testable rather than emergent.

### 3.6 REFLECT

Append to `journal/<YYYY-MM-DD>.md`:

- **What changed** — facts, with counts and links to records.
- **What it means** — interpretation, explicitly labelled as such.
- **What's next** — queue depth and the top few items.
- **What I need from you** — the human-gated list: pending proposals, open questions, missing documents, drafted issues awaiting `/issues push`, and PRs awaiting review. If this section is empty, say so.

Length obeys `profile.yaml → communication.report_length`. A quiet heartbeat writes one line, not a page.

### 3.7 COMMIT

Advance `state/cursors.json`, write the run record to `state/run-log.jsonl`, and leave the system resumable. A run that dies before COMMIT leaves its cursor unadvanced, so the next SENSE emits `run.failed` and the work is retried rather than lost.

Cursors are per-stream, not global:

```json
{
  "inbox":     { "last_scanned": "2026-08-15T07:14:22Z", "last_hash_seen": "41ab…" },
  "cadence":   { "hourly": "…", "daily": "…", "weekly": "…", "monthly": "…",
                 "quarterly": "…", "annual": "…" },
  "ledgers":   { "transactions": { "last_written": "…", "records": 12841 } },
  "rules":     { "za/sars-tables": { "as_at": "2026-03-01", "verified": "2026-07-02" } }
}
```

## 4. Cadence triggers

Driven by comparing `state/cursors.json` against the clock and the **South African fiscal calendar**. Every cadence is overridable per-user in `profile.yaml`.

| Cadence | When | Does |
|---|---|---|
| **hourly** | heartbeat | inbox sweep, cheap change detection |
| **daily** | evening | memory consolidation, journal roll-up, tomorrow's brief |
| **weekly** | Sunday | cashflow check, budget variance, open-loop review, document gaps |
| **monthly** | 1st | statement ingestion cycle, dashboard refresh, debit-order audit, net worth snapshot |
| **quarterly** | Mar/Jun/Sep/Dec | deep domain review, insurance & medical aid adequacy, allocation drift, provisional tax posture, quote-refresh sweep |
| **annual** | see below | tax year-end pack, RA optimisation, TFSA check, will & beneficiary review, renewal calendar, Reg 28, estate liquidity |
| **event-driven** | on trigger | unseen document type, `/life-event`, variance breach, deadline within lead time |

### 4.1 SA fiscal anchors

Hard-coded into `tools/py/calendar_za.py`, each with a lead time so work starts before the date, not on it:

| Date | Event | Lead |
|---|---|---|
| 28/29 Feb | Personal tax year end — RA top-up, TFSA limit, CGT harvesting | 60 days |
| 31 Aug | Provisional tax IRP6 period 1 | 30 days |
| 28/29 Feb | Provisional tax IRP6 period 2 | 30 days |
| Jul–Oct | Personal income tax filing season | 30 days |
| Company year end + 12 months | Company ITR14 | 60 days |
| Trust year end (28/29 Feb) | IT12TR, annual financial statements, beneficial-ownership filing | 90 days |
| Monthly, 7th | PAYE/UIF/SDL (EMP201) | 5 days |
| Bi-monthly, 25th | VAT (VAT201) | 7 days |
| Oct–Nov | Medical aid option-change window | 30 days |
| Policy anniversary | Short-term insurance renewal, quote refresh | 45 days |

Annual limits that the tax and investment agents check against, each carried in `.claude/rules/za/` with an explicit "as at" date and refresh interval rather than hard-coded here: the retirement-contribution deduction cap, TFSA annual and lifetime limits, CGT annual exclusion, estate duty abatement and rates, and donations tax thresholds. A rule past its refresh interval must be re-verified before it is relied on, and the output says when it was last verified.

## 5. Idempotency

The acceptance test is mechanical:

```
1. reset vault.example/ to a known state
2. /heartbeat            → does work, writes ledgers, journals it
3. /heartbeat            → SENSE reports quiet: true
4. assert: no ledger diff between runs 2 and 3
5. assert: run 3 wrote exactly one journal line
6. assert: run 3 spawned zero subagents
```

Three independent mechanisms make this hold, and the design deliberately does not rely on any one of them alone:

1. **Deterministic IDs** — re-processing the same document produces identical records, so the append is detected as a duplicate and skipped.
2. **Cursors** — consumed inputs are not re-consumed.
3. **Work-item identity** — `hash(signal)` collapses repeated signals into one ageing item.

## 6. Nightly ritual: `/consolidate`

Runs after the day's last heartbeat.

```
1. read journal/<today>.md, agent state files, proposals, decisions
2. extract durable facts        → promote to memory/long/
3. age medium-term items        → demote or expire past horizon
4. deduplicate                  → merge near-identical statements
5. detect contradictions        → SURFACE, never silently overwrite
6. compress                     → verbose notes into crisp statements
7. audit                        → one line per promotion/demotion/expiry to memory/audit.jsonl
8. regenerate CLAUDE.md memory block between the delimiters
9. write tomorrow's brief       → memory/short/brief-<tomorrow>.md
```

Contradiction handling is the part that matters. If long-term memory says *"prefers no lock-in contracts"* and today's decision was a 24-month fibre contract, `/consolidate` does not overwrite the preference and does not discard the fact. It writes both, flags the conflict, and asks — because the resolution might be "the preference was wrong" or might be "this was an exception", and only you know which.
