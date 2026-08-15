# ADR-0018 — The Life File is a tiered document, not a data dump

**Status** Accepted · Phase 0 design, Phase 2 implementation

## Context

The user asked for a command that produces **a PDF to hand to family — a copy of everything they need when he dies.**

This is the artefact the whole system has been pointing at. The `readiness` agent already scores the Life File checklist; this renders it. It is also the moment the system stops being a personal tool and becomes something a grieving spouse opens at the worst possible time, so it has to be readable by someone who is not technical, not calm, and not the person who built it.

It is simultaneously **the single most dangerous object LifeOS can produce.** One document containing ID numbers, account numbers, policy numbers, the location of the safe, the digital executor, and the trust register is a complete identity-theft kit and a map of the estate. Left in a drawer, emailed to a sibling, or photographed, it discloses more in one act than every other part of the system combined. The vault at least sits behind full-disk encryption; a printed PDF sits on a kitchen table.

The naive implementation — dump every ledger into a PDF — maximises both value and harm at once.

## Decision

### 1. Three audience tiers, not one document

| Tier | For | Contains | Identifiers |
|---|---|---|---|
| **1 — First 48 Hours** | whoever finds it first | who to call, funeral and burial wishes, where the will is and who the executor is, the 30-day liquidity plan, where the originals are kept | **none** — names, roles and locations only |
| **2 — Executor Pack** | executor, spouse, attorney | everything in tier 1, plus policies to claim, accounts, assets, liabilities, trusts, employee benefits, the digital estate, obligations, court matters | **masked** — last 4 digits only |
| **3 — Sealed Annexure** | the executor alone, on death | full identifiers needed to actually administer the estate | **unmasked** |

Tier 1 is the one meant to be findable. Tier 3 is generated **only** on explicit request, is watermarked as sealed, and its generation is recorded in the audit log.

The tiering is the entire safety design: the copy most likely to be lying around is the one that discloses almost nothing, and the copy that discloses everything is the one nobody has a reason to leave out.

### 2. Never in any tier

Passwords, PINs, safe combinations, alarm codes, seed phrases, private keys, 2FA secrets. LifeOS stores **pointers**, and the Life File prints the pointer: *"1Password → Personal. Master password is with the executor."* A document that hands over both the map and the keys is a burglary aid.

### 3. Gaps are a headline section, not an omission

The most valuable page is **"What your family will NOT find"** — the unsigned will, the missing title deed, the suretyship nobody knew about, the beneficiary nomination that contradicts the will.

A Life File that only shows what is known is a comfortable lie. Its whole job is to make the holes visible while there is still time to fill them, which is why the readiness score and the top gaps sit on page one rather than in an appendix.

### 4. Provenance and staleness are on the page

Every figure carries its "as at" date. The cover carries the generation date, the readiness score, and the words **"supersedes all earlier copies"**. A Life File is a snapshot of a moving target; an undated one is worse than none because it will be trusted years after it stopped being true.

Regeneration is expected — quarterly, and on every `/life-event`.

### 5. HTML is the source, PDF is derived

`visualiser` renders a self-contained HTML file (inline CSS, no CDN, no build step); `weasyprint` renders that to PDF. If `weasyprint` cannot load, `/life-file` still emits the HTML and says to print it from a browser. The deliverable degrades; it never fails.

Verified on this machine: `weasyprint` 65.1 works with pango 1.57 and cairo 1.18, given `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib` — set in `.claude/settings.json` and in the wrapper scripts.

### 6. Ownership

`readiness` composes it (it already owns the checklist and the score), `analyst` computes the liquidity figures, `visualiser` renders. No new agent.

## Consequences

- The system's value becomes legible on day one: even a nearly-empty vault produces a Life File whose gap section is immediately, uncomfortably useful.
- The dangerous artefact is the one the user must deliberately ask for, and the safe one is the default.
- Distribution guidance ships with the document rather than being left to intuition — tier 1 with the will and with the executor, tier 2 with the executor and the attorney, tier 3 sealed.
- The cost is three renders instead of one, and a masking layer that must be tested. Both are cheap next to the failure mode.
- Tier 3 generation is auditable, so it is always answerable who produced an unmasked copy and when.
- The Life File will sometimes contradict the ledgers, because it is a snapshot. The date on the cover is what resolves that, and it is why "supersedes all earlier copies" is printed rather than implied.

## Alternatives considered

**One complete document** — simplest, and it makes the most-copied artefact the most dangerous one. Rejected.

**Redact everything, always** — safe, and useless: an executor genuinely needs the policy number to lodge the claim. Tier 3 exists for exactly that need.

**Encrypt the PDF** — considered and rejected as the primary control: password-protected PDFs are routinely defeated, the password ends up written on the envelope, and it fails the "readable by a grieving spouse" test. Tiering addresses the real risk; encryption may still be offered for tier 3 as a secondary measure.

**Generate it only when the vault is complete** — would delay the most useful output indefinitely. The gaps *are* the output.
