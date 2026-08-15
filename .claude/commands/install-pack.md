---
description: List, install or remove an optional domain pack.
argument-hint: "[list | install <name> | uninstall <name>]"
allowed-tools: Bash, Read, Glob
---

# /install-pack $ARGUMENTS

!`.venv/bin/python -m lifeos.packs status`

## No arguments → list

Show what is available and what is installed, with a line each on what a pack adds.

## `install <name>`

```bash
.venv/bin/python -m lifeos.packs install <name> --dry-run   # show, then
.venv/bin/python -m lifeos.packs install <name>
```

Run the dry run first and show the user what will change. A pack copies agents, commands and rulebooks into the core directories, appends its document types, field-extraction rules and readiness requirements between fences, and enables its domains in `profile.yaml`.

Then report the pack's `next_steps` — which documents to drop in `$VAULT/inbox/`, and which command to run.

## `uninstall <name>`

Removes what the pack added and nothing else. **Ledger data and domains are left alone**: the trust records stay, and the domain stays enabled. Removing a capability is not a decision that the data no longer matters. Say this — a user expecting a clean wipe should know they did not get one, and a user expecting their data kept should know it was.

## Rules

- **Install is idempotent.** Running it twice is a no-op by design; a half-installed pack is worse than an uninstalled one.
- **A pack never overwrites.** If it declares a file or a key the core or another pack already provides, the install is **refused** with the collision named. Appending a duplicate YAML key does not merge — it produces a document that will not parse, and the failure would land on the next command rather than on the install.
- **A pack installs capability, never data.** It touches no ledger. A colleague installing `trusts` gets the machinery and none of anyone else's records.
- After installing, tell the user to run `/heartbeat` so the new document types are picked up.
