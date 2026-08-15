# ADR-0010 — Lean agent tree; depth is earned

**Status** Accepted · Phase 0

## Context

The domain taxonomy decomposes to 175 leaves. The brief requires that every leaf be represented — as an agent, a ledger schema, or a checklist item with an owner — and that nothing be silently dropped. It also says a domain *earns* depth by complexity, and that depth is not fixed.

A literal reading produces around fifty agent files. Every agent's description is loaded so the dispatcher can route to it, so fifty agents means a large, permanent context cost on every session and a harder routing decision — more candidates, finer distinctions, more misroutes. It also front-loads a great deal of speculative structure: most of those specialists would have no work to do for months, and their shape would be guessed before any real document had been seen.

## Decision

**17 agent files.** Six system agents — `orchestrator`, `librarian`, `memory-keeper`, `meta-architect`, `analyst`, `visualiser` — and eleven domain agents covering taxonomy A–J, with banking split into `finance` because it carries the flagship pipeline.

**A specialist begins as a charter section plus a skill inside its domain agent,** not as its own file. `meta-architect` monitors `state/agents/<name>.json` and proposes promotion when measured overload appears: run duration, error rate, open-loop count, or number of ledgers owned crossing thresholds set in `profile.yaml`. Promotion is a proposal for you to approve, not an automatic refactor.

**Coverage is proven, not counted.** `docs/coverage-map.md` maps all 175 leaves to an owner plus a ledger, schema or checklist entry. `/audit` parses it, cross-checks against `.claude/agents/` and `templates/schemas/` on disk, and fails on any unowned leaf, missing owner or missing schema.

The candidate specialists and their promotion triggers are listed at the end of `docs/agent-catalogue.md`, so the growth path is explicit rather than improvised.

## Consequences

- Routing stays accurate and session context stays small.
- Structure follows evidence. An agent exists because work justified it, not because a taxonomy predicted it.
- Definition-of-done #3 — every leaf has a named owner — is satisfied by a machine-checked artefact, which is a stronger guarantee than a file count.
- The fractal property is unaffected: a promoted specialist is generated from the same charter template and dispatched identically ([ADR-0002](0002-fractal-definition-flat-runtime.md)).
- The cost is that domain agents carry more scope early, and their charters are longer. `meta-architect`'s overload monitoring exists precisely to catch when that stops being reasonable.
- There is a risk of never promoting anything because thresholds are never tuned. Mitigated by the quarterly coverage audit surfacing overload signals whether or not a threshold fired.

## Alternatives considered

**Fifty agents up front** — maximum literal fidelity, real cost to routing and context, and a great deal of speculative structure. Rejected.

**Lean everywhere except a full specialist tree for trusts** — tempting, since trusts is a colleague's entire use case. Rejected for now: the same promotion mechanism serves it, and Phase 6 can promote several trust specialists at once on evidence rather than assumption.

**One agent per ledger** — a clean rule that fragments cohesive domains; `insurance` would become seven agents that always run together. Rejected.
