---
description: Deep review of one domain — current state, changes, gaps, risks, ranked recommendations.
argument-hint: "<domain>  e.g. insurance | living | investments | finance | cover"
allowed-tools: Bash, Read, Grep, Glob, Task, Write
---

# /review $ARGUMENTS

Deep review of a single domain. Delegate to the owning agent (see `docs/agent-catalogue.md`); do not analyse another domain's ledgers yourself.

## The one to run first

**`/review cover`** produces the consolidated health and risk map — the report that answers questions no single document can:

!`.venv/bin/python -m lifeos.covermap --markdown --write`

It reads the medical scheme, the gap policy, employer benefits and personal policies together, and names what is covered, by whom, at what annual cost, and where the holes are.

## Other domains

| Domain | Run |
|---|---|
| `insurance` | `python -m lifeos.cover` then `python -m lifeos.covermap --markdown` |
| `living` | `python -m lifeos.cover` — scheme, gap cover, employer benefits |
| `investments` | `python -m lifeos.investments --markdown` — holdings, fee drag |
| `finance` | see `/dashboard` and `/optimise` |
| `readiness` | see `/readiness` |

## Report

1. **Where it stands** — the headline numbers.
2. **What changed** since the last review.
3. **Gaps** — what is missing, and what it would cost to be wrong about it.
4. **Risks** — including the uncomfortable ones. A review that only says reassuring things is not a review.
5. **Ranked recommendations** — costed, with effort.

## Rules that hold for every domain

- **Never recommend cancelling cover outright.** Model it, cost it, name the trade-off, and say who must decide. Cancelling income protection because it looks duplicated can leave someone uninsurable.
- **Employer-provided cover ends with employment.** Say so wherever it is counted.
- **Ceded cover does not reach the family.** Say so wherever it is totalled.
- **Every industry convention or tax limit carries its "as at" date and source.** If the cached rule is stale, say when it was last verified and re-verify before relying on it.
- **Distinguish the four things**: what the documents say · arithmetic from them · suggestions · matters needing a registered financial advisor, tax practitioner or attorney.
- Findings are proposals. Nothing is actioned.
