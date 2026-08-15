# LifeOS — Architecture

> Status: Phase 0 (design). Nothing in this document is implemented yet.
> Companion documents: [loop.md](loop.md) · [agent-catalogue.md](agent-catalogue.md) · [coverage-map.md](coverage-map.md) · [data-dictionary.md](data-dictionary.md) · [commands.md](commands.md) · [github.md](github.md) · [adr/](adr/)

## 1. What this is

LifeOS is a personal life-management system with **no server, no database and no application**. The repository is the product; Claude Code is the runtime; files on disk are the state.

A session is a turn of a perpetual loop. Every turn, the system senses what changed, decides what matters, delegates to the agent that owns that slice of life, integrates the results across domains, writes down what it learned, and advances its cursors so the next turn resumes cleanly. Run it hourly for a decade and it should always do the right next thing — including, most of the time, almost nothing.

The primary user is a South African engineer/CTO with personal finances, business interests, a PhD and a family. The secondary user is a colleague who cares mainly about trust administration. Both are served from one codebase via `packs/` and `profile.yaml`.

## 2. The two halves

```
life-os/            SYSTEM   shareable, MIT, zero personal data, git-tracked
vault/              VAULT    real life, git-ignored, never committed, never leaves disk
```

This separation is the single most important structural decision in the system ([ADR-0008](adr/0008-vault-location-and-separation.md)). Every other rule depends on it holding.

### 2.1 System repo

```
life-os/
├── CLAUDE.md                    constitution + router + machine-maintained memory block
├── README.md  SECURITY.md  LICENSE
├── requirements.txt  package.json
├── .claude/
│   ├── settings.json            hooks, permissions, env
│   ├── agents/                  17 agent charters
│   ├── commands/                20 slash commands
│   ├── skills/                  procedural skills — when and how to call tools
│   ├── hooks/                   session-start, pii-guard, vault-audit, pre-commit
│   └── rules/za/                SARS tables, Reg 28, estate duty — each with "as at" + refresh interval
├── templates/
│   ├── AGENT_CHARTER.md         the fractal unit
│   ├── schemas/                 JSON Schema: envelope, ledgers, state, memory
│   └── vault/                   blank vault skeleton used by /lifeos-init
├── packs/                       trusts · sme-owner · expat · phd-researcher · landlord
├── tools/
│   ├── py/                      .venv — extract, parse, normalise, analyse, tax, sense
│   ├── js/                      node_modules — render-dashboard, validate-schema
│   └── scheduler/               headless heartbeat wrapper + launchd template
├── docs/                        this directory
└── vault.example/               fully-populated FAKE vault — every test runs against this
```

### 2.2 Vault

```
vault/
├── profile/       profile.yaml — persons, entities, jurisdiction, preferences, consent, cadences
├── inbox/         you drop documents here. The only thing you do manually.
├── documents/     filed originals, content-addressed, immutable
├── ledgers/       normalised JSONL — the structured truth
├── state/         cursors, queue, run log, per-agent state, gaps register
├── memory/        short/ medium/ long/
├── reports/       generated dashboards, reviews, optimisation reports
├── proposed/      drafts awaiting your approval
└── journal/       daily narrative of everything the system did and why
```

### 2.3 Path resolution

One resolver, two implementations, no hardcoded paths anywhere:

```
$LIFEOS_VAULT  →  ./vault/  (default)
```

`tools/py/vault.py` and `tools/js/vault.mjs` are the only code permitted to compute the vault root. Agents and skills refer to vault locations as `$VAULT/ledgers/transactions.jsonl` and resolve through a tool. A grep for absolute paths under `/Users` in the system repo must return nothing — enforced by `/selftest`.

**Note on the current choice.** The vault sits inside the repo, excluded by `.gitignore`. That is a convenience, not a guarantee: `git add -f`, an edited `.gitignore`, or `git stash -u` would each defeat it, and git history cannot be un-rung. The pre-commit hook is therefore a hard, non-bypassable second line of defence, not a nicety. Moving the vault outside the repo later is a one-line `$LIFEOS_VAULT` change, but it must happen before the first real document lands.

## 3. The fractal unit

Every agent — orchestrator, domain, specialist — is defined by the same seven-part charter, generated from `templates/AGENT_CHARTER.md`:

1. **Identity & scope** — what slice it owns, and explicitly what it does not.
2. **Inputs** — document types, ledgers, rulebooks, upstream agent outputs.
3. **Outputs** — ledgers it may write, reports, proposals. *Exactly one agent owns write access to any ledger.*
4. **State file** — `state/agents/<name>.json`.
5. **Cadence & triggers** — when it wakes; what wakes it early.
6. **Sub-agents** — its specialists, if it has earned any.
7. **Definition of done & self-review** — how it knows the run succeeded, and the three closing questions: *what do I now know that I didn't; what is still missing; what would make me more useful next time?* The answers become work items and memory candidates.

The orchestrator's relationship to a domain agent is structurally identical to a domain agent's relationship to its specialists. That is the fractal property, and it is what makes `/add-domain` work.

### 3.1 Fractal in definition, flat at runtime

The charter recurses. **Execution does not.** Building a load-bearing loop on nested subagent dispatch is not safe, so LifeOS flattens recursion into waves ([ADR-0002](adr/0002-fractal-definition-flat-runtime.md)):

```
wave 1   orchestrator → finance, insurance, tax
         finance returns { result, dispatch_requests: [ "statement-parser:absa-cheque" ] }
wave 2   orchestrator → statement-parser:absa-cheque
         returns { result, dispatch_requests: [] }
wave 3   none requested → DISPATCH ends
```

Depth becomes waves rather than stack frames. Bounded by `max_waves` (default 4) in `settings.json`. The orchestrator remains the only component that spawns agents, which also makes cost and concurrency observable in one place.

### 3.2 Depth is earned

17 agents exist. The 175 leaves of the domain taxonomy do **not** each get an agent file — every agent description loads into the dispatch context, and dozens of them would degrade routing and inflate every session ([ADR-0010](adr/0010-lean-agent-tree.md)).

Instead a specialist starts life as a section of its domain agent's charter plus a skill. `meta-architect` watches `state/agents/<name>.json`; when a domain's run duration, error rate or open-loop count crosses a threshold, it *proposes* promoting one specialist into its own agent file. Coverage is guaranteed by [coverage-map.md](coverage-map.md) and audited by `/audit` — not by counting files.

## 4. Data model

### 4.1 Files are the database

| Format | Used for | Mutability |
|---|---|---|
| Markdown | narrative, reports, memory, journal | human-editable |
| YAML | profile, config, budgets | human-editable |
| JSONL | ledgers, events, audit | **append-only** |
| JSON | state, indices, cursors | rewritten atomically |
| CSV | tabular exports | derived, disposable |
| HTML | dashboards | derived, disposable |

SQLite is permitted by the brief as a derived read-model. It is **not being built** — JSONL plus pandas is sufficient at personal scale, and an unused cache is a liability ([ADR-0009](adr/0009-no-sqlite-read-model.md)). The rebuild-from-JSONL contract is documented so it can be added if a ledger ever outgrows the simple approach.

Every derived artefact must be reproducible from source documents plus config. `/audit` proves it; a round-trip test deletes a ledger, re-runs the pipeline and asserts byte-identical output.

### 4.2 The record envelope

Every ledger record, in every ledger, shares one envelope (`templates/schemas/envelope.schema.json`):

```json
{
  "id": "sha256:9f2c…",
  "schema": "transaction/1",
  "subject_id": "per_arne",
  "entity_id": "ent_personal",
  "source": {
    "doc_hash": "sha256:41ab…",
    "locator": "page=3;row=17",
    "method": "parser:absa-cheque/2",
    "confidence": 0.98,
    "extracted_at": "2026-08-15T09:14:22Z"
  },
  "valid_from": "2026-07-01",
  "valid_to": null,
  "superseded_by": null,
  "_meta": { "run_id": "run_20260815T0914Z_7f3a", "agent": "finance", "written_at": "…" }
}
```

Four properties fall out of this, and each of them is load-bearing:

- **Provenance.** `source.doc_hash` + `locator` means every number in every report walks back to a page of a real document. No invented figures, ever. A field the system inferred rather than read carries `method: "inferred"` and a confidence, and is rendered differently in reports.
- **Idempotency.** `id = sha256(doc_hash + locator + natural_key)`. Re-ingesting the same statement produces byte-identical records, so the write is a no-op. This — not cleverness in the agent — is the mechanism that prevents redone work ([ADR-0006](adr/0006-deterministic-record-ids.md)).
- **Append-only correction.** Records are never mutated. A correction appends a new record and sets `superseded_by` on the old one via a tombstone line. History is therefore complete and auditable.
- **Versioning.** `schema: "<name>/<n>"`. A bump requires an ADR and a `tools/py/migrate.py` step ([ADR-0012](adr/0012-schema-versioning.md)).

### 4.3 Money

Money is **never** a float:

```json
{ "cents": -125000, "currency": "ZAR" }
```

Integer minor units plus an ISO-4217 code, enforced by schema ([ADR-0005](adr/0005-money-as-integer-cents.md)). Cross-currency aggregation requires an explicit dated rate from `ledgers/fx-rates.jsonl` and is labelled with the rate and its date in every report.

### 4.4 Single writer

Exactly one agent owns write access to any ledger — declared in charter part 3 and tabulated in [agent-catalogue.md](agent-catalogue.md). Within a heartbeat wave, agents run concurrently, so:

- All writes go through `tools/py/atomic.py` (write temp → `fsync` → `rename`).
- JSONL appends use `O_APPEND` with a single `write()` per record.
- `state/queue.json` is written by the **orchestrator only**; agents return proposed work items and the orchestrator merges them.

[ADR-0007](adr/0007-single-writer-atomic-writes.md).

### 4.5 Unknown is a first-class answer

`state/gaps.jsonl` is the register of everything the system knows it does not know: a missing document, an unreadable field, an unanswered question, a contradiction it refuses to resolve silently. Gaps feed the work queue and the readiness score. "I don't know" is a valid, recorded, actionable output — never a guess.

## 5. Pipelines

Seven stages, each a leaf tool with a strict JSON in/out contract, each individually invocable and resumable. No agent is obliged to run all seven; most domains only ever use the first three.

| Stage | Does | Implemented by |
|---|---|---|
| `INGEST` | inbox sweep → type detect → OCR if needed → file immutably to `documents/<year>/<domain>/<hash>-<slug>.<ext>` | `tools/py/ingest.py` |
| `EXTRACT` | pdf/docx/xlsx/csv/md/txt/image → records + provenance per field | `tools/py/extract/` |
| `NORMALISE` | map to ledger schema, dedupe by record id, reconcile; conflicts → `proposed/`, never guessed | `tools/py/normalise.py` |
| `ENRICH` | categorise, classify, tag entities, link the relationship graph, look up public reference data | `tools/py/enrich/` |
| `ANALYSE` | aggregations, trends, variance, ratios, projections, gap analysis, scenarios | `tools/py/analyse/` |
| `VISUALISE` | self-contained HTML + markdown + CSV | `tools/js/render.mjs` |
| `RECOMMEND` | ranked, costed optimisations with rationale and evidence links | agent judgment + `analyse` output |

### 5.1 Tools compute, skills judge

This is the correction that makes the design executable ([ADR-0004](adr/0004-tools-compute-skills-judge.md)). Claude Code skills are model-selected context, not a callable API — a deterministic seven-stage pipeline cannot be built out of them.

So: **determinism lives in `tools/`, judgment lives in `.claude/skills/`.** `tools/py/parse_statement.py` deterministically turns an ABSA PDF into transaction records. The `statement-ingestion` skill tells the agent when to reach for it, which bank adapter applies, what a low-confidence result means, and when to escalate to `proposed/` instead of writing.

### 5.2 Bank statement adapters

SA bank PDF layouts differ substantially and change without notice. `tools/py/parsers/` is an adapter registry — FNB, Standard Bank, ABSA, Nedbank, Capitec, Investec, Discovery, TymeBank — selected by fingerprinting the document. When no adapter matches, or an adapter returns below its confidence floor, the fallback is explicit: LLM-assisted extraction, marked `method: "llm-extract"` with its confidence, written to `proposed/` for your confirmation. A parser never silently guesses a number into a ledger.

### 5.3 Flagship pipelines

Two, chosen because they prove the two central claims.

**Money, end to end** — monthly statements → categorised transactions → cashflow dashboard → budget variance → optimisation report (duplicate subscriptions, fee leakage, escalation creep, missed deductions, savings rate vs target). Handles multiple accounts across multiple banks and multiple entities, keeps personal and business separate, and still rolls up to one consolidated view. This proves the machinery works.

**Health cover, across domains** — medical aid plan + gap cover + employee benefits → one consolidated map showing what is covered, by whom, at what annual cost, with the overlaps and the holes named. This proves the holistic claim, because no single document contains the answer.

## 6. Memory

Three tiers, owned entirely by `memory-keeper`, all human-readable and hand-editable.

| Tier | Horizon | Holds |
|---|---|---|
| `memory/short/` | session + 7 days | current work, recent decisions, transient context, open questions |
| `memory/medium/` | ~90 days | active projects, in-flight optimisations, recent life events, pending deadlines, promises made |
| `memory/long/` | durable | preferences, risk appetite, standing instructions, decision history with rationale, structural life facts, observed patterns |

The nightly `/consolidate` ritual reviews the day's journal, agent state and proposals, then promotes durable facts, demotes and expires stale medium-term items, deduplicates, compresses verbosity, and **surfaces contradictions rather than silently overwriting**. Every promotion, demotion and expiry writes an audit line to `memory/audit.jsonl`, so memory is never a black box.

Long-term memory feeds forward into `CLAUDE.md` through an explicitly delimited machine-maintained block:

```markdown
<!-- LIFEOS:MEMORY:BEGIN — machine-maintained by memory-keeper. Edit above or below, not inside. -->
…
<!-- LIFEOS:MEMORY:END -->
```

Every future session therefore starts informed.

## 7. Guardrails

### 7.1 Human gates

Agents read, analyse, recommend and draft. Agents do **not** send email, submit forms, transact, or delete source documents. Anything irreversible or externally visible becomes an artefact in `proposed/` and waits. `documents/` originals are immutable and write-blocked by hook.

### 7.2 Hooks

| Hook | Event | Enforces |
|---|---|---|
| `session-start.sh` | `SessionStart` | loads profile, state digest, memory digest, open loops |
| `pii-guard.py` | `PreToolUse` (WebFetch, WebSearch) | blocks any outbound request matching SA ID numbers, account/policy numbers, email addresses, or names drawn from the live profile |
| `pii-guard.py` | `PreToolUse` (`Bash` matching `gh *`) | same matcher — `gh` is an egress channel and is guarded identically ([github.md §1.1](github.md#11-enforcement-not-etiquette)) |
| `pii-guard.py` | `PreToolUse` (Write, Edit) | blocks writes to `documents/` originals |
| `vault-audit.py` | `PostToolUse` | appends every vault mutation to `state/audit.jsonl` |
| `pre-commit` | git | refuses any staged path under `vault/`, and greps staged diffs for PII patterns and profile names |

Redaction is enforced by hook, not by convention ([ADR-0015](adr/0015-redaction-enforced-by-hook.md)). An agent that tries to look up "what does Discovery Classic Comprehensive cover" succeeds; one that includes a member number in the query is blocked, and the block is logged.

### 7.3 Epistemic honesty

Every output distinguishes four things, and the report templates enforce the distinction visually:

1. **What your documents say** — quoted, with hash and page.
2. **Arithmetic derived from them** — with the formula shown.
3. **Suggestions** — clearly marked as such, with effort and impact.
4. **Matters requiring a professional** — a registered financial advisor, tax practitioner, attorney, or the Master's Office.

LifeOS never impersonates professional advice. It prepares you to have a much sharper conversation with the professional.

Every claim about tax law, product terms or limits carries an "as at" date and a source. `.claude/rules/za/*.yaml` each declare a `refresh_interval`; when a cached rule is older than that, the agent must re-verify against the web before relying on it, and says so in the output.

### 7.4 Secrets and POPIA

LifeOS stores **pointers, never plaintext credentials** — "1Password → Personal → FNB Online", not a password. The digital-estate ledger records which entry exists, not what it contains.

POPIA posture: purpose limitation and minimality are design constraints, and every category in [data-dictionary.md](data-dictionary.md) carries a documented erasure path covering derived artefacts as well as source records. `/forget <subject>` executes it and reports what it removed and what it could not.

## 8. Growth

- **Domains** are enabled per `profile.yaml`. Disabling one does not break the relationship graph — it degrades to "not tracked" with an explicit note in the coverage map and the readiness score.
- **Packs** (`packs/<name>/`) layer agents, ledgers, rulebooks and commands onto the core by merge, not fork. Installing the `trusts` pack copies its charters and schemas in and registers its domains.
- **Jurisdiction** is a config axis. `.claude/rules/za/` ships; a `.claude/rules/<code>/` sibling can be added without touching agent logic ([ADR-0016](adr/0016-jurisdiction-as-config-axis.md)).
- **Self-extension** is the acceptance test: `/add-domain` invokes `meta-architect` to instantiate the charter template, register the ledger and owner, update the coverage map, and write the state file. The next `/heartbeat` picks the new domain up with **zero changes to the orchestrator**.

### 8.1 GitHub as the system's backlog

Agents use `gh` to track and maintain **the system itself** — tool bugs, statement adapters, stale rulebooks, schema bumps, agent refactors, phase progress. Issues give the machine a backlog that survives sessions, machines and context windows, and milestones give `/status` an external measure of phase progress rather than a self-assessment.

The boundary is absolute and is the whole design of it: **GitHub tracks the system; it never touches your life.** An issue may describe a *class of problem* ("ABSA changed its column order") and never an *instance of your data* ("your July statement, account 4051…"). Because `gh` is network egress to a third party, it is guarded by the same PII hook as `WebFetch`, filing is human-gated by default, and `state/system/issues.jsonl` — not GitHub — remains the source of truth so an outage can never break the loop. Full design in [github.md](github.md); rationale in [ADR-0017](adr/0017-github-for-system-work.md).

## 9. Scheduling

Claude Code is invoked, not resident, so "hourly forever" needs an external trigger. `tools/scheduler/heartbeat.sh` wraps a headless `claude -p /heartbeat` run with logging and a lockfile; `tools/scheduler/com.lifeos.heartbeat.plist.template` is a documented launchd job.

Neither is installed by the build ([ADR-0013](adr/0013-scheduling-template-not-installed.md)). Autonomous hourly writes to your financial records while you are not watching is a decision you make deliberately, with a one-line command, once you trust the system.

## 10. Verification

| Property | How it is proven |
|---|---|
| Idempotency | `/heartbeat` twice against `vault.example/` → no ledger diff, one journal line |
| Provenance | `/audit` walks every derived figure to a `doc_hash` + locator; orphans fail |
| Reproducibility | delete a ledger, re-run from `documents/` + config, assert byte-identical |
| Redaction | seeded fake SA ID + profile name in a web query **and in a `gh issue create` body** → hook must block both |
| Leak guard | stage a file under `vault/` → pre-commit must refuse |
| Coverage | `/audit` cross-checks the coverage map against the taxonomy; unowned leaf fails |
| Correctness | `pytest tools/py/tests`, `npx vitest run`, `ruff check` green at every phase boundary |
| Self-extension | `/add-domain` output participates in the next heartbeat unmodified |
