# ADR-0019 — Packs are merged, not forked

**Status** Accepted · Phase 6

## Context

The brief requires optional bundles — `trusts`, `sme-owner`, `expat`, `phd-researcher`, `landlord` — that layer agents, ledgers, rulebooks and commands onto the core, and states that **installing one is a merge, not a fork**. The acceptance test is concrete: a colleague clones the repo, runs `/lifeos-init`, chooses the `trusts` pack, and has a genuinely useful trust-administration assistant within an hour, without touching anyone else's data.

A fork — copy the repo, add trust code, diverge — fails that test on the second day, when a core fix has to be applied twice and the two copies drift.

## Decision

A pack is a directory under `packs/<name>/` obeying the same conventions as the core, with a `pack.yaml` manifest. Installing copies its files into the counterpart core directories and **appends** its rules between fences:

```
# >>> LIFEOS PACK: trusts >>>
...
# <<< LIFEOS PACK: trusts <<<
```

Four properties, each load-bearing:

**Nothing in the core is edited.** Appends are fenced, so uninstall removes exactly what was added and a core upgrade does not fight the pack.

**Install is idempotent.** Running it twice is a no-op. A half-installed pack — an agent present but its rulebook missing — is worse than none, because it fails at classification time rather than at install time.

**Collisions are refused, not merged.** If a pack declares a key the core or another pack already provides, the install fails with the collision named. This was found the hard way: the trusts pack initially redefined `trust_deed`, which the core already classified. Appending a duplicate YAML key does not merge — it produces a document that will not parse, and the failure surfaced on the *next* command to read it, not on the install. Fail fast, at the point the human can act.

**A pack installs capability, never data.** It touches no ledger and no vault record. That is what makes it safe for a colleague: they get the machinery for trust administration and none of anyone else's affairs.

**A pack carries the rules for reading its own documents.** The core knows nothing about trust deeds. Document types, field-extraction patterns and readiness requirements all travel in the manifest, so adding a domain is data plus a fixture, not a code change.

## Consequences

- One codebase, many configurations. A core fix reaches every installation.
- A pack is reviewable as a single file: `pack.yaml` says exactly what it will do.
- Uninstall deliberately leaves **domains enabled and ledger data untouched**. Removing a capability is not a decision that the data no longer matters, and silently hiding records would be worse than leaving a domain enabled with nothing writing to it.
- The cost is that a pack cannot *extend* an existing key — only add new ones. Enriching the core's `trust_deed` classifier means changing the core, deliberately and in review. That is the right friction.
- Packs cannot depend on each other in this design. If that need arises, it wants an explicit `requires:` field and a resolution order, not implicit ordering.

## Alternatives considered

**Fork per pack** — what the brief explicitly rules out, and rightly: two copies of a system that holds financial records will drift, and only one of them will get the security fix.

**Runtime overlay** — resolve pack files at load time rather than copying, so nothing is ever written into the core. Cleaner in principle, and it would make `.claude/agents/` no longer the whole truth about which agents exist. Copying is inspectable: what is installed is what is on disk.

**Everything in the core, enabled by config** — no pack mechanism at all, just `domains:` flags. Simplest, and it makes every user carry every domain's agent descriptions in their dispatch context — the exact cost [ADR-0010](0010-lean-agent-tree.md) exists to avoid.
