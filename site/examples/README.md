# Example Life Files

Two real, unedited outputs of `/life-file`, generated from `vault.example/` — the
fully-populated **fake** vault every test in this repo runs against. Nobody in
these documents exists. "A Sample" is not a person, Northbank is not a bank, and
the R2.18m home loan is a fixture.

| File | Tier | Audience | Identifiers |
|---|---|---|---|
| [`life-file-tier1-first-48-hours.pdf`](life-file-tier1-first-48-hours.pdf) | 1 | Whoever finds it | none at all |
| [`life-file-tier2-executor-pack.pdf`](life-file-tier2-executor-pack.pdf) | 2 | Executor, attorney | masked to last 4 |

Tier 3 — the Sealed Annexure, which unmasks — is deliberately **not** published.
It is the tier that has to be asked for explicitly, every time, and shipping a
specimen of it would undercut the point of it being sealed.

## What to look at

**Section 2, "What my family will *not* find".** It is the second page of the
document rather than an appendix, and on this fixture it is the longest section
in the pack — four catastrophic gaps, a 30.1% readiness score, and a ranked list
of what to fix first with the score each fix recovers.

That is the design working, not the fixture being unusually bad. A Life File
that printed only what was known would read as complete, and a family acting on
it would discover the holes at the worst possible moment. So the gaps are
rendered with the same weight as the findings.

Note also that no password, PIN, safe code or seed phrase appears anywhere at
any tier. LifeOS stores a *pointer* to where a credential lives, and the pointer
is what gets printed. A document holding both the map and the keys is a burglary
aid.

## Regenerating these

```bash
LIFEOS_VAULT="$PWD/vault.example" python -m lifeos.life_file --tier 2
```

Output lands in `$VAULT/reports/life-file/`. HTML is always written; the PDF is
derived from it, and if WeasyPrint cannot load its system libraries the HTML
still lands with instructions to print it — the deliverable degrades, it never
fails. On macOS the PDF path needs `brew install pango` and
`DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`.
