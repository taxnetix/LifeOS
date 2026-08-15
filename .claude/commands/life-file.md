---
description: Generate the Life File — a document for your family covering everything they need when you die.
argument-hint: "[--tier 1|2|3] [--person <ref>] [--html-only]"
allowed-tools: Bash, Read, Write, Grep, Glob, Task
---

# /life-file $ARGUMENTS

Produce the document you hand to your family. Design and rationale: [ADR-0018](../../docs/adr/0018-life-file-document.md).

**Default tier is 1.** Tier 3 must be asked for explicitly, every time.

## Tiers

| Tier | For | Identifiers |
|---|---|---|
| **1 — First 48 Hours** *(default)* | whoever finds it first | **none** |
| **2 — Executor Pack** | executor, spouse, attorney | **masked** to last 4 |
| **3 — Sealed Annexure** | the executor alone, on death | **unmasked** |

## Never print, at any tier

Passwords · PINs · safe combinations · alarm codes · seed phrases · private keys · 2FA secrets.

Print the **pointer**: *"1Password → Personal. Master password held by the executor."* (Phrase it as *held by*, never *is* — the schema treats `password is …` as an assignment and rejects it, deliberately.) A document carrying both the map and the keys is a burglary aid. If you find yourself about to print a secret, you have misread the ledger — `credential_pointer` is a location, never a value.

## Composition

Delegate to `readiness` (it owns the checklist and the score), which calls `analyst` for the liquidity figures and `visualiser` to render.

### Page 1 — always, in this order

1. **Cover** — whose Life File, generation date, readiness score, tier, and the words **"Supersedes all earlier copies."**
2. **In the first 48 hours** — who to call, in order, with numbers.
3. **What your family will NOT find** — the top gaps by consequence. Unsigned will, missing title deed, unrecorded suretyship, beneficiary nomination conflicting with the will.

That third section is the point of the document. Do not bury it, do not soften it, and do not omit it because it is uncomfortable. A Life File that shows only what is known is a comfortable lie.

### Then, by tier

**Tier 1** — funeral and burial wishes per person · where the will is and who the executor and custodian are · the 30-day liquidity plan as a real number with where it comes from · where the originals are kept · who else holds copies.

**Tier 2** — adds: policies to claim, with insurer and broker · bank accounts · investments · assets and where the title deeds are · liabilities **including suretyships** · employee benefits · medical aid · trusts, trustees and the Master's reference · digital estate as pointers · leases · court matters and maintenance obligations · people to notify.

**Tier 3** — as tier 2, with identifiers unmasked. Watermark every page **SEALED — CONTAINS FULL IDENTIFIERS**. Record the generation in `$VAULT/state/audit.jsonl`.

## Rules that are not negotiable

- **Every figure carries its "as at" date.** An undated Life File is worse than none, because it will be trusted years after it stopped being true.
- **No invented numbers.** A value you cannot trace to a document is a gap, and gaps belong in the gaps section. Never a placeholder, never an estimate presented as a fact.
- **Mark estimates as estimates.** A municipal valuation is not a market value.
- **Say what is not tracked.** A disabled domain is listed as "not tracked", never silently absent.
- Write to `$VAULT/reports/life-file/<date>-tier<N>.{html,pdf}`.

## Rendering

```bash
.venv/bin/python -m lifeos.life_file --tier <N>     # phase 2
```

HTML is the source and is always written; the PDF is derived by `weasyprint`. If `weasyprint` cannot load its system libraries, **still emit the HTML** and tell the user to open it and print to PDF. The deliverable degrades; it never fails.

## Hand it over properly

Close by telling the user, plainly:

- **where each tier should live** — tier 1 with the will and with the executor; tier 2 with the executor and the attorney; tier 3 sealed, one copy, with the executor only
- **the top three gaps** and roughly what each would take to close
- **when to regenerate** — quarterly, and after any `/life-event`
- that this is a snapshot, and every earlier copy is now out of date

## Phase note

Until Phase 2 lands `readiness` and the renderer, `/life-file` still runs: it produces the cover, the readiness score, and the gaps section from whatever is in the vault. On a nearly-empty vault that is almost entirely gaps — **which is the honest and useful answer**, and the fastest way to see what your family would actually face today.
