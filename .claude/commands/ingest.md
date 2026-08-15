---
description: Force an inbox sweep — classify, file immutably, index and route every document.
argument-hint: "[--dry-run] [--path FILE]"
allowed-tools: Bash, Read, Write, Grep, Glob, Task
---

# /ingest $ARGUMENTS

## Run it

!`.venv/bin/python -m lifeos.ingest`

Use `--dry-run` first when the user is unsure — it classifies and reports without filing anything.

## Report

Group by outcome, and lead with what needs the human:

| Status | Means |
|---|---|
| `filed` | classified, copied, hash-verified, indexed, routed |
| `duplicate` | already in the index by content hash — skipped, not re-filed |
| `unclassified` | no rule matched confidently. **A question, not a failure.** |
| `unreadable` | extraction produced nothing |
| `unsupported` | no extractor for that file type |
| `copy_failed` | the filed copy did not match the source hash — serious |

For anything in the bottom four rows, say **which file and why**, and what would resolve it. These stay in `$VAULT/inbox/` with a gap record; the system never deletes an inbox file.

## Then route

Each filed document names the domain that owns it. Return `dispatch_requests[]` for those domains so the orchestrator can pick them up in the next wave — do not analyse the contents yourself.

Once documents are filed, `/readiness` will have changed. Say so.

## Rules

- **Originals are immutable.** Filed copies are chmod 444 and a hook blocks writes to `documents/`. Never modify one, not even to fix a filename.
- **Idempotent.** Identity is the content hash, so the same document under a different name is still a duplicate. Running `/ingest` twice must file nothing the second time.
- **Never guess a classification.** The classifier refuses when two types are within its margin; that refusal is correct and must be surfaced, not overridden.
- A document type LifeOS has never seen is a signal for `meta-architect`, and possibly a new rule in `.claude/rules/document-types.yaml`. Say so rather than forcing it into an existing type.
