# South African rulebooks

Tax tables, thresholds, abatements and fee scales — **as data, with dates**.

## Why these are files and not code

Every one of these numbers changes, most of them annually at the February
Budget. A rate compiled into a function cannot carry its own provenance, cannot
be checked for staleness, and cannot tell a reader *when it was last true*.
See [ADR-0016](../../../docs/adr/0016-jurisdiction-as-config-axis.md).

## Every rulebook declares four things

```yaml
as_at: 2025-02-19          # the date the values were announced or took effect
tax_year: 2026             # SA year of assessment: 1 Mar 2025 – 28 Feb 2026
source: https://...        # where a human can check it
verified: false            # has a human or a web lookup confirmed it since?
refresh_interval: P1Y
```

## `verified: false` is the default, and it is doing real work

**These values were written from memory and have not been checked against
SARS.** They are believed correct for the tax year stated, and they may be
wrong. Nothing that computes with them is allowed to present a bare number:
`lifeos.rules` marks every result `requires_verification` and every report
carries the caveat.

That is not defensiveness for its own sake. A confident, wrong estate duty
figure is worse than no figure — it gets planned around, and the error only
surfaces at the moment the family can least absorb it.

## Flipping `verified` to true

Requires an actual check against the source URL, on a stated date, by a person
or by an agent's web lookup. Then set `verified: true` and `verified_on`. Do not
flip it because a calculation looked reasonable.

## Current staleness

Today's SA tax year is **2027** (1 Mar 2026 – 28 Feb 2027). These rulebooks
carry **2026** figures. They are therefore **a year out of date**, `/status`
reports them as stale, and SENSE raises `rule.expired`.

This is the machinery working, not a bug. The correct fix is to look up the
2026 Budget figures, update these files, and set `verified: true`.
