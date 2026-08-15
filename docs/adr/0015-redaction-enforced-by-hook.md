# ADR-0015 — Redaction is enforced by hook, not convention

**Status** Accepted · Phase 0

## Context

LifeOS is local-first and private by default. The brief permits exactly one class of outbound traffic: explicit, agent-declared lookups of public reference information — tax tables, product terms, benchmark rates. It forbids sending personal identifiers, account numbers, ID numbers or document contents, and states that redaction is a hard rule enforced by a hook.

Instructing agents not to leak is not a control. It is a hope with good intentions. Agents are asked to research "what does this medical aid option cover", and the most natural query to write is the one containing the member number. The failure is a single plausible-looking tool call, and it is irreversible: a search query is logged by the provider, an issue body is indexed and cached.

## Decision

**`.claude/hooks/pii-guard.py` registers on `PreToolUse` for every egress channel**, and the definition of egress is deliberately broad:

| Channel | Why it counts |
|---|---|
| `WebFetch`, `WebSearch` | obvious |
| `Bash` matching `gh *` | an issue body is publication ([ADR-0017](0017-github-for-system-work.md)) |
| `Bash` matching `curl`, `wget`, `nc`, `ssh`, `scp`, `rsync` | direct network egress |

It also registers on `Write`/`Edit` to block modification of `documents/` originals, which are immutable by design.

**The matcher is derived from live data, not a static list.** It loads `profile.yaml` at call time and blocks on: SA ID-number patterns (13 digits with a valid Luhn check), account, policy, member and registration numbers present in the ledgers, email addresses, physical addresses, and every proper name of every person and entity in the profile. A static regex set would miss the names that matter most — the user's own.

**Blocking is the default on ambiguity.** A borderline match blocks and explains, rather than allowing and warning. The agent is told what class of pattern matched so it can rewrite the query generically, which is almost always possible: "Discovery Classic Comprehensive 2026 benefits" answers the question that "member 12345678 plan details" was reaching for.

**Every block is logged** to `state/audit.jsonl` with the pattern *class* and never the matched value — a redaction log that contained the redacted values would be self-defeating.

## Consequences

- The privacy guarantee is a mechanism rather than a behaviour, so it holds even when an agent is wrong, a prompt is poorly worded, or a future model reasons differently.
- The audit log makes leak attempts visible, which turns a silent risk into a reviewable signal — a rising block count means an agent needs better instructions.
- False positives are expected and acceptable. A common surname in the profile will block innocuous queries; the fix is rewriting the query, and the cost of that annoyance is far below the cost of one leak.
- Hook latency is on the path of every matching tool call, which is part of why validation lives in Node where startup time matters ([ADR-0011](0011-python-primary-thin-node.md)).
- The guard is not a substitute for the pre-commit hook — different channel, different control ([ADR-0008](0008-vault-location-and-separation.md)).
- A hook cannot cover a channel it does not know about. New egress mechanisms must be added to the matcher, and `/selftest` includes a live block test so a broken hook fails the suite rather than failing open.

## Alternatives considered

**Instruct agents in `CLAUDE.md` and trust them** — the brief explicitly rejects this, and it is right to.

**Allow-list of permitted domains** — controls *where* traffic goes, not *what* it carries. A permitted tax-authority site can still receive an ID number. Complementary, not sufficient.

**Strip PII automatically and let the call through** — silently altering a query produces confusing results and teaches the agent nothing. Blocking with an explanation produces a better query.

**Block all network access** — would forbid the public reference lookups the brief explicitly permits and the tax rulebooks genuinely need.
