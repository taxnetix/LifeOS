---
description: Ranked, costed optimisation proposals with evidence. Proposals only — nothing is actioned.
argument-hint: "[domain]"
allowed-tools: Bash, Read, Write, Glob
---

# /optimise $ARGUMENTS

!`.venv/bin/python -m lifeos.optimise --markdown --write`

## Report

Lead with the total annual amount identified, then the top findings in order. For each: what it is, what it is worth per year, what it costs to act, and how confident the system is.

Ranking is annual rand recovered ÷ effort — so the best next action is often not the biggest number. Say that explicitly when it applies.

## The findings that matter most

| Kind | Why it earns its place |
|---|---|
| `duplicate_subscription` | The same service billed personally *and* through the business is invisible on either statement alone. This is the finding that justifies holding one consolidated ledger. |
| `escalation_creep` | A 6% annual escalation is invisible month to month and compounds. Almost never renegotiated, because nobody notices it. |
| `fee_leakage` | Individually trivial, annually significant, and precisely why nobody looks. |
| `unknown_cancellation_route` | A recurring cost nobody can work out how to stop. The thing an executor struggles with most. |
| `tax_review` | Spending a practitioner would want to see. |

## Rules — these are not negotiable

- **Proposals only.** Never cancel a subscription, move money, contact a provider, or draft a cancellation email that could be sent. Findings go to `reports/` and `proposed/` and wait.
- **Never claim something is tax-deductible.** `tax_review` findings flag what is worth *asking about*. The determination belongs to a registered tax practitioner, and say so.
- **Every finding carries its evidence.** If it has no record IDs behind it, it is an opinion — do not present it as a finding.
- **Do not pad the list.** A short list of real findings is worth more than a long one padded with generic advice. If there are only three, say three.
- Estimates are marked as estimates. Fee leakage assumes roughly half is avoidable; say so rather than presenting the number as recoverable.
