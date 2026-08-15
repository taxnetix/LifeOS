---
description: Triage the system backlog. Subcommands - propose, push, sync. System work only, never personal data.
argument-hint: "[propose <desc> | push | sync | --phase N | --needs-human]"
allowed-tools: Bash, Read, Write, Grep, Glob, Task
---

# /issues $ARGUMENTS

The system's own backlog: tool bugs, statement adapters, stale rulebooks, schema bumps, agent refactors, phase progress. Full rules in `docs/github.md`.

## The boundary — before anything else

**An issue may describe a _class of problem_. It may never contain an _instance of the user's data_.**

| File it | Never |
|---|---|
| "ABSA changed statement column order mid-2026" | "Parse the July ABSA statement" |
| "`za/sars-tables.yaml` past refresh interval" | "Effective rate rose to 34%" |

The `pii-guard` hook enforces this on the `gh` call. Being blocked means the mistake was already made — abstract first.

## No subcommand → triage

!`.venv/bin/python -m lifeos.status`

Read `$VAULT/state/system/issues.jsonl` and report:

1. **Blocked on you** — `needs:human`, and unfiled drafts in `$VAULT/proposed/issues/`
2. **Open work** by `phase:` and `kind:`
3. **Milestone progress** per phase
4. **Mirror freshness** — if GitHub was unreachable, say the view is a cache and give its age

Works fully offline from the cache.

## `propose <desc>` → draft only

Delegate to `meta-architect`. It writes `$VAULT/proposed/issues/<slug>.md`:

```markdown
Title: <imperative, specific, no personal data>
Labels: kind:adapter, area:tool/parsers, phase:3, self-filed
Milestone: Phase 3 — Financial flagship

## Problem
<the class of problem>

## Evidence
<metrics, structure, layout — never a real document, never a real number from the user's life>

## Proposed fix
<what would close this>
```

Nothing reaches GitHub. Show the draft and stop.

## `push` → the egress point

For each draft in `$VAULT/proposed/issues/`:

1. **Show it to the user in full.** Get explicit approval unless `profile.github.autofile` is true.
2. File it:
   ```bash
   gh issue create --title "..." --body-file <draft> --label "..." --milestone "..."
   ```
3. Move the draft to `$VAULT/proposed/issues/filed/` and re-sync.
4. Report numbers and URLs.

If the hook blocks a push, **do not rewrite the body to slip past it.** The block means personal data is in the draft. Abstract the content and re-propose.

## `sync` → refresh the mirror

!`.venv/bin/python -m lifeos.gh_sync`

Degrades silently offline, setting `reachable: false`. It must never fail a heartbeat.

## Never

Delete a repo or issue · force-push · rewrite history · change branch protection or settings · add collaborators · publish a release · push to `main`. Code changes arrive as pull requests.
