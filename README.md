# LifeOS

A personal life-management system implemented **entirely as a Claude Code agentic system**. Not a web app. Not a backend. The repository is the product; Claude Code is the runtime; files on disk are the state.

It ingests real documents — bank statements, policy schedules, medical aid plans, tax certificates, wills, trust deeds, payslips — turns them into structured ledgers, analyses them across domains, produces dashboards and optimisation reports, remembers what it learns, and knows what to do next every time it wakes up.

Built for South African tax, estate and trust law. Personal and business treated as one interconnected graph.

> **Status: all 7 phases complete.** Documents flow in with provenance; readiness is scored; the Life File renders to PDF; statements become a categorised ledger, a dashboard and ranked findings; and the health-and-risk cover map reads the medical scheme, gap policy, employer benefits and personal policies together to name the overlaps and the holes. Tax deadlines run off dated SARS rulebooks that report their own staleness, and the estate model answers the question families actually hit: not whether the estate is solvent, but whether anyone can reach cash in the first thirty days. `/audit` proves every figure traces to a page of a real document, and `/add-domain` grows a domain the loop picks up with no changes to the orchestrator. See [the roadmap](#roadmap).

## The idea in one paragraph

Most personal-finance tools ask you to enter data. LifeOS asks you to **drop a document in a folder**. Everything else — filing it immutably, extracting it with provenance, normalising it into a ledger, noticing it contradicts something you told it last year, working out what that means for your estate liquidity — is the system's job. And it does that job on a loop that is safe to run hourly, forever, because when nothing has changed it costs almost nothing and says so.

## Quick start

```bash
git clone <this repo> && cd life-os
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt
npm install
bash tools/scripts/install-hooks.sh      # the vault leak guard. Do this.
```

Then, in Claude Code:

```
/lifeos-init      # interview, scaffold your vault, pick domains and packs
/boot             # orient
```

Drop a document in `vault/inbox/` and run `/heartbeat`.

## The two halves

```
life-os/     SYSTEM   this repo. Shareable, MIT, zero personal data.
vault/       VAULT    your real life. Git-ignored. Never leaves your machine.
```

`$LIFEOS_VAULT` overrides the default location. Every agent resolves the vault through one resolver; nothing hardcodes a path.

## Commands

| | |
|---|---|
| `/lifeos-init` | Interview, scaffold the vault, select packs |
| `/boot` | Orient: where you stand, what's next, what's needed from you |
| `/heartbeat` | One pass of the loop. Idempotent. Safe hourly, forever |
| `/status` · `/selftest` | System health · the full test suite and structural invariants |
| `/ingest` | Force an inbox sweep |
| `/readiness` | Life File score, and the shortest path to improving it |
| **`/life-file`** | **The document you hand your family when you die** |
| `/dashboard` · `/optimise` | Cashflow dashboard · ranked, costed findings |
| `/review cover` | **The consolidated health and risk map** — what no single document says |
| `/review <domain>` | Deep review of one domain |
| `/deadlines` | Everything due, with lead times and why it applies to you |
| `/ask` · `/what-if` · `/life-event` | Cross-domain Q&A with citations · scenarios · cascades |
| `/trust-review` | s7C exposure, trustee independence, compliance, separation |
| `/install-pack` | List, install or remove an optional domain pack |
| `/issues` | The system's own backlog on GitHub |
| `/consolidate` · `/audit` · `/add-domain` · `/forget` | Memory ritual · provenance proof · self-extension · POPIA erasure |

Full contracts: [docs/commands.md](docs/commands.md).

## What makes it different

**It runs on a loop, not on demand.** SENSE is a Python script, not a reasoning step, so an idle heartbeat is milliseconds plus one short turn. The system notices an elapsed cadence, an expiring policy, a stale rulebook — not just a new file.

**Every number traces to a page.** Each record carries its source document hash, its exact locator, the tool that extracted it and a confidence. Below the ledger's confidence floor a record does not enter the ledger at all — it becomes a question. `/audit` walks any figure in any report back to a page of a real document.

**Unknown is a first-class answer.** There is a gaps register. No placeholders, no plausible guesses, no zero meaning "we didn't look".

**Nothing personal leaves the machine.** A `PreToolUse` hook blocks any outbound call — web, `curl`, or `gh` — carrying an SA ID number, an account number, or a name from your profile. It is a mechanism, not a policy, so it holds even when an agent is wrong.

**It maintains itself.** Agents file GitHub issues about the *system* — a bank changed its statement layout, a tax table is past its refresh interval — never about your life. That boundary is enforced by the same hook.

**It never states a tax rate from memory.** Rates, thresholds and abatements live in dated rulebooks that carry a source and a `verified` flag. The ones shipped are marked unverified — written from memory, not checked against SARS — so every figure built on them arrives with that caveat attached. The system reports its own rulebooks as a year out of date, because they are.

**It sees what no single document says.** The medical scheme covers hospital, the gap policy covers the shortfall it leaves, the employer covers part of your income, and a personal policy covers a part that may not stack with it. Each document is silent about the others. `/review cover` reads them together and names the duplication, the cover that ends with your job, and the hole where day-to-day care falls between the two.

**It can grow itself.** `/add-domain` scaffolds a new domain from the charter template, and the next heartbeat picks it up with no changes to the orchestrator.

## The Life File

The artefact everything points at: **a document you can hand to your family**, in three tiers.

| Tier | For | Identifiers |
|---|---|---|
| First 48 Hours *(default)* | whoever finds it | none |
| Executor Pack | executor, spouse, attorney | masked |
| Sealed Annexure | the executor, on death | unmasked, explicit request only |

No passwords, PINs or safe codes at any tier — LifeOS prints the *pointer*, never the secret. Its headline section is **"What your family will NOT find"**: the unsigned will, the missing title deed, the suretyship nobody knew about. A Life File showing only what is known would be a comfortable lie. [ADR-0018](docs/adr/0018-life-file-document.md).

## Packs

Optional domain bundles that layer onto the core by **merge, not fork** — one codebase, many configurations, so a core fix reaches every installation.

```
/install-pack install trusts
```

`trusts` ships first: the trust register, trustees and their independence, resolutions, beneficiaries by class and vesting, loan accounts and **s7C exposure**, distributions and their tax attribution, and the Master and SARS compliance calendar. A pack installs *capability, never data* — your colleague gets the machinery and none of your records. [ADR-0019](docs/adr/0019-packs-merge-not-fork.md).

## Roadmap

| Phase | | Status |
|---|---|---|
| 0 | Architecture, agent catalogue, schemas, ADRs | ✅ |
| 1 | Skeleton and spine — loop, hooks, vault, 4 system agents | ✅ |
| 2 | Ingestion, provenance, readiness, the Life File | ✅ |
| 3 | Financial flagship — statements → dashboard → optimisation | ✅ |
| 4 | Cover and wealth — insurance, medical, investments, gap analysis | ✅ |
| 5 | Tax and estate — SARS rulebooks, duty and liquidity modelling | ✅ |
| 6 | Trusts pack, installable standalone | ✅ |
| 7 | `/ask`, `/what-if`, cascades, memory ritual, self-extension | ✅ |

## Documentation

[docs/README.md](docs/README.md) is the reading order. Start with [architecture](docs/architecture.md) and [loop](docs/loop.md); the [18 ADRs](docs/adr/README.md) record every decision that would be expensive to reverse.

## Safety

Read [SECURITY.md](SECURITY.md) before putting real documents in a vault.

## Licence

MIT. See [LICENSE](LICENSE). The licence covers the system. Your vault is yours.
