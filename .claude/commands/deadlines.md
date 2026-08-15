---
description: Everything due, sorted, with lead times, owners and what each needs.
argument-hint: "[--horizon DAYS]"
allowed-tools: Bash, Read, Grep, Glob
---

# /deadlines $ARGUMENTS

!`.venv/bin/python -m lifeos.tax --markdown`

## Report

1. **Inside its lead window** — anything that needs work started *now*, with days remaining. Overdue items first, marked clearly.
2. **The next twelve months**, dated, with the taxpayer each belongs to.
3. **What each one needs** — the documents that must be on hand. If they are missing, that is a gap, and `/readiness` tracks it.

Say **why** an obligation applies to a taxpayer. "Provisional tax, because rental income was seen in the ledger" is actionable; a bare "IRP6" invites the reply "that isn't mine".

## Rules

- **Dates come from the rulebook, never from memory.** `.claude/rules/za/deadlines.yaml` carries them with an "as at" date.
- **Say when the rulebook is stale.** Filing-season opening dates are announced annually and are the part most likely to have moved. If the rules are past their refresh interval, say so and offer to re-verify against SARS — a public date lookup is exactly the outbound request the redaction guard permits.
- **Lead times are the point.** A return due in 30 days with documents not yet gathered is already late. Report the lead window, not just the due date.
- **Never file, submit or pay anything.** Prepare, remind, and list what is needed.
- If a deadline has passed, say so plainly and note that penalties and interest generally run from the due date — then point to a registered tax practitioner.
