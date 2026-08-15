---
description: Run the full test suite plus the structural invariants that keep the system honest.
argument-hint: "[unit | structural | all]"
allowed-tools: Bash, Read, Grep, Glob
---

# /selftest $ARGUMENTS

Prove the system still holds its own rules. Run everything unless a suite is named.

## 1. Unit tests

!`.venv/bin/pytest tools/py/tests -q`

!`npm test --silent`

## 2. Lint

!`.venv/bin/ruff check tools/py`

## 3. Schemas compile

!`node tools/js/validate-schema.mjs --all`

## 4. Structural invariants

Run these and report each as PASS or FAIL:

**One writer per ledger** — parse the ownership table in `docs/agent-catalogue.md`; fail on any ledger with zero or two writers.

**Provenance, coverage, one-writer and absolute paths** — all four, plus schema validity and document integrity, are checked by one command:

```bash
.venv/bin/python -m lifeos.audit --markdown
```

It exits non-zero on any failure. Do not re-implement these checks inline here: an inline grep for a hardcoded path has to contain that path, which then trips the check it is testing.

**Redaction holds** — the guard must block a seeded fake SA ID in both a web query and a `gh issue create` body:
```bash
echo '{"tool_name":"WebSearch","tool_input":{"query":"tax for 8801015800086"}}' | .venv/bin/python .claude/hooks/pii-guard.py
echo '{"tool_name":"Bash","tool_input":{"command":"gh issue create -b \"account 4051234567890\""}}' | .venv/bin/python .claude/hooks/pii-guard.py
```
Both must return `permissionDecision: deny`. **A guard that fails open is a failed test**, not a warning.

**Originals immutable** — a write to `$VAULT/documents/<year>/...` must be denied.

**Leak guard installed** — `.git/hooks/pre-commit` exists and is executable. If not, say to run `bash tools/scripts/install-hooks.sh`.

**Heartbeat idempotency** — run SENSE twice against `vault.example/`; the reports must be identical apart from `run_id` and `now`.

## Report

A table of PASS/FAIL, failures first. Then one line: safe to proceed, or not.

Do not fix anything. `/selftest` reports; fixing is a separate, deliberate act.
