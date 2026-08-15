# ADR-0016 — Jurisdiction is a config axis

**Status** Accepted · Phase 0

## Context

LifeOS is built for a South African user, and the tax, estate and trust logic is deeply SA-specific: provisional tax, `s7C`, Reg 28, `s4A` abatement, the two-pot retirement system, the Master's beneficial-ownership register. The brief asks that SA rulebooks ship, and that the structure permit a `.claude/rules/<jurisdiction>/` sibling later.

There is also a live possibility — the user has an emigration scenario in `/what-if` and an `expat` pack in the roadmap — that a second jurisdiction becomes relevant to the *same* vault rather than to a different user.

## Decision

**Jurisdiction is data, not code.** `.claude/rules/<code>/` holds the rulebooks; `profile.yaml` names the active jurisdiction per person and per entity, because in a family or a group of companies these genuinely differ.

**Agent logic never hard-codes a rule.** No rate, threshold, abatement or deadline appears in an agent charter, a skill or a tool. Agents ask for the rule by name; the rulebook supplies the value.

**Every rulebook file declares its own currency:**

```yaml
jurisdiction: za
rule: retirement-deduction
as_at: 2026-03-01
refresh_interval: P1Y
source: https://www.sars.gov.za/...
values: { ... }
```

A rule past its `refresh_interval` produces a `rule.expired` signal, must be re-verified before it is relied on, and every output that uses it states when it was last verified. Verification is a public-information lookup, which is exactly the traffic the redaction hook permits.

**What is not abstracted.** The seven pipeline stages, the record envelope, the loop, memory and readiness are jurisdiction-neutral already. Domain *agents* are largely neutral too — what varies is which rules they consult and which deadlines exist. Where structure genuinely differs (a jurisdiction with no equivalent of a discretionary trust), the mechanism is a pack, not a fork.

## Consequences

- A tax table update is a data edit with an `as_at` bump, not a code change — which is what makes annual SARS changes routine rather than a release.
- Multi-jurisdiction households work without contortion, because jurisdiction attaches to the person or entity rather than to the installation.
- Rule currency becomes a first-class, monitored property instead of an assumption that quietly rots.
- Adding a second jurisdiction is real work — someone must write the rulebooks — but it is *additive* work in one directory, with no change to agents, schemas or the loop.
- The brief's requirement that every claim about tax law carry an "as at" date and a source is satisfied structurally: the metadata is in the rule, so an output cannot cite a rule without also being able to cite its date.
- The cost is indirection. Reading an agent charter no longer tells you the rate. `/status` listing stale rulebooks compensates.

## Alternatives considered

**Hard-code SA rules and generalise later** — faster now, and the refactor lands exactly when the system is largest and most load-bearing. Rejected; the abstraction is cheap today.

**A jurisdiction abstraction layer with per-jurisdiction agent implementations** — far more machinery than the variation justifies. Most of what differs is values and deadlines, which is data.

**Fetch rules live rather than caching them** — no staleness problem, but a network dependency on every tax computation and no reproducibility: a report re-run next year would silently use different rules. Caching with an explicit `as_at` is what makes `/audit` meaningful.
