---
description: Life File readiness score, the gaps that matter, and the shortest path to improving it.
argument-hint: "[--person <ref>] [--category <name>]"
allowed-tools: Bash, Read, Grep, Glob, Task
---

# /readiness $ARGUMENTS

!`.venv/bin/python -m lifeos.readiness --markdown`

## Report, in this order

1. **The score**, and whether it moved since last time.
2. **Catastrophic gaps** — named, with the consequence spelled out. Not softened.
3. **The shortest path** — the top few actions by score-delta ÷ effort, each with what it costs and what it recovers.
4. **By category**, briefly.
5. **Not tracked** — requirements in disabled domains, listed so nothing looks silently complete.

## What the statuses mean

- `present` — filed and current
- `expired` — filed but past its freshness window
- `absent` — nothing on file
- `unattributed` — the right *kind* of document exists but LifeOS cannot yet prove whose it is. Half credit. Say this plainly; it is honest bookkeeping, and it resolves as the identity domain deepens.

## Rules

- **The score is weighted by consequence, not by count.** If asked why it is low, explain which catastrophic items are missing — not how many items there are.
- **Never round up.** A 23% readiness is a useful, uncomfortable fact. Making it sound better is the one thing that would make this command worthless.
- The right next action is usually not the biggest gap. It is the catastrophic one that takes ten minutes — say so.
- If the user wants the document itself, point them at `/life-file`.
