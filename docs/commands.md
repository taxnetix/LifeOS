# LifeOS — Command Contracts

> Status: Phase 0 (design). No command files are written yet.
> Each command below declares: **arguments · preconditions · effect · idempotency · human gate · phase**.

Three properties hold for every command without exception:

1. **No command performs an irreversible or externally-visible act without a human gate.** Draft, propose, wait.
2. **Every command is safe to interrupt.** A killed command leaves cursors unadvanced, so the next `/heartbeat` retries rather than loses.
3. **Every command states what it does not know.** Gaps are output, not silence.

---

## Core loop

### `/lifeos-init`
**Args** — none (interactive). **Pre** — none; run on a fresh clone.
**Effect** — interviews you; scaffolds `$VAULT` from `templates/vault/`; writes `profile/profile.yaml` (persons, entities, jurisdiction, currency, fiscal year, risk appetite, communication preferences, notification thresholds, cadences, enabled domains); selects `packs/`; seeds state, cursors and empty ledgers.
**Idempotent** — yes, by refusing: an existing vault is never overwritten. Re-running offers *amend* or *scaffold elsewhere*.
**Gate** — confirms the vault path and pack selection before writing anything.
**Phase** 1

### `/boot`
**Args** — none. **Pre** — vault exists.
**Effect** — orients: profile, state, open loops, calendar position, what's next. **Read-only** apart from one journal line. If it finds a broken state — failed prior run, corrupt cursor — it says so and *proposes* a repair rather than performing one.
**Idempotent** — yes, trivially. **Gate** — none needed. **Phase** 1

### `/heartbeat`
**Args** — optional `--dry-run`, `--max-items N`. **Pre** — vault exists.
**Effect** — one full pass of SENSE → TRIAGE → PLAN → DISPATCH → INTEGRATE → REFLECT → COMMIT. See [loop.md](loop.md).
**Idempotent** — **yes, and this is the system's central guarantee.** A second consecutive run against unchanged inputs writes no ledger diff, spawns no subagent, and appends one journal line.
**Gate** — never sends, submits, transacts or deletes. Everything externally-visible lands in `proposed/`.
**Phase** 1 (end to end with zero domains), deepening every phase after.

### `/consolidate`
**Args** — none. **Pre** — at least one journal entry.
**Effect** — the nightly memory ritual: promote durable facts, demote and expire stale items, deduplicate, **surface contradictions rather than resolving them**, compress, audit every change, regenerate the `CLAUDE.md` memory block, write tomorrow's brief.
**Idempotent** — yes; a second run finds nothing new to promote.
**Gate** — contradictions are surfaced for you, never silently overwritten. Hand-edited memory is preserved; mangling it is a failed run.
**Phase** 7 (memory scaffolding lands in Phase 1)

---

## Documents and readiness

### `/ingest`
**Args** — optional path. **Pre** — vault exists.
**Effect** — forces an inbox sweep: classify, extract type, OCR if needed, file immutably to `documents/<year>/<domain>/<hash>-<slug>.<ext>`, index, route to the owning domain.
**Idempotent** — yes; a document already in `documents/index.jsonl` by hash is skipped, not re-filed.
**Gate** — **originals are never deleted, modified or overwritten.** Unclassifiable files stay in `inbox/` with a gap record explaining why.
**Phase** 2

### `/readiness`
**Args** — optional subject. **Pre** — `readiness.jsonl` seeded.
**Effect** — Life File readiness score plus the shortest path to improve it, ranked by score-delta ÷ effort. Score is weighted by consequence-of-absence, not document count.
**Idempotent** — yes; pure recomputation. **Gate** — none. **Phase** 2

### `/life-file`
**Args** — `[--tier 1|2|3] [--person <ref>] [--html-only]`. **Pre** — a vault exists.
**Effect** — produces **the document you hand your family when you die**: `$VAULT/reports/life-file/<date>-tier<N>.{html,pdf}`. HTML is the source and is always written; the PDF is derived by `weasyprint`, and if that cannot load, the HTML is still produced with instructions to print it.
**Tiers** — **1 First 48 Hours** *(default)*, no identifiers, meant to be findable · **2 Executor Pack**, identifiers masked to last 4 · **3 Sealed Annexure**, unmasked, explicit request only, watermarked, and its generation is written to the audit log.
**Never at any tier** — passwords, PINs, safe combinations, alarm codes, seed phrases, private keys, 2FA secrets. The pointer is printed; the secret never is.
**Idempotent** — yes; identical vault state produces identical output apart from the generation date.
**Gate** — read-only with respect to the vault, but tier 3 is the most sensitive artefact the system can produce, so it must be asked for explicitly every time and is never the default.
**Notable** — the headline section is **"What your family will NOT find"**: the unsigned will, the missing title deed, the unrecorded suretyship, the nomination that contradicts the will. A Life File showing only what is known is a comfortable lie; the gaps are the point. See [ADR-0018](adr/0018-life-file-document.md).
**Phase** 2 (runs from Phase 1 in degraded form — cover, score and gaps only, which on an empty vault is the honest answer)

### `/audit`
**Args** — optional domain. **Pre** — ledgers exist.
**Effect** — proves every derived artefact traces back to a source document: walks each figure to a `doc_hash` + locator, cross-checks [coverage-map.md](coverage-map.md) against the taxonomy and against `.claude/agents/` on disk, verifies exactly one writer per ledger, verifies no absolute paths in the system repo.
**Fails** — on an orphan figure, an unowned leaf, a missing schema, a two-writer ledger.
**Idempotent** — yes; read-only. **Phase** 7

---

## Analysis and reporting

### `/review <domain>`
**Args** — domain name. **Pre** — domain enabled and has data.
**Effect** — deep review of one domain: current state, changes since last review, gaps, risks, ranked recommendations.
**Idempotent** — yes; regenerates the report. **Gate** — recommendations only. **Phase** 4+

### `/dashboard [domain]`
**Args** — optional domain; default all. **Pre** — ledgers populated.
**Effect** — regenerates self-contained HTML dashboards plus markdown summaries and CSV exports.
**Idempotent** — yes; byte-identical output from identical inputs.
**Constraint** — **every dashboard must open correctly with no network access.** Inline CSS and JS, inline SVG charts, no CDN, no build step.
**Phase** 3

### `/optimise [domain]`
**Args** — optional domain. **Pre** — domain has data.
**Effect** — ranked, costed optimisation proposals with rationale, evidence links and effort/impact estimates → `reports/` or `proposed/`.
**Idempotent** — yes; re-ranks against current data.
**Gate** — proposals only. It never cancels a policy, moves money, or contacts a provider.
**Phase** 3

### `/deadlines`
**Args** — optional horizon (default 90 days). **Pre** — `tax-deadlines.jsonl` seeded.
**Effect** — everything due, sorted, with lead times, owners and document readiness per deadline.
**Idempotent** — yes; read-only. **Phase** 5

### `/ask <question>`
**Args** — free text. **Pre** — ledgers exist.
**Effect** — answers across every domain, **with citations to your own documents** — hash, page, and the record IDs used.
**Idempotent** — yes; read-only.
**Gate** — distinguishes what your documents say, arithmetic derived from them, suggestions, and matters requiring a professional. Says "I don't know" when the answer is not in the vault, and opens a gap record.
**Phase** 7

### `/what-if <scenario>`
**Args** — free text (retire at 60, emigrate, sell the business, disability at 45, death tomorrow).
**Effect** — scenario model across every domain, with assumptions listed explicitly and sensitivity on the two or three that matter most. Writes to `reports/scenarios/`.
**Idempotent** — yes; deterministic given the same assumptions and data.
**Gate** — modelling only, clearly not advice. **Phase** 7

### `/life-event <desc>`
**Args** — free text (marriage, birth, death, job change, purchase, business sale).
**Effect** — records the event, then cascades impact analysis across every domain: which ledgers change, which policies need review, which tax consequences arise, which documents are now stale, which beneficiary nominations may now conflict. Queues the resulting work.
**Idempotent** — yes; the same event declared twice is one record with one cascade.
**Gate** — the cascade produces work items and proposals, never automatic changes to your affairs.
**Phase** 7

---

## System

### `/status`
**Args** — none.
**Effect** — health of every agent, staleness of every ledger, queue depth, parked items, open gaps, rulebooks past their refresh interval, and — via the GitHub mirror — open system issues and milestone progress per phase.
**Idempotent** — yes; read-only. **Phase** 1

### `/add-domain <name>`
**Args** — domain name. **Pre** — name not already taken.
**Effect** — `meta-architect` scaffolds a new domain from `templates/AGENT_CHARTER.md`: agent file, ledger schema, state file, coverage-map rows, catalogue entry.
**Idempotent** — yes, by refusing to clobber an existing domain.
**Acceptance** — the next `/heartbeat` picks the new domain up **with zero changes to the orchestrator**. This is definition-of-done #5.
**Phase** 7

### `/selftest`
**Args** — optional suite.
**Effect** — runs `pytest tools/py/tests`, `npx vitest run`, `ruff check`, plus the structural checks: one writer per ledger, no absolute paths in the system repo, every schema valid, the redaction hook blocking a seeded fake ID in both a web query and a `gh issue create` body, the pre-commit hook refusing a staged vault path, and heartbeat idempotency against `vault.example/`.
**Idempotent** — yes. **Phase** 1, extended each phase.

### `/forget <subject>`
**Args** — subject ref or category. **Pre** — subject exists.
**Effect** — executes the POPIA erasure path from [data-dictionary.md §6](data-dictionary.md#6-popia--classification-retention-erasure), covering source records, **derived artefacts**, journal, all three memory tiers and the `CLAUDE.md` block.
**Idempotent** — yes; a second run finds nothing.
**Gate** — **destructive, so double-gated.** It first produces a dry-run manifest of exactly what would be removed and waits for explicit confirmation. Originals are quarantined before shredding.
**Reports three things** — what it removed, what it retained and under which legal basis, and what it **could not** remove (an emailed report, a printed copy, a bank's own records, anything ever pushed to GitHub). Honesty about the limits of erasure is part of the erasure.
**Phase** 7

---

## GitHub — system backlog

Full design in [github.md](github.md). These operate **only** on system work; they can never carry personal data, and the PII hook enforces that on the `gh` call itself.

### `/issues`
**Args** — optional filter (`--phase N`, `--needs-human`, `--blocked`).
**Effect** — triaged view of `state/system/issues.jsonl`: open work, what is blocked on you, milestone progress. Works **offline** from the cached mirror.
**Idempotent** — yes; read-only. **Phase** 1

### `/issues propose <desc>`
**Effect** — drafts an issue to `proposed/issues/<slug>.md` with labels and milestone. Redaction-checked at draft time, so a violation is caught before you ever see a filed issue.
**Gate** — drafts only; nothing reaches GitHub. **Phase** 1

### `/issues push`
**Effect** — files every approved draft via `gh issue create`; reports numbers and URLs; updates the mirror.
**Gate** — **this is the egress point.** Each draft is shown and confirmed unless `github.autofile` is set. Blocked by the PII hook if any draft still matches a pattern.
**Phase** 1

### `/issues sync`
**Effect** — forces a mirror refresh. Degrades silently offline, marking `github.reachable: false`.
**Idempotent** — yes. **Phase** 1

---

## Summary

| Command | Phase | Mutates vault | Human gate |
|---|---|---|---|
| `/lifeos-init` | 1 | scaffolds | confirms path + packs |
| `/boot` | 1 | journal line only | — |
| `/heartbeat` | 1 | ledgers, state, journal | proposals only |
| `/status` | 1 | — | — |
| `/selftest` | 1 | — | — |
| `/issues`, `… sync` | 1 | mirror only | — |
| `/issues propose` | 1 | `proposed/` | — |
| `/issues push` | 1 | mirror | **egress — confirms each** |
| `/ingest` | 2 | documents, index | originals immutable |
| `/readiness` | 2 | report | — |
| `/life-file` | 2 | report | tier 3 explicit each time |
| `/dashboard` | 3 | reports | — |
| `/optimise` | 3 | reports, proposals | proposals only |
| `/review` | 4 | reports | proposals only |
| `/deadlines` | 5 | — | — |
| `/consolidate` | 7 | memory, CLAUDE.md | contradictions surfaced |
| `/ask` | 7 | — | — |
| `/what-if` | 7 | reports | — |
| `/life-event` | 7 | ledgers, queue | cascade → work items |
| `/add-domain` | 7 | system repo | — |
| `/audit` | 7 | — | — |
| `/forget` | 7 | **deletes** | **dry-run + confirm** |
