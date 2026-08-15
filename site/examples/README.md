# Example Life Files

Two real outputs of the `/life-file` command, built from `vault.example/`, the
fake vault the test suite runs against. Nobody in these documents exists. "A
Sample" is not a person, Northbank is not a bank, and the R2.18m home loan is
made up.

| File | Tier | Who it's for | Numbers shown |
|---|---|---|---|
| [`life-file-tier1-first-48-hours.pdf`](life-file-tier1-first-48-hours.pdf) | 1 | Whoever finds it | none at all |
| [`life-file-tier2-executor-pack.pdf`](life-file-tier2-executor-pack.pdf) | 2 | Executor, attorney | last 4 digits only |

Tier 3, the Sealed Annexure, is not published here. It shows numbers in full,
has to be asked for by name every time, and every copy made gets logged.

## What to look at

**Section 2, "What my family will *not* find".** It sits on the second page
rather than tucked away in an appendix, and it runs longer than any other
section: four serious gaps, a readiness score of 30.1%, and a ranked list of
what to fix first with the score each fix wins back.

A Life File that printed only the sorted parts would read as complete, and a
family acting on it would hit the holes at the worst possible time. That is why
the gaps carry the same weight as the findings.

No password, PIN, safe code or seed phrase appears at any tier. LifeOS records
where a credential is kept, and that is what gets printed. A document holding
both the map and the keys would just be a burglary aid.

## Making them again

```bash
LIFEOS_VAULT="$PWD/vault.example" python -m lifeos.life_file --tier 2
```

Output lands in `$VAULT/reports/life-file/`. The HTML is always written and the
PDF comes from it. If WeasyPrint cannot load its system libraries you still get
the HTML, with instructions for printing it. On macOS the PDF step needs
`brew install pango` and `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`.
