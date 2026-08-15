---
description: Health of every agent, staleness of every ledger, queue depth, gaps, and phase progress.
allowed-tools: Bash, Read
---

# /status

!`.venv/bin/python -m lifeos.status`

Render that JSON as a short table for a human. Lead with anything wrong.

| Section | Report |
|---|---|
| Agents | health, last run, open loops, pending questions. **Name unhealthy agents first.** |
| Ledgers | record count, age, and whether past its freshness threshold |
| Queue | depth, in progress, failed, parked |
| Gaps | open, blocking, and the count by consequence |
| Rulebooks | any past their refresh interval — these must be re-verified before reliance |
| Awaiting you | items in `$VAULT/proposed/` |
| GitHub | open system issues, unfiled drafts, milestone progress per phase, last sync and whether it was reachable |
| Runs | total, quiet ratio, last outcome |

## Rules

- Read-only. `/status` never fixes anything; it reports.
- A high quiet ratio is **healthy** — it means the loop is cheap when there is nothing to do.
- `parked` items are not failures to hide: name them and say what would revive them.
- If GitHub was unreachable, say the mirror is a cache and give its age. That is a degraded read, not an error.
