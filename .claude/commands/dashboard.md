---
description: Regenerate the financial dashboard — self-contained HTML, no network needed to read it.
argument-hint: "[domain]"
allowed-tools: Bash, Read, Write, Glob
---

# /dashboard $ARGUMENTS

## Build it

!`.venv/bin/python -m lifeos.finance`

!`.venv/bin/python -m lifeos.recurring`

Then render:

```bash
VAULT="$(.venv/bin/python -m lifeos.vault)"; mkdir -p "$VAULT/reports"
.venv/bin/python -m lifeos.analyse > /tmp/lifeos-analysis.json
node tools/js/render-dashboard.mjs /tmp/lifeos-analysis.json > "$VAULT/reports/dashboard-$(date +%F).html"
```

`mkdir -p` is not optional: `reports/` is a derived directory and may not exist on a fresh vault or after a rebuild, and the redirect cannot create it.

## Report

Give the user the headline numbers in text — money in, money out, net, savings rate, and the personal/business split — then the path to the HTML file. Do not make them open a file to learn the top-line figure.

Flag, every time:

- **Uncategorised transactions.** Offer to work through them in batches; write answers back as `category_method: human` so the system learns from their decisions rather than its own guesses.
- **Unverified adapters.** Rows from these are below the confidence floor and are sitting in `$VAULT/proposed/low-confidence/`, not in the ledger. Say which bank, and that confirming them or adding a verified layout is what fixes it.
- **Reconciliation failures.** A statement whose running balance does not add up means a layout changed. That is a `kind:adapter` issue for `meta-architect` — describing the layout change, never the user's numbers.
- **Partial net worth.** While `assets`, `liabilities` and `holdings` are empty this is a **cash position, not a net worth**. Never present it as the latter.

## Rules

- The HTML must open correctly **with no network access** — inline CSS, inline SVG, no CDN, no build step. Verify with a quick grep for `http` if you changed the renderer.
- Regenerating is idempotent: same ledgers, same output.
- Transfers between the user's own accounts are excluded from both sides. If a figure looks low, that is usually why — say so rather than letting them wonder.
- Never compute a figure yourself in prose. If it is not in the analysis JSON, it does not go in the summary.
