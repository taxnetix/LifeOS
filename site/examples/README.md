# Example Life Files

Two outputs of `/life-file`, generated from `vault.example/` — the fully-populated
fake vault the test suite runs against. Nobody in these documents exists. "A
Sample" is not a person, Northbank is not a bank, and the R2.18m home loan is
invented.

| File | Tier | Audience | Identifiers |
|---|---|---|---|
| [`life-file-tier1-first-48-hours.pdf`](life-file-tier1-first-48-hours.pdf) | 1 | Whoever finds it | none at all |
| [`life-file-tier2-executor-pack.pdf`](life-file-tier2-executor-pack.pdf) | 2 | Executor, attorney | masked to last 4 |

Tier 3, the Sealed Annexure, is not included here. It shows identifiers in full,
has to be requested explicitly each time it is generated, and every generation
is written to the audit log.

## What these show

**Section 2, "What my family will *not* find".** It sits on the second page
rather than in an appendix, and here it runs longer than any other section —
four catastrophic gaps, a 30.1% readiness score, and a ranked list of what to
fix first with the score each fix recovers.

A Life File that printed only what was known would read as complete, and a
family acting on it would find the holes at the worst possible moment. The gaps
carry the same weight as the findings for that reason.

No password, PIN, safe code or seed phrase appears at any tier. LifeOS stores a
*pointer* to where a credential lives, and the pointer is what gets printed. A
document holding both the map and the keys is a burglary aid.

## Regenerating these

```bash
LIFEOS_VAULT="$PWD/vault.example" python -m lifeos.life_file --tier 2
```

Output lands in `$VAULT/reports/life-file/`. HTML is always written and the PDF
is derived from it; if WeasyPrint cannot load its system libraries the HTML
still lands with instructions to print it. On macOS the PDF path needs
`brew install pango` and `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`.
