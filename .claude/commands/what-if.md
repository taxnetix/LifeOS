---
description: Model a scenario across every domain, with assumptions stated and sensitivities named.
argument-hint: "<scenario>  e.g. retire at 60 | emigrate | sell the business | disability at 45 | death tomorrow"
allowed-tools: Bash, Read, Grep, Glob, Task, Write
---

# /what-if $ARGUMENTS

Model a scenario from the ledgers. Write to `$VAULT/reports/scenarios/`.

## Start from what is already computed

| Scenario | Start here |
|---|---|
| death tomorrow | `python -m lifeos.estate --markdown` — duty, CGT, fees, and the 30-day liquidity gap |
| disability / cannot work | `python -m lifeos.covermap --markdown` — income protection, and whether it stacks |
| retire at 60 | `python -m lifeos.investments --markdown` — holdings and fee drag |
| sell the business | `python -m lifeos.analyse` and the CGT rulebook |
| emigrate | tax residency, `s10(1)(o)(ii)`, offshore holdings, FX exposure |

## Structure

1. **The question, restated** — precisely, because "retire at 60" hides a dozen choices.
2. **What the ledgers say today** — the starting position, cited.
3. **Assumptions, listed explicitly** — every one. Growth rate, inflation, life expectancy, whether the spouse survives.
4. **The result.**
5. **Sensitivity on the two or three assumptions that actually move it.** A model with fifteen assumptions and no sensitivity is a number with false precision.

## Rules

- **Assumptions are the output, not a footnote.** A reader who disagrees with one must be able to see it and say so.
- **Never present a projection as a plan.** Say which figures are modelled and which are read from documents.
- Every rate and limit comes from `.claude/rules/` with its "as at" date. If a rulebook is stale, the scenario inherits that — say so at the top, not the bottom.
- Death, disability and emigration scenarios all end in the same place: **a registered financial advisor, and for anything structural, an attorney.** Say so without hedging the analysis itself.
- Deterministic given the same inputs. Re-running must produce the same answer.
