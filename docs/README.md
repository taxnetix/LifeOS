# LifeOS — Documentation

**Phase 0 (Plan) is complete.** Everything here is design. No agents, commands, hooks or tools are implemented yet — that begins in Phase 1, after review.

Source brief: [LIFE-OS-BOOTSTRAP-PROMPT.md](../LIFE-OS-BOOTSTRAP-PROMPT.md)

## Read in this order

| # | Document | What it settles |
|---|---|---|
| 1 | [architecture.md](architecture.md) | System/vault split, the fractal contract, data model, pipelines, memory, guardrails |
| 2 | [loop.md](loop.md) | The perpetual loop, deterministic SENSE, cadence triggers, SA fiscal calendar, idempotency proof |
| 3 | [agent-catalogue.md](agent-catalogue.md) | All 17 agents, and the authoritative ledger-ownership table |
| 4 | [coverage-map.md](coverage-map.md) | All 175 taxonomy leaves → owner + schema + checklist. The "nothing dropped" contract |
| 5 | [data-dictionary.md](data-dictionary.md) | Record envelope, every ledger field, POPIA classification and erasure paths |
| 6 | [commands.md](commands.md) | 20 command contracts: args, preconditions, idempotency, human gates |
| 7 | [github.md](github.md) | GitHub as the system's own backlog, and the boundary that keeps your life off it |
| 8 | [dependencies.md](dependencies.md) | Every package justified; external binaries; two live findings |
| 9 | [adr/](adr/README.md) | 18 architecture decision records |

## Schemas

`templates/schemas/` — 42 JSON Schema 2020-12 files, all parsing, all `$ref`s resolving.

```
envelope.schema.json          the record envelope everything composes with allOf
ledgers/    (32)              one per ledger
state/       (7)              cursors, queue, gaps, agent-state, run-log, issues, audit
memory/      (2)              memory audit, long-term front matter
config/      (1)              budgets.yaml
```

## The five decisions that shape everything else

1. **Files are the database** ([ADR-0001](adr/0001-files-are-the-database.md)) — legible in thirty years, by a non-programmer, without this system.
2. **Fractal in definition, flat at runtime** ([ADR-0002](adr/0002-fractal-definition-flat-runtime.md)) — the charter recurses; execution becomes waves, so the hourly loop rests on nothing fragile.
3. **SENSE is a script, not a thought** ([ADR-0003](adr/0003-deterministic-sense.md)) — this is what makes an idle heartbeat genuinely nearly free.
4. **Deterministic record IDs** ([ADR-0006](adr/0006-deterministic-record-ids.md)) — idempotency as a property of the data, not a behaviour to remember.
5. **Redaction enforced by hook** ([ADR-0015](adr/0015-redaction-enforced-by-hook.md)) — privacy as a mechanism, holding even when an agent is wrong.

## Where the design departs from the brief

Each is argued in full in its ADR: skills cannot be pipeline stages ([0004](adr/0004-tools-compute-skills-judge.md)); runtime recursion is flattened ([0002](adr/0002-fractal-definition-flat-runtime.md)); the SQLite read-model is dropped ([0009](adr/0009-no-sqlite-read-model.md)); the agent tree is lean and earns depth ([0010](adr/0010-lean-agent-tree.md)); the scheduler ships uninstalled ([0013](adr/0013-scheduling-template-not-installed.md)).

Additions the brief did not specify: a testing strategy, integer-cents money, idempotency keys, single-writer atomic writes, schema versioning, a bank-adapter registry with an explicit human-confirm fallback, a gaps register, a stable clock, FX rates, `/forget` for POPIA erasure, and GitHub as the system's own backlog.

## Open item

The vault lives at `./vault/` inside this repo, git-ignored, per your instruction. `.gitignore` is advisory and git history cannot be un-rung, so the pre-commit hook is a hard control rather than a convenience. If you later want definition-of-done #6 guaranteed structurally, moving the vault out is one `$LIFEOS_VAULT` change — but it must happen before the first real document lands. See [ADR-0008](adr/0008-vault-location-and-separation.md).
