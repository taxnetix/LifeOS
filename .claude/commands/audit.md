---
description: Prove every derived artefact traces back to a source document.
argument-hint: "[--quick] [--trace <record-id>]"
allowed-tools: Bash, Read, Grep, Glob
---

# /audit $ARGUMENTS

!`.venv/bin/python -m lifeos.audit --markdown`

Seven checks. **It exits non-zero on any failure**, so it can gate a commit or a scheduled run.

| Check | Proves |
|---|---|
| provenance | every record names a document, a locator and a confidence |
| orphans | every cited document exists — no figure traces to nothing |
| integrity | every filed original still hashes to what was indexed |
| coverage | every taxonomy leaf has an owner and a real schema |
| one_writer | exactly one agent writes each ledger |
| no_absolute_paths | the system repo hardcodes no path |
| schema | every record validates against its ledger schema |

## Tracing one figure

```bash
.venv/bin/python -m lifeos.audit --trace <record-id-prefix>
```

Walks a single record back to the page of the document it came from. Use this whenever the user asks "where did that number come from" — the answer should be a file and a locator, never a recollection.

## Rules

- **Report failures in full.** An audit that passes by being lenient is worse than no audit: it manufactures confidence. Never soften a failure or describe it as a warning.
- A record whose `doc_hash` is `human` or `inferred` is legitimately not from a document — say which it is, because inferred figures are rendered differently for a reason.
- An **integrity** failure is serious: a filed original no longer matches its hash means either corruption or an edit that slipped past the immutability hook. Stop and tell the user before doing anything else.
- If coverage fails, the fix is usually `meta-architect` updating the map — not deleting the row.
