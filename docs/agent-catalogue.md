# LifeOS — Agent Catalogue

> Status: Phase 0 (design). No agent files are written yet.
> Every agent below is generated from `templates/AGENT_CHARTER.md` and obeys the same seven-part contract. See [architecture.md §3](architecture.md#3-the-fractal-unit).

## Ledger ownership — the authoritative table

Exactly one agent may write any given ledger. Everyone else reads. This table is the source of truth; a `/selftest` check parses agent charters and fails if any ledger has zero or two owners.

| Ledger (`$VAULT/ledgers/`) | Sole writer | Readers |
|---|---|---|
| `people.jsonl` | `identity` | all |
| `entities.jsonl` | `identity` | all |
| `relationships.jsonl` | `identity` | all |
| `accounts.jsonl` | `finance` | tax, estate, assets, readiness |
| `transactions.jsonl` | `finance` | tax, analyst, living |
| `recurring-payments.jsonl` | `finance` | living, insurance, investments |
| `budgets.yaml` | `finance` | analyst |
| `networth-snapshots.jsonl` | `finance` | estate, investments, analyst |
| `medical-aid.jsonl` | `living` | insurance, tax, readiness |
| `employee-benefits.jsonl` | `living` | insurance, investments, estate |
| `subscriptions.jsonl` | `living` | finance |
| `digital-estate.jsonl` | `living` | estate, readiness |
| `household.jsonl` | `living` | insurance, readiness |
| `leases.jsonl` | `living` | tax, assets, finance |
| `policies.jsonl` | `insurance` | estate, tax, living, readiness |
| `holdings.jsonl` | `investments` | tax, estate, assets, analyst |
| `contributions.jsonl` | `investments` | tax |
| `assets.jsonl` | `assets` | estate, insurance, tax, finance |
| `liabilities.jsonl` | `assets` | estate, finance, tax |
| `valuations.jsonl` | `assets` | estate, analyst |
| `fx-rates.jsonl` | `assets` | all |
| `tax-events.jsonl` | `tax` | estate, analyst |
| `tax-deadlines.jsonl` | `tax` | orchestrator, readiness |
| `wills.jsonl` | `estate` | trusts, readiness, final-wishes |
| `beneficiaries.jsonl` | `estate` | insurance, investments, readiness |
| `trusts.jsonl` | `trusts` | estate, tax, assets |
| `trustees.jsonl` | `trusts` | estate, readiness |
| `distributions.jsonl` | `trusts` | tax, finance |
| `loan-accounts.jsonl` | `trusts` | tax, estate |
| `final-wishes.jsonl` | `final-wishes` | estate, readiness |
| `readiness.jsonl` | `readiness` | orchestrator |
| `documents/index.jsonl` | `librarian` | all |
| `state/gaps.jsonl` | *append-only, many writers* | all |
| `state/queue.json` | `orchestrator` | all (read) |
| `state/system/issues.jsonl` | `orchestrator` (sync) | `meta-architect` |
| `memory/**` | `memory-keeper` | all (read) |

---

# System agents (6)

## `orchestrator`

**Scope.** Owns the loop, the queue and cross-domain integration. Does **not** own any domain ledger, does not extract documents, does not perform domain analysis. It is a dispatcher and an integrator, nothing else.

**Inputs.** `tools/py/sense.py` output · `state/queue.json` · `state/cursors.json` · `profile.yaml` · structured results from every dispatched agent · `.claude/rules/za/cross-domain.yaml`.

**Outputs.** `state/queue.json` (sole writer) · `state/cursors.json` · `state/run-log.jsonl` · `state/system/issues.jsonl` (GitHub mirror, refreshed in SENSE via `tools/py/gh_sync.py`) · `journal/<date>.md`.

**State.** `state/agents/orchestrator.json` — last run, wave count, queue depth, items parked, failures.

**Cadence.** Every `/heartbeat`. Triggered early by `/ingest`, `/life-event`, or any command that mutates the queue.

**Sub-agents.** All of them. It is the only component that spawns agents ([ADR-0002](adr/0002-fractal-definition-flat-runtime.md)).

**Done when.** Every selected work item reached a terminal state, all returned gaps and questions merged, cross-domain implications either resolved or queued, journal written, cursors advanced. A run that cannot reach COMMIT leaves cursors untouched so the next SENSE emits `run.failed`.

## `librarian`

**Scope.** Owns `inbox/` → `documents/`. Classify, extract type, name, file, dedupe, index, route to the owning domain. Never loses an original; never interprets content beyond classification — the meaning of a document is the domain agent's job.

**Inputs.** Everything in `inbox/`. `documents/index.jsonl`. `.claude/rules/document-types.yaml`.

**Outputs.** `documents/<year>/<domain>/<hash>-<slug>.<ext>` (immutable) · `documents/index.jsonl` (sole writer) · gap records for unreadable or unclassifiable files · dispatch requests to the routed domain.

**State.** `state/agents/librarian.json` — files processed, unclassified backlog, OCR failures, new document types seen.

**Cadence.** Every heartbeat when `inbox.new` fires; forced by `/ingest`.

**Sub-agents.** None yet. Candidates if volume justifies: `ocr-specialist`, `type-classifier`.

**Done when.** `inbox/` is empty or every remaining file has a gap record explaining why it could not be filed. Every filed document has an index entry with hash, type, domain, date range and page count. **An original is never deleted, never modified, never overwritten.**

## `memory-keeper`

**Scope.** Owns `memory/` — all three tiers, the consolidation ritual, and the `CLAUDE.md` machine-maintained block. Does not own the journal (that is the orchestrator's) but reads it.

**Inputs.** `journal/` · agent state files · `proposed/` decisions · session transcripts · existing memory.

**Outputs.** `memory/short/`, `memory/medium/`, `memory/long/` (sole writer) · `memory/audit.jsonl` · the delimited block in `CLAUDE.md` · contradiction reports.

**State.** `state/agents/memory-keeper.json` — last consolidation, promotions, demotions, expiries, unresolved contradictions.

**Cadence.** Daily via `/consolidate`. Early trigger on `/life-event` or an explicit standing instruction from you.

**Sub-agents.** None.

**Done when.** Durable facts promoted, stale items demoted or expired, duplicates merged, contradictions surfaced rather than resolved, every change audited, `CLAUDE.md` block regenerated, tomorrow's brief written. **Memory files remain human-readable and hand-editable** — a consolidation that mangles hand edits is a failed run.

## `meta-architect`

**Scope.** Owns the system itself. Scaffolds domains and specialists from the charter template, audits coverage against the taxonomy, keeps this catalogue accurate, proposes refactors. Does **not** touch vault data.

**Inputs.** `templates/AGENT_CHARTER.md` · all agent state files · [coverage-map.md](coverage-map.md) · `profile.yaml` enabled domains · `state/system/issues.jsonl` (the GitHub mirror).

**Outputs.** New `.claude/agents/*.md` · new `templates/schemas/*.json` · updates to [coverage-map.md](coverage-map.md) and this file · refactor proposals to `proposed/` · **GitHub issue drafts to `proposed/issues/`, and — once approved — issues, labels, milestones and pull requests via `gh`**.

**State.** `state/agents/meta-architect.json` — coverage score, agents proposed for promotion, overload signals, open system issues by phase.

**Cadence.** Quarterly audit; on demand via `/add-domain` and `/issues`; early on a `document.type.unseen`, `rule.expired` or `github.*` signal.

**GitHub.** `meta-architect` owns the system's own backlog: authoring, triage, labelling, milestones and PRs ([github.md](github.md)). It drafts; it does not file. A draft becomes a real issue only after you approve it, unless `github.autofile` is set. It may **never** delete a repo or issue, force-push, rewrite history, change branch protection, or push to `main` — every code change it produces arrives as a pull request. Its issues describe classes of problem, never instances of your data, and the PII hook enforces that rather than trusting it.

**Sub-agents.** None.

**Done when.** Every taxonomy leaf has an owner, schema or checklist entry; the catalogue matches the agent files on disk; overloaded agents have a promotion proposal. Overload is measured, not guessed: run duration, error rate, open-loop count and ledger count per agent, thresholds in `profile.yaml`.

## `analyst` *(shared service)*

**Scope.** Aggregation, trend, variance, ratio, projection and scenario mathematics for any domain that asks. Owns **no** ledger and writes none — it computes and returns.

**Inputs.** Any ledger (read-only) · `budgets.yaml` · `.claude/rules/za/` · a computation request.

**Outputs.** Structured results to the calling agent · `reports/analysis/*.json` intermediates. Every figure carries its formula and the record IDs it was computed from.

**State.** `state/agents/analyst.json` — computations run, inputs that were stale at compute time.

**Cadence.** On request only.

**Sub-agents.** None.

**Done when.** Every returned figure traces to source record IDs, stale inputs are flagged in the result rather than silently used, and no figure is produced from an empty or partial ledger without saying so.

## `visualiser` *(shared service)*

**Scope.** Rendering only. Self-contained HTML dashboards, markdown summaries, CSV exports. Owns no ledger, computes no figures — it renders what `analyst` produced.

**Inputs.** Analyst output · report templates · `profile.yaml → communication`.

**Outputs.** `reports/**/*.html` · `reports/**/*.md` · `reports/**/*.csv`.

**State.** `state/agents/visualiser.json` — dashboards rendered, staleness of each.

**Cadence.** On request; monthly for the standing dashboard set.

**Sub-agents.** None.

**Done when.** Every HTML file opens correctly with **no network access** — inline CSS and JS, inline SVG charts, no CDN, no build step. Every figure on screen links back to its source records. Report length obeys your stated preference.

---

# Domain agents (11)

Each entry below is compressed. Full seven-part charters are generated into `.claude/agents/` in the phase that builds the domain.

## `identity` — taxonomy A

**Owns.** People, entities and the relationship graph that ties every person and entity to every obligation, asset and benefit elsewhere in the system. Self, spouse, children (including from prior marriages and deceased), dependants, parents. Core records: ID numbers, passports, licences, birth/marriage certificates, maiden names, addresses, contact channels. Marital regime — ANC, accrual, in community — plus divorce, settlement and maintenance orders. Employment details. Business entities: registration and tax numbers, key personnel, shareholding, directorships, auditors, agreements, financial statements with a currency check.

**Does not own.** The obligations themselves — only the identities and the edges between them.

**Notable.** The relationship graph is what makes cross-domain analysis possible at all. `identity` is a Phase 1 dependency for everything else, and it is the agent most likely to have to say *"I don't know"* — an unknown ID number is a gap record, never a placeholder.

**Cadence.** On document arrival; annual review of currency (financial statements < 6 months, licence expiry, passport expiry).

## `living` — taxonomy B (excluding banking)

**Owns.** Medical aid (scheme, plan, member number, main member vs dependants, dependant roster, gap cover, family doctor, organ donor status, dentistry/optometry sub-limits, PMB awareness, savings/threshold tracking, annual option-change window). Employee benefits (pension/provident and member number, group life, income protection, funeral, risk benefits) — explicitly cross-referenced against personal cover to find duplication and gaps. Subscriptions and contracts. Digital estate — accounts, usernames, **credential location only, never a secret**, devices, digital executor. Household security and access: safe code location, alarm custodian, spare keys, firearm licences, service providers. Leases in either direction.

**Does not own.** Bank accounts and transactions (`finance`), insurance policies you bought yourself (`insurance`).

**Notable.** Half of the health-cover flagship lives here; the other half is `insurance`. Neither can answer it alone, which is the point.

## `finance` — taxonomy B/E

**Owns.** All bank accounts per person and per entity. Transactions. Every debit order and recurring cash payment — type, amount, source account, escalation, contract end date, cancellation route. Budgets. Net worth snapshots. Income tax reference numbers are held by `identity`; the accounts they attach to are held here.

**Does not own.** Investments (`investments`), liabilities as balance-sheet items (`assets` — though `finance` sees the repayments).

**Notable.** Carries the money flagship: statements → categorised ledger → cashflow dashboard → budget variance → optimisation report. Must handle multiple banks and multiple entities, keep personal and business strictly separate, and still roll up to one consolidated view. The `proposed/` escape hatch matters most here — an uncertain categorisation is a question, not a silent assignment.

**Cadence.** Monthly ingestion cycle; weekly cashflow check; event-driven on `inbox.new` of type statement.

## `insurance` — taxonomy C

**Owns.** Life, capital disability, income protection, dread disease, funeral. Short-term: contents, buildings, vehicle, all-risk, portable possessions, liability, cyber. Business: key person, buy-and-sell, contingent liability, business overheads, professional indemnity. Per policy: insurer, number, type, premium, escalation, beneficiaries, cession, waiting periods, exclusions, broker.

**Analysis.** Needs analysis vs actual cover · duplication against group benefits · premium efficiency · estate liquidity contribution · `s3(3)(a)(ii)` deemed-property implications · quote-refresh cadence.

**Cadence.** Quarterly adequacy review; 45 days before each policy anniversary; event-driven on `/life-event`.

## `investments` — taxonomy D

**Owns.** Retirement annuities, preservation funds, pension/provident funds and two-pot components. Discretionary: unit trusts, share portfolios, offshore, money market, crypto, TFSA. Per holding: platform, account number, type, mandate, fees (advice/platform/fund), beneficiaries, performance.

**Analysis.** Asset allocation vs policy · Reg 28 compliance where applicable · total expense ratio drag · currency exposure · contribution optimisation against the retirement-contribution deduction cap · TFSA annual and lifetime limits · `s10C` · drawdown modelling and retirement adequacy projection.

**Cadence.** Quarterly drift review; annual contribution optimisation with a 60-day lead before the tax year end.

## `assets` — taxonomy E

**Owns.** Property (description, address, title deed location, valuation, bond, rates, levies, tenants, sectional-title deeds). Movables: vehicles, jewellery, art, firearms and licences, collectibles, timeshare, offshore assets. Liabilities: home loans, vehicle finance, overdrafts, credit cards, store and clothing accounts, personal loans, cellphone contracts, **surety and suretyship obligations**, assets pledged as security, insolvency history. Rights: usufruct, fideicommissum, annuity and trust income entitlements. FX rates.

**Notable.** Suretyship is the item most often forgotten and most damaging at death — it is a required field on the readiness checklist, not an optional one.

## `tax` — taxonomy F

**Owns.** Personal: annual return, IRP5/IT3(a), IT3(b)/(c), medical tax credits, RA deduction, travel/logbook, home office, rental schedules, CGT events, provisional tax, donations tax, `s10(1)(o)(ii)` where relevant. Business: company/CC/trust returns, provisional tax, VAT cycle, PAYE/UIF/SDL, dividends tax. Trust: distributions, `s7C` loan interest, conduit principle, attribution rules. Deadline calendar, document readiness checklist, effective-rate tracking, structuring reviews.

**Rulebooks.** `.claude/rules/za/` — fetched and cached with an explicit "as at" date and a refresh interval. A rule past its interval must be re-verified before reliance, and every output says when it was last verified.

**Boundary.** Prepares, computes, and flags. Does not file, does not submit, and states plainly when a registered tax practitioner is required.

## `estate` — taxonomy G

**Owns.** Wills (signed? combined? date, executor, custodian, physical location, review triggers). Living will and its location. Further wishes supportive of the will. Estate duty and CGT-at-death calculation, `s4A` abatement, section 4(q) spousal roll-over, executor's fees, Master's fees, **liquidity shortfall analysis**. Beneficiary nominations across every policy and fund, checked for conflict with the will. Deceased spouse estate details and prior estate rights. People to be notified — name, relationship, contact. Ongoing court cases (courts must be notified on death) and maintenance obligations.

**Notable.** The beneficiary-vs-will conflict check is a cross-domain read across `policies`, `holdings`, `employee-benefits` and `wills`. A nomination that contradicts the will is one of the highest-value findings the system can produce, and it is invisible from inside any single domain.

## `trusts` — taxonomy H (also `packs/trusts/`)

**Owns.** Trust register (name, MT number, type — inter vivos discretionary, testamentary, bewind, special — deed and amendments, letters of authority). Trustees: identity, appointments and resignations, independent trustee presence, resolutions register, minutes and cadence. Beneficiaries: capital vs income, contingent vs vested, classes. Assets, loan accounts, `s7C` interest exposure, distributions and their tax attribution. Compliance calendar: annual financial statements, IT12TR, beneficial-ownership register, FICA obligations, independent-trustee and proper-administration duties, trustee liability. Testamentary trust management for minors and its interaction with guardianship.

**Notable.** Documented separation of trust affairs from personal affairs — while the relationship graph still links them. This is the one domain shipped as a standalone pack, because it is a colleague's entire use case.

## `final-wishes` — taxonomy I

**Owns.** Burial vs cremation per person, grave purchased, plot details, ashes instructions. Funeral cover and provider contacts, service preferences, and the immediate-liquidity plan for the first 30 days.

**Notable.** Small, and deliberately separate from `estate`. It is the part a grieving family reads first, so it must be answerable without a lawyer, and the 30-day liquidity plan is a hard number cross-read from `finance` and `insurance`.

## `readiness` — taxonomy J

**Owns.** The Life File checklist as a live, continuously-scored artefact: every required document per person and entity — present, absent or expired; where the original is kept; who else needs a copy. Produces a single **Readiness Score** and the shortest path to improving it.

**Inputs.** Every other domain's ledgers, plus `documents/index.jsonl` and `state/gaps.jsonl`.

**Also produces the Life File.** `/life-file` composes the document handed to family on death — three audience tiers, identifiers masked or absent except in the explicitly-requested sealed tier, no secrets at any tier, and **"What your family will NOT find" as the headline section**. `analyst` supplies the 30-day liquidity figure; `visualiser` renders HTML, and `weasyprint` derives the PDF. See [ADR-0018](adr/0018-life-file-document.md).

**Notable.** This is the "be prepared for your what-if day" engine, and the thing that makes the system's value obvious on day one — which is why it lands in Phase 2, before any of the clever analysis. Even a nearly-empty vault produces a Life File, and on an empty vault it is almost entirely gaps, which is exactly the useful answer.

---

## Specialists not yet promoted

These exist as charter sections and skills inside their domain agent. `meta-architect` proposes promotion to a standalone agent when the owning agent's state file shows overload ([ADR-0010](adr/0010-lean-agent-tree.md)).

| Candidate | Lives inside | Promote when |
|---|---|---|
| `statement-parser` | `finance` | more than ~6 bank adapters in active use |
| `categoriser` | `finance` | categorisation rules exceed what one charter can carry |
| `medical-aid-analyst` | `living` | plan comparison across more than 2 schemes |
| `policy-comprehension` | `insurance` | policy wording analysis becomes routine |
| `reg28-checker` | `investments` | more than one Reg 28-bound fund |
| `provisional-tax` | `tax` | more than 2 provisional taxpayers |
| `vat` | `tax` | a VAT-registered entity is added |
| `estate-duty-modeller` | `estate` | scenario modelling becomes routine |
| `trust-compliance` | `trusts` | more than ~3 trusts under administration |
| `ocr-specialist` | `librarian` | scanned-document volume justifies it |
