---
description: Declare a life event and cascade its impact across every domain.
argument-hint: "<description>  e.g. married | child born | job change | bought a house | business sold | death in family"
allowed-tools: Bash, Read, Write, Grep, Glob, Task
---

# /life-event $ARGUMENTS

Record the event, then cascade. Delegate to `orchestrator` — this is exactly the cross-domain integration the loop exists for.

## Cascade

For the declared event, work out which domains are affected and queue the work. Not a checklist to recite — a genuine trace through the graph:

| Event | Touches |
|---|---|
| **Marriage** | matrimonial regime (what is even in the estate) · will · beneficiary nominations · medical aid dependants · tax status · short-term insurance |
| **Child born** | dependants · medical aid · guardianship in the will · education provision · beneficiary nominations · trust beneficiaries |
| **Job change** | **all employer cover ends** — group life, disability, income protection, funeral · provident fund transfer · income protection stacking recalculated · salary-based deduction headroom |
| **Bought property** | asset and bond ledgers · title deed location · estate duty and CGT base cost · short-term insurance · bond life cover and its cession |
| **Business sold** | CGT event · provisional tax · net worth · buy-and-sell cover now moot · trust loan accounts |
| **Death in family** | beneficiary of their estate? · inherited assets and their base cost · own will now stale · dependants changed |
| **Divorce** | regime and accrual · will (a nomination does NOT lapse automatically) · beneficiary nominations · maintenance obligations that survive death |

## The one to say out loud

**A job change ends employer cover on the day employment ends.** Group life, disability and income protection all stop, and re-insuring later is priced at the age and health you are *then*. Anyone who has been treating employer cover as permanent has a gap the moment they resign — and the cover map has probably been saying so already.

**Divorce does not automatically revoke a beneficiary nomination.** An ex-spouse can remain the nominee for years. Raise it every time.

## Then

1. Record the event in the journal with its date.
2. Queue the follow-up work — do not try to do all of it now. INTEGRATE stays bounded on purpose.
3. Re-run `/readiness`, and `/review cover` if cover was touched.
4. Say what changed, and what now needs a professional.

## Rules

- Declaring the same event twice is one record and one cascade.
- The cascade produces **work items and proposals**, never automatic changes to anyone's affairs.
- Some cascades are emotionally heavy. Be brief, concrete and kind; do not editorialise, and do not bury the actionable part.
