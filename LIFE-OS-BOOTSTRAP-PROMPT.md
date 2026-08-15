# Claude Code Bootstrap Prompt — "LifeOS"

> Paste everything below the line into Claude Code, running in an empty git repo.
> Recommended first move: run it in Plan Mode (Shift+Tab) so you review the architecture before any files are written.

---

You are the architect and first engineer of **LifeOS** — a personal life-management system implemented **entirely as a Claude Code agentic system**. Not a web app. Not a backend. The repository *is* the product; Claude Code *is* the runtime.

Read this whole brief. Then **produce a plan and stop for my approval before writing any code.** After I approve, build it phase by phase, pausing at the end of each phase.

## 1. What LifeOS is

A repo containing a self-directing network of agents, skills, commands, pipelines and state files that together document, understand, monitor and optimise the whole of a person's life — personal *and* business, treated as one interconnected graph. It ingests real documents (bank statements, policy schedules, medical aid plans, tax certificates, wills, trust deeds, payslips, invoices), turns them into structured ledgers, analyses them, produces dashboards and optimisation reports, remembers what it learns, and knows what to do next every time it wakes up.

Primary user: a South African software engineer/CTO with personal finances, multiple business interests, a PhD on the side, a family, and a tax code that punishes inattention. Secondary user: a colleague whose main interest is **trust administration**. The system must serve both from the same codebase.

## 2. Hard constraints — read these twice

1. **Claude-native only.** The mechanics are `CLAUDE.md`, `.claude/agents/`, `.claude/commands/`, `.claude/skills/`, `.claude/hooks/`, `.claude/settings.json`, subagents, the `Task` tool, MCP, and plain files on disk. No Node/Python service, no Docker, no Postgres, no React app, no API server. Python and shell scripts are permitted **only** as leaf tools invoked by agents (parsers, chart renderers, validators) — never as a runtime that orchestrates.
2. **Files are the database.** Markdown for narrative and reports. YAML for configuration and profile. JSONL append-only for events, transactions and audit. JSON for state and indices. CSV for tabular exports. SQLite is permitted *only* as a derived read-model that can be rebuilt from the JSONL ledgers by re-running a pipeline — never as a source of truth. Every derived artefact must be reproducible from source documents plus config.
3. **Local-first and private by default.** Nothing leaves the machine except explicit, agent-declared web lookups for public reference information (tax tables, product terms, benchmark rates). Never send personal identifiers, account numbers, ID numbers or document contents to a web search. Redaction is a hard rule enforced by a hook.
4. **System and data are separate.** This is the single most important structural decision — see §3.
5. **Every irreversible or externally-visible action is human-gated.** Agents may read, analyse, recommend, draft. Agents may not send email, submit forms, transact, or delete source documents. They produce a `PROPOSED/` artefact and wait.
6. **Fractal by construction.** Every agent — from the top orchestrator to a leaf specialist — obeys the *same* structural contract (§5). A new life domain is added by instantiating that contract, not by writing bespoke plumbing. The system must be able to grow a new branch of itself using its own scaffolding command.

## 3. Repository shape: system vs vault

The repo I share with colleagues must contain **zero personal data**.

```
lifeos/                          # THIS repo — shareable, public-safe, MIT
├── CLAUDE.md                    # constitution + router; loaded every session
├── README.md                    # what it is, how to bootstrap
├── SECURITY.md                  # threat model, redaction rules, what never leaves disk
├── .claude/
│   ├── settings.json
│   ├── agents/                  # agent definitions (see §5, §6)
│   ├── commands/                # slash commands (see §9)
│   ├── skills/                  # reusable procedural skills (see §9)
│   ├── hooks/                   # guardrails: redaction, vault-write audit, pre-commit
│   └── rules/                   # domain rulebooks (SA tax tables, Reg 28, estate duty…)
├── templates/                   # blank ledger schemas, report templates, charter template
├── packs/                       # optional domain packs: trusts, sme-owner, expat, phd
├── tools/                       # leaf scripts: pdf extract, statement parse, chart render
├── docs/                        # architecture, agent catalogue, data dictionary, ADRs
└── vault.example/               # fully-populated FAKE vault, for demo & tests

$LIFEOS_VAULT/                   # SEPARATE, git-ignored or private repo — real life
├── profile/                     # who I am, entities, preferences, consent settings
├── inbox/                       # I drop documents here. This is the only thing I do manually.
├── documents/                   # filed originals, content-addressed, immutable
├── ledgers/                     # normalised JSONL: transactions, policies, assets, obligations
├── state/                       # agent status, work queue, cursors, run log
├── memory/                      # short / medium / long term (see §8)
├── reports/                     # generated dashboards, reviews, optimisation reports
├── proposed/                    # drafts awaiting my approval
└── journal/                     # daily narrative log of everything the system did & why
```

The vault path resolves from `$LIFEOS_VAULT`, falling back to `./vault/` which is git-ignored. `/lifeos-init` bootstraps a vault from `templates/`. All agents address the vault through a single documented path convention — never hardcoded absolute paths.

## 4. The perpetual loop

This is the heart of the thing. Design it so that **the same command, run repeatedly forever, always advances the system correctly** — including when nothing has changed (in which case it costs almost nothing and says so).

```
/boot  →  orient: read profile, state, open loops, calendar position
          ↓
/heartbeat  (hourly, or on demand)
   1. SENSE     detect change since last cursor: new files in inbox/, elapsed
                cadence triggers, stale data, expiring obligations, open questions,
                unanswered proposals, failed prior runs
   2. TRIAGE    convert every signal into work items with domain, priority, cost
                estimate, dependencies; write to state/queue.json
   3. PLAN      select the next coherent batch — respect dependencies, budget,
                and "one domain deep beats five domains shallow"
   4. DISPATCH  delegate each item to the owning domain agent via Task; agents may
                recursively dispatch to their own specialists
   5. INTEGRATE collect results, update ledgers and state, resolve cross-domain
                implications (this is where the holistic view actually happens)
   6. REFLECT   write journal entry: what changed, what it means, what's next,
                what I need from the human
   7. COMMIT    advance cursors; leave the system in a resumable state
```

Cadence triggers, all driven by comparing `state/cursors.json` against the clock and the South African fiscal calendar:

- **hourly** — heartbeat: inbox sweep, cheap change detection
- **daily (evening)** — memory consolidation (§8), journal roll-up, tomorrow's brief
- **weekly** — cashflow check, budget variance, open-loop review, document gaps
- **monthly** — statement ingestion cycle, full financial dashboard refresh, subscription/debit-order audit, net worth snapshot
- **quarterly** — deep domain review, insurance & medical aid adequacy, investment allocation drift, provisional tax posture, "get fresh quotes" sweep
- **annual** — 28/29 Feb tax year-end pack, RA contribution optimisation before year end, TFSA limit check, will & beneficiary nomination review, policy renewal calendar, Reg 28 compliance, estate liquidity calculation
- **event-driven** — new document type never seen before, life event declared (`/life-event`), material variance breach, deadline within N days

Two failure modes to design against explicitly: **doing nothing because nothing obviously changed**, and **redoing work already done**. The cursor + queue + journal triad exists to prevent both. Heartbeat must be idempotent.

## 5. The universal agent contract (the fractal unit)

Every agent, at every level, is defined by the same seven-part charter. Write this as `templates/AGENT_CHARTER.md` and generate all agents from it.

1. **Identity & scope** — what slice of life it owns; what it explicitly does *not* own.
2. **Inputs** — which document types, ledgers, rulebooks and upstream agent outputs it consumes.
3. **Outputs** — ledgers it may write, reports it produces, proposals it may draft. Exactly one agent owns write access to any given ledger.
4. **State file** — `state/agents/<name>.json`: last run, cursor, health, open loops, known gaps, confidence, pending questions for the human.
5. **Cadence & triggers** — when it wakes, and what makes it wake early.
6. **Sub-agents** — its specialists. A domain agent decomposes into specialists; specialists may decompose further. Depth is not fixed — a domain earns depth by complexity. This is the fractal property: the orchestrator's relationship to a domain agent is structurally identical to a domain agent's relationship to its specialists.
7. **Definition of done & self-review** — how it knows a run succeeded, what it checks, and how it reports its own limitations. Every agent ends every run by asking: *what do I now know that I didn't, what is still missing, and what would make me more useful next time?* Those answers become work items and memory candidates.

Three cross-cutting agents sit outside the domain tree:

- **`librarian`** — owns `inbox/` → `documents/`: classify, extract, name, file, dedupe, index, detect document type, route to domain, never lose an original.
- **`memory-keeper`** — owns `memory/` (§8).
- **`meta-architect`** — owns the system itself: scaffolds new domains and specialists from the charter template, audits agent coverage against the Life File taxonomy (§6), keeps `docs/agent-catalogue.md` accurate, proposes refactors when an agent's state file shows it's overloaded. This is what makes the system able to grow itself.

## 6. Domain taxonomy — must be complete

Derived from the *Efficient Wealth / Board of Executors "Life File"* structure, then extended for a South African business owner. Every leaf below must be represented — as an agent, a ledger schema, or a checklist item with an owner. Nothing may be silently dropped.

**A. Identity, People & Entities** (`agents/identity/`)
- Individuals: self, spouse, children (incl. from prior marriages and deceased), dependants, parents & their birth dates
- Core records: ID numbers, passports, driver's licences, birth/marriage certificates, maiden names, addresses (home & postal), all contact channels
- Marital regime: ANC / accrual / in community, divorce orders, settlement & maintenance orders
- Employment: employer, occupation, work contacts, employee numbers
- Business entities: name, registration number, tax number, addresses, key personnel & contacts, shareholding, directorships, auditors/accountants, partnership & CC/company agreements, financial statements (currency < 6 months)
- Relationship graph tying every person and entity to every obligation, asset and benefit elsewhere in the system

**B. Day-to-Day Living** (`agents/living/`)
- Health & medical aid: scheme, plan/option, member number, main member vs dependants, dependant roster, gap cover provider & policy, family doctor & contacts, organ donor status, dentistry/optometry sub-limits, PMB awareness, savings/threshold tracking, annual option-change window
- Employee benefits: pension/provident fund & member number, group life, income protection, funeral cover, risk benefits — explicitly cross-referenced against personal cover to find duplication and gaps
- Income tax reference numbers per person and entity
- Banking: all accounts per person and per entity — bank, branch, account number, type
- Regular payments: every debit order and recurring cash payment — type, amount, source account, escalation, contract end date, cancellation route
- Subscriptions & contracts: DSTV/streaming, phone & data, gym, software, memberships
- Digital estate: accounts, usernames, credential *location* (never plaintext secrets — pointer to password manager entry), devices, digital executor
- Household security & access: safe code location, alarm code custodian, spare keys, firearm licences, service-provider contacts (repairs, alarm, plumbing, electrical)
- Rental & lease contracts in either direction

**C. Insurance & Risk** (`agents/insurance/`)
- Life assurance, disability/capital disability, income protection, dread disease, funeral
- Short-term: household contents, buildings, vehicle, all-risk, portable possessions, liability, cyber
- Business: key person, buy-and-sell, contingent liability, business overheads, professional indemnity
- Per policy: insurer, policy number, type, premium, escalation, beneficiaries, cession, waiting periods, exclusions, broker
- Analysis: needs analysis vs actual cover, duplication, premium efficiency, estate liquidity contribution, `s3(3)(a)(ii)` deemed-property implications, quote-refresh cadence

**D. Investments & Retirement** (`agents/investments/`)
- Retirement annuities, preservation funds, pension/provident funds, two-pot components
- Discretionary: unit trusts, share portfolios, offshore, money market, crypto, TFSA
- Per holding: platform, account number, type, mandate, fees (advice/platform/fund), beneficiaries, performance
- Analysis: asset allocation vs policy, Reg 28 compliance where applicable, total expense ratio drag, currency exposure, contribution optimisation against the 27.5%/R350k deduction cap, TFSA annual & lifetime limits, `s10C`, drawdown modelling and retirement adequacy projection

**E. Assets & Liabilities** (`agents/assets/`)
- Property: description, address, title deed location, valuation, bond, rates, levies, tenants, transport/sectional-title deeds
- Movables: vehicles & registrations, jewellery, art, firearms & licences, collectibles, timeshare, offshore assets
- Liabilities: home loans, vehicle finance, overdrafts, credit cards, store & clothing accounts, personal loans, cellphone contracts, surety and suretyship obligations, assets pledged as security, insolvency history
- Rights: usufruct, fideicommissum, annuity and trust income entitlements
- Rolling net worth statement and balance-sheet history

**F. Tax** (`agents/tax/`) — first-class, SA-specific
- Personal: annual return, IRP5/IT3(a), IT3(b)/(c), medical tax credits, RA deduction, travel/logbook, home office, rental income schedules, CGT events, provisional tax (Aug & Feb), donations tax, `s10(1)(o)(ii)` if relevant
- Business: company/CC/trust returns, provisional tax, VAT cycle, PAYE/UIF/SDL, dividends tax
- Trust: distributions, `s7C` loan interest, conduit principle, attribution rules
- Deadline calendar, document readiness checklist, effective-rate tracking, structuring reviews using current SARS tables (fetch and cache the live tables into `.claude/rules/`, with an explicit "as at" date and re-verification cadence)

**G. Estate, Wills & Succession** (`agents/estate/`)
- Wills: signed? combined? date, executor, custodian & physical location, review triggers
- Living will and its location
- Further wishes and instructions supportive of the will
- Estate duty and CGT-at-death calculation, `s4A` abatement, section 4(q) spousal roll-over, executor's fees, master's fees, liquidity shortfall analysis
- Beneficiary nominations across every policy and fund, checked for conflict with the will
- Estate details of any deceased spouse, prior estate rights
- Family and friends to be notified — name, relationship, contact
- Ongoing court cases (courts must be notified on death), maintenance obligations

**H. Trusts** (`agents/trusts/` — also shipped as `packs/trusts/`)
Built for my colleague, but valuable to everyone. Deep enough to stand alone:
- Trust register: name, MT number, type (inter vivos discretionary / testamentary / bewind / special), deed & amendments, letters of authority
- Trustees: identity, appointments & resignations, independent trustee presence, resolutions register, meeting minutes and cadence
- Beneficiaries: capital vs income, contingent vs vested, classes
- Assets, loan accounts, `s7C` interest exposure, distributions and their tax attribution
- Compliance calendar: annual financial statements, IT12TR, beneficial-ownership register (Master's filing), FICA obligations, independent-trustee and proper-administration duties, trustee liability
- Testamentary trust management for minors, and the interaction with guardianship
- Documented separation of trust affairs from personal affairs, with the relationship graph nonetheless linking them

**I. Funeral & Final Wishes** (`agents/final-wishes/`)
- Burial vs cremation per person, grave purchased?, plot details, ashes instructions
- Funeral cover and provider contacts, service preferences, immediate-liquidity plan for the first 30 days

**J. Document Readiness** (`agents/readiness/`)
The Life File checklist as a live, continuously-scored artefact rather than a paper form: every required document per person and entity, present/absent/expired, where the original is kept, who else needs a copy. Produces a single **Readiness Score** and the shortest path to improving it. This is the "be prepared for your what-if day" engine — and the thing that makes the system's value obvious on day one.

Also required: an **`agents/orchestrator/`** at the root, and **`agents/analyst/`** + **`agents/visualiser/`** as shared services any domain can call.

## 7. Pipelines

Implement as skills so any agent can invoke them, with a standard stage contract and resumability:

```
INGEST      inbox sweep → type detection → OCR if needed → original filed
            immutably to documents/<year>/<domain>/<hash>-<slug>.<ext>
EXTRACT     PDF/DOCX/XLSX/CSV/MD/TXT/image → structured records + provenance
            (every extracted field carries source doc hash, page, confidence)
NORMALISE   map to ledger schema, dedupe, reconcile against existing records,
            flag conflicts for human review rather than guessing
ENRICH      categorise (transactions), classify (policy clauses), tag entities,
            link to the relationship graph, look up public reference data
ANALYSE     aggregations, trends, variance vs budget, ratios, projections,
            gap analysis, scenario modelling
VISUALISE   self-contained HTML dashboards (inline CSS/JS, no build step, no CDN
            dependency required to read them) + markdown summaries + CSV exports
RECOMMEND   ranked, costed, actionable optimisations with rationale, evidence
            links, and effort/impact estimate → reports/ or proposed/
```

Flagship pipeline to prove the concept end to end: **monthly bank statement → categorised transaction ledger → income/expense/cashflow dashboard → budget variance → optimisation report** (duplicate subscriptions, fee leakage, escalation creep, tax-deductible items missed, savings rate vs target). Must handle multiple accounts across multiple banks and multiple entities, and correctly separate personal from business while still rolling up to one consolidated view.

Second flagship, to prove the cross-domain claim: **medical aid plan + gap cover + employee benefits → consolidated health cover map** showing what's covered, by whom, at what annual cost, with the overlaps and the holes named.

## 8. Memory

Three tiers plus a consolidation ritual. `memory-keeper` owns all of it.

- **Short term** (`memory/short/`) — current session and rolling 7 days: what we're working on, recent decisions, transient context, unanswered questions.
- **Medium term** (`memory/medium/`) — rolling ~90 days: active projects, in-flight optimisations, recent life events, pending deadlines, things I said I'd do.
- **Long term** (`memory/long/`) — durable: my preferences and risk appetite, standing instructions, decision history with rationale, structural facts about my life, lessons learned, patterns observed ("he never reads reports longer than two pages", "he prefers Afrikaans-language service providers", "he rejects anything with a lock-in period").

Nightly `/consolidate` run: review the day's journal, chats, agent state and proposals; extract durable facts and promote them; demote or expire stale medium-term items; deduplicate; detect contradictions and surface them rather than silently overwriting; compress verbosity into crisp statements; write an audit line for every promotion, demotion and expiry so memory is never a black box. Memory files must be human-readable and hand-editable — I will edit them.

Long-term memory feeds back into `CLAUDE.md` via an explicitly delimited, machine-maintained section, so every future session starts informed.

## 9. Commands, skills, hooks

**Slash commands** (`.claude/commands/`) — at minimum:

| Command | Purpose |
|---|---|
| `/lifeos-init` | Interview me, scaffold vault, write profile, select packs, set cadences |
| `/boot` | Orient: profile + state + open loops + calendar position + what's next |
| `/heartbeat` | Run the loop in §4 once. Idempotent. Safe to run hourly forever. |
| `/consolidate` | Nightly memory consolidation + journal roll-up + tomorrow's brief |
| `/ingest` | Force an inbox sweep and file everything |
| `/review <domain>` | Deep review of one domain, on demand |
| `/dashboard [domain]` | Regenerate dashboards |
| `/optimise [domain]` | Produce ranked optimisation proposals |
| `/readiness` | Life File readiness score + shortest path to improve it |
| `/ask <question>` | Ad-hoc question answered across every domain, with citations to my own documents |
| `/life-event <desc>` | Declare a life event (marriage, birth, death, job change, purchase, business sale) → cascade impact analysis across every domain |
| `/what-if <scenario>` | Scenario modelling (retire at 60, emigrate, sell the business, disability at 45, death tomorrow) |
| `/deadlines` | Everything due, sorted, with lead times |
| `/add-domain <name>` | `meta-architect` scaffolds a new domain from the charter template |
| `/status` | Health of every agent, staleness of every ledger, queue depth |
| `/audit` | Prove every derived artefact traces back to a source document |

**Skills** (`.claude/skills/`) — document extraction (pdf, docx, xlsx, csv, images/OCR), statement parsing per SA bank format, transaction categorisation, policy-document comprehension, ledger read/write with schema validation, chart & dashboard rendering, web verification with mandatory redaction, SA tax computation, report writing in my preferred voice, agent scaffolding.

**Hooks** (`.claude/hooks/`) — `SessionStart` loads profile/state/memory digest; a `PreToolUse` guard blocks any web request containing PII patterns (SA ID numbers, account numbers, policy numbers, email addresses, names from the profile) and blocks writes to `documents/` originals; a `PostToolUse` audit appends every vault mutation to an append-only log; a pre-commit guard refuses any commit that would put vault content into the system repo.

## 10. Customisation & sharing

- `profile/profile.yaml` — persons, entities, jurisdiction, currency, fiscal year, risk appetite, communication preferences (length, tone, language), notification thresholds, cadence overrides, enabled domains.
- `packs/` — optional bundles that layer agents, ledgers, rulebooks and commands onto the core: **`trusts`**, `sme-owner`, `expat`, `phd-researcher`, `landlord`. A pack is just a directory obeying the same conventions — installing one is a merge, not a fork. My colleague should be able to clone the repo, run `/lifeos-init`, choose the `trusts` pack, and have a genuinely useful trust-administration assistant within an hour without touching anyone else's data.
- Domains and specialists are enable/disable by config. Removing a domain must not break the graph — it degrades to "not tracked" with an explicit note.
- Jurisdiction is a config axis. Ship SA rulebooks; structure them so a `.claude/rules/<jurisdiction>/` sibling could be added later.

## 11. Guardrails

- Every factual claim about my life traces to a source document with hash and page. No invented numbers, ever. Unknown is a valid, first-class answer and belongs in the gaps register.
- Every claim about tax law, product terms or limits carries an "as at" date and a source. Verify against the web when the cached rule is older than its stated refresh interval.
- Distinguish clearly between (a) what my documents say, (b) arithmetic derived from them, (c) suggestions, and (d) matters requiring a registered financial advisor, tax practitioner, attorney or the Master's Office. Never impersonate professional advice; do prepare me to have a much sharper conversation with the professional.
- Secrets: store *pointers*, never plaintext credentials. Passwords live in a password manager; LifeOS records which entry, not what it is.
- POPIA-aware: purpose limitation, minimality, and a documented erasure path for every category of personal information held — including derived artefacts.

## 12. Build plan

Deliver in phases. Stop after each for my review. Each phase must leave the repo working and demonstrable against `vault.example/`.

- **Phase 0 — Plan.** Architecture doc, agent catalogue with the full §6 taxonomy mapped to owners, ledger schemas, state and memory schemas, loop design, command list, ADRs for the big calls. No implementation. **Stop.**
- **Phase 1 — Skeleton & spine.** `CLAUDE.md`, settings, hooks, templates, `/lifeos-init`, `/boot`, `/status`, vault scaffolding, state and cursor model, journal. Orchestrator + librarian + memory-keeper + meta-architect. `/heartbeat` running end to end with zero domains — it must correctly report "nothing to do" and prove idempotency.
- **Phase 2 — Ingestion & readiness.** Document pipeline for all target formats, `documents/` filing, extraction with provenance, `agents/readiness/` and `/readiness` with a real score against `vault.example/`. This is the first phase with visible payoff.
- **Phase 3 — Financial flagship.** Banking, transactions, regular payments; statement parsing; categorisation; the full ingest→dashboard→optimise pipeline; net worth. Prove it on fake statements in `vault.example/`.
- **Phase 4 — Cover & wealth.** Insurance, medical aid & employee benefits (with the consolidated health cover map), investments & retirement, plus the cross-domain duplication/gap analysis that justifies the whole holistic premise.
- **Phase 5 — Tax & estate.** Tax agent with cached SARS rulebooks and deadline calendar; estate agent with duty/CGT/liquidity modelling and beneficiary-vs-will conflict detection; final wishes.
- **Phase 6 — Trusts pack.** Full depth per §6H, installable standalone.
- **Phase 7 — Intelligence & closure.** `/ask`, `/what-if`, `/life-event` cascades, quarterly and annual review workflows, `/consolidate` memory ritual, `/audit`, `/add-domain` self-scaffolding. Documentation for colleagues. Demonstrate the recursion: use `/add-domain` to create a domain that didn't exist at design time and show it participating in the next heartbeat unmodified.

## 13. Definition of done for the whole system

1. `/heartbeat` can run hourly, indefinitely, and always does the right next thing — including nothing, cheaply.
2. Dropping a PDF in `inbox/` and running `/heartbeat` results in a filed document, updated ledgers, refreshed dashboards, and a journal entry explaining what changed and why it matters.
3. Every leaf in §6 has a named owner, a schema, or a checklist entry. Run a coverage audit and show me the map.
4. A colleague can clone, init, choose a pack, and be productive without reading the source.
5. The system can extend itself: `/add-domain` produces a working agent that the loop picks up with no changes to the orchestrator.
6. Nothing personal has ever entered this repo's git history.

---

Now: read the brief back to me as a plan. Flag anything you think is wrong, over-engineered, or missing. Propose the concrete file tree and the agent catalogue. Then wait.
