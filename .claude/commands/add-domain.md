---
description: Scaffold a new domain from the charter template. The next heartbeat picks it up unmodified.
argument-hint: "<name> [--label \"Human readable name\"]"
allowed-tools: Bash, Read, Write, Glob, Task
---

# /add-domain $ARGUMENTS

Delegate to `meta-architect`. It scaffolds; you review.

```bash
.venv/bin/python -m lifeos.scaffold <name> --label "..." --dry-run
.venv/bin/python -m lifeos.scaffold <name> --label "..."
```

## What it creates

An agent charter from `templates/AGENT_CHARTER.md`, a ledger schema composing the shared envelope, a state file, a row in the ownership table, rows in the coverage map, and the domain enabled in `profile.yaml`.

## The acceptance test — say it, then prove it

**The next `/heartbeat` must pick the new domain up with zero changes to the orchestrator.** This is definition-of-done #5.

If the orchestrator needed editing, **the scaffolding is wrong — fix the scaffolding, not the orchestrator.** Adding a special case to the loop for one domain is how a fractal system quietly stops being one.

Prove it rather than asserting it:

```bash
shasum -a 256 .claude/agents/orchestrator.md tools/py/lifeos/sense.py   # before
# ... scaffold ...
.venv/bin/python -m lifeos.audit --markdown        # the new domain is already covered
.venv/bin/python -m lifeos.status                  # /status already sees it
shasum -a 256 .claude/agents/orchestrator.md tools/py/lifeos/sense.py   # identical
```

## Then hand over

The charter has sections marked **TO FILL IN** — what the domain does *not* own, and what "done" means for it. Only a human can answer those. The domain is live regardless; those sections make it *good*, not functional.

## Rules

- **Never clobber.** Scaffolding refuses if the domain exists.
- Composing the shared envelope is not optional — it is what gives the new domain provenance, deterministic ids and confidence without writing any of that again.
- If the user wants a whole bundle rather than one domain, they want `/install-pack`.
