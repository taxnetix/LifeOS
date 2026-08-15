# ADR-0002 — Fractal in definition, flat at runtime

**Status** Accepted · Phase 0

## Context

The brief requires that every agent, at every level, obey the same seven-part charter, and that a domain agent decompose into specialists which may themselves decompose further — the orchestrator's relationship to a domain agent being structurally identical to a domain agent's relationship to its specialists. This fractal property is what allows a new life domain to be added by instantiating a contract rather than writing bespoke plumbing.

Taken literally at runtime, it requires a subagent to spawn subagents, recursively and without a fixed depth. Building the system's central loop — the thing that must run hourly, forever, unattended — on unbounded nested dispatch is not a safe foundation: nested spawning is not a guarantee to rely on, depth is unbounded by construction, and cost and concurrency become invisible because no single component sees the whole tree.

## Decision

Separate the two meanings of "fractal".

**In definition — fully recursive.** Every agent at every level is generated from `templates/AGENT_CHARTER.md` and obeys the identical seven-part contract. A specialist's charter is structurally indistinguishable from the orchestrator's. This is preserved exactly as the brief requires.

**At runtime — flattened into waves.** The orchestrator is the only component that spawns agents. An agent needing a specialist returns a `dispatch_requests[]` array in its structured result; the orchestrator executes those in the next wave of the same heartbeat.

```
wave 1   orchestrator → finance, insurance, tax
         finance returns dispatch_requests: ["statement-parser:absa-cheque"]
wave 2   orchestrator → statement-parser:absa-cheque
         returns dispatch_requests: []
wave 3   none requested → DISPATCH ends
```

Bounded by `max_waves` (default 4) in `settings.json`. Exceeding it parks the remaining requests as queued work for the next heartbeat rather than failing.

## Consequences

- Recursion depth becomes iteration count — observable, bounded, resumable, and interruptible between waves.
- Cost and concurrency are visible in exactly one place.
- A wave boundary is a natural checkpoint: a heartbeat killed mid-run resumes at wave granularity.
- Definition-of-done #5 still holds — `/add-domain` output is picked up by the loop unmodified, because the loop only ever reads charters and dispatches them.
- The cost is one extra orchestrator round-trip per level of depth. In practice depth rarely exceeds two.
- Agents must return structured results rather than prose, which is a discipline worth having anyway.

## Alternatives considered

**True nested dispatch** — matches the brief literally, but makes the hourly loop depend on a behaviour that is neither bounded nor guaranteed. Rejected as too fragile for the one component that must never break.

**Fixed two-level hierarchy** — simple and safe, but forecloses depth permanently and contradicts "a domain earns depth by complexity". Rejected.

**Agents call tools instead of specialists** — works for deterministic leaf work and is what [ADR-0004](0004-tools-compute-skills-judge.md) does, but a specialist that needs *judgment* is not a script. Both mechanisms are needed.
