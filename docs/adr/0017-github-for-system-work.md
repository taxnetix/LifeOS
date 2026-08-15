# ADR-0017 — GitHub tracks the system, never your life

**Status** Accepted · Phase 0

## Context

`gh` is installed and authenticated on this machine, and the user asked that agents use GitHub for issue tracking, project management and self-maintenance — noting it is valuable for maintaining the system, the tools, and for state tracking.

The value is real. `state/queue.json` is per-vault, ephemeral in practice, and invisible from anywhere else. A backlog of "the ABSA parser needs a new fingerprint" or "`policies.jsonl` needs a `cession` field" deserves to outlive a session, be linkable to a commit and a PR, and be reviewable months later. Milestones give phase progress an external measure rather than a self-assessment.

The hazard is equally real. GitHub is a third-party network service. Brief constraint §3 permits outbound traffic only for public reference information; constraint §5 human-gates anything externally visible; definition-of-done #6 requires that nothing personal has *ever* entered this repo's history. An issue body is published, notified, indexed and cached — deleting it later does not un-send it.

## Decision

**GitHub tracks the system. It never touches the life.**

The operative rule agents follow: **an issue may describe a _class of problem_; it may never contain an _instance of your data_.** "ABSA changed statement column order in mid-2026" is publishable engineering. "Your July statement, account 4051…" is not. Agents abstract before they file.

**Files remain the source of truth.** `state/system/issues.jsonl` is the local view; `tools/py/gh_sync.py` reconciles it during SENSE, refreshing when the network is up and **degrading silently to the cache when it is not**, setting `github.reachable: false`. GitHub can never fail a heartbeat — a flight, an outage or an expired token must not break the loop.

**Egress is guarded, not trusted.** `pii-guard.py` registers on `PreToolUse` for `Bash` commands matching `gh *`, applying the same profile-derived matcher used for web lookups ([ADR-0015](0015-redaction-enforced-by-hook.md)).

**Filing is human-gated by default.** Reads are free. Writes — `issue create`, `comment`, `pr create` — go through `proposed/issues/` and `/issues push`. `github.autofile: true` opts out, sensibly only for a private repo. Destructive operations — repo or issue deletion, force-push, history rewriting, branch-protection changes, direct pushes to `main` — are prohibited outright, and every agent code change arrives as a reviewable PR.

**Priority is capped below life work.** A failing CI run must not outrank a provisional tax deadline. `profile.yaml → github.priority_ceiling` enforces it.

**Ownership.** `orchestrator` syncs; `meta-architect` authors and triages. No new agent ([ADR-0010](0010-lean-agent-tree.md)).

## Consequences

- The system gains a durable, reviewable backlog for its own maintenance, and a self-repair loop: an unparseable statement layout becomes an abstract issue, then an adapter, then a PR, then a native parse.
- Rulebook staleness gets a durable reminder that outlives the session that noticed it — a public fact about public tax tables, safe to publish.
- The `self-filed` label makes machine-authored backlog auditable separately from the user's own.
- Offline behaviour is a design property, not an accident.
- **The residual risk is stated plainly:** anything that does reach GitHub is effectively unremovable. `/forget` therefore reports GitHub content as unremovable and advises treating it as disclosed. This is why the hook, the gate and the abstraction rule all exist rather than any one of them.
- The repo being public or private changes the blast radius of a redaction miss, not the rules. Public argues strongly for keeping filing gated.
- **Live finding:** the current token carries `gist, read:org, read:project, repo`. `repo` covers issues, labels, milestones and PRs — everything this design uses. `read:project` is read-only, so a Projects v2 board would need `gh auth refresh -s project`. Phase tracking uses milestones instead, which work today.

## Alternatives considered

**GitHub as the source of truth for system work** — simpler, no mirror to reconcile, and it makes the hourly loop depend on network availability and a valid token. Rejected; contradicts [ADR-0001](0001-files-are-the-database.md) and local-first.

**Track life work in GitHub issues too** — the user's queue would become genuinely nicer to use, and it would put financial and medical details on a third-party server. Rejected outright; this is the line the whole system exists to hold.

**A private GitHub repo for vault work items** — better, and still an unnecessary copy of personal data on someone else's infrastructure for a benefit that `state/queue.json` already delivers locally. Rejected.

**No GitHub at all** — loses durable self-maintenance and external phase tracking for a risk that a hook plus a human gate plus an abstraction rule can manage. Rejected.
