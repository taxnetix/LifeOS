---
description: POPIA erasure for one subject, including derived artefacts. Destructive — double-gated.
argument-hint: "<subject-ref>"
allowed-tools: Bash, Read, Glob, AskUserQuestion
---

# /forget $ARGUMENTS

**The only destructive command in LifeOS.** Double-gated, deliberately.

## Step 1 — manifest, always first

!`.venv/bin/python -m lifeos.forget $ARGUMENTS`

Nothing is touched. Show the user exactly what would go: ledger records, filed documents, and **derived artefacts** — reports, dashboards, journal entries, all three memory tiers. Erasure that removes a document while its numbers survive in a dashboard is not erasure.

## Step 2 — confirm, then apply

Get an explicit yes. Then:

```bash
.venv/bin/python -m lifeos.forget <subject> --apply
```

Records are **tombstoned**, not rewritten — the fact that a record existed and was erased stays auditable; its content does not. Originals are **quarantined** to `$VAULT/proposed/erasure/`, not deleted.

## Step 3 — shredding is a separate decision

```bash
.venv/bin/python -m lifeos.forget <subject> --confirm-shred
```

Only after the user has seen what was quarantined. This is not reversible.

## Always report three things

1. **What was removed.**
2. **What was retained, and why** — tombstones stay because deleting them would destroy the audit trail that proves the erasure happened.
3. **What could NOT be removed**, plainly:
   - anything ever pushed to GitHub — notified, indexed, cached; deleting does not un-send
   - reports emailed, printed or copied out of the vault
   - the institution's own records, kept under its own retention rules
   - backups taken before the erasure

Honesty about the limits of erasure is part of the erasure. A report claiming completeness it cannot deliver is worse than one that names the gap.
