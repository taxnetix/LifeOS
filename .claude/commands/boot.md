---
description: Orient — profile, state, open loops, calendar position, and what's next.
allowed-tools: Bash, Read, Grep, Glob
---

# /boot

Orient at the start of a working session. **Read-only** apart from one journal line.

## Gather

!`.venv/bin/python -m lifeos.status`

!`.venv/bin/python -m lifeos.sense`

Also read, if they exist:
- `$VAULT/profile/profile.yaml` — who, entities, enabled domains, preferences
- `$VAULT/memory/short/` and `$VAULT/memory/medium/` — what we were in the middle of
- the last few entries in `$VAULT/journal/`

## Report — one page maximum

1. **Where you stand** — enabled domains, ledger freshness, readiness score if it exists.
2. **Calendar position** — the SA fiscal anchors now inside their lead window, with days remaining.
3. **Open loops** — what was in flight when we last stopped.
4. **What's next** — the top few queue items.
5. **What I need from you** — proposals, open questions, missing documents. If empty, say so.

## Rules

- **Never mutate a ledger.** `/boot` orients; `/heartbeat` acts.
- If the system is in a broken state — a failed prior run, a corrupt cursor, an unreadable ledger — **say so and propose a repair. Do not perform one.**
- If there is no vault, say exactly that and point to `/lifeos-init`. Nothing else.
- Obey `profile.communication.report_length`. Default short: a page is a ceiling, not a target.
