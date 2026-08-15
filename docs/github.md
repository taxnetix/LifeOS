# LifeOS — GitHub as the System's Own Tracker

> Status: Phase 0 (design). Nothing here is implemented yet.
> Decision record: [ADR-0017](adr/0017-github-for-system-work.md).

LifeOS agents have `gh` available and use it to track, plan and maintain **the system itself**. Issues become the durable backlog for tool bugs, bank-statement adapters, rulebook refreshes, agent refactors and phase progress — work that survives sessions, machines and context windows in a way `state/queue.json` alone does not.

## 1. The boundary — read this first

GitHub is a **third-party network service**. Brief constraint §3 says nothing leaves the machine except explicit, agent-declared lookups of *public reference information*. `gh` is therefore an **egress channel**, and it is governed exactly like `WebFetch`.

```
GitHub tracks     THE SYSTEM     tools, agents, schemas, rules, docs, phases
GitHub NEVER      YOUR LIFE      transactions, policies, tax, family, documents
```

| Belongs on GitHub | Stays in `state/queue.json` |
|---|---|
| "ABSA changed statement column order in mid-2026; add a layout fingerprint" | "Parse *your* July ABSA statement" |
| "`za/sars-tables.yaml` is past its refresh interval" | "*Your* effective rate rose to 34%" |
| "`policies.jsonl` needs a `cession` field" | "*Your* Old Mutual policy is ceded to the bond" |
| "Beneficiary-conflict check has no test fixture" | "*Your* RA nomination contradicts *your* will" |
| "Phase 4 blocked on health-cover map design" | "*Your* gap cover duplicates group life" |

**The rule agents follow: an issue may describe a _class of problem_; it may never contain an _instance of your data_.** Agents abstract before they file. The left column of that table is publishable engineering; the right column is your life, and it stays on disk.

### 1.1 Enforcement, not etiquette

A hook that guarded only `WebFetch` would be defeated by `gh issue create --body "…"`. So `.claude/hooks/pii-guard.py` registers on `PreToolUse` for **`Bash` commands matching `gh *`** as well, and applies the same matcher used for web lookups: SA ID numbers, account/policy/member numbers, email addresses, physical addresses, and every proper name drawn from the live `profile.yaml`.

A blocked `gh` call is logged to `state/audit.jsonl` with the matched pattern class — never the matched value.

### 1.2 Filing is human-gated by default

Creating a public issue is an externally-visible, effectively-irreversible act (GitHub notifies, indexes and caches; deleting later does not un-send). Brief constraint §5 applies. So:

| Operation | Gate |
|---|---|
| `gh issue list/view`, `gh pr list/view`, `gh run list` | **ungated** — read-only, nothing leaves |
| `gh issue create/comment/edit`, `gh pr create`, label/milestone writes | **gated** — agent writes `proposed/issues/<slug>.md`, you approve, `/issues push` files them |
| `gh repo delete`, `gh issue delete`, force-push | **prohibited** — never, by any agent |

Set `github.autofile: true` in `profile.yaml` to skip the gate — sensible once you trust it, and recommended only for a **private** system repo. The default is gated.

## 2. Files remain the database

GitHub is a **synchronised mirror, not the source of truth** ([ADR-0017](adr/0017-github-for-system-work.md)). `state/system/issues.jsonl` holds the local view; `tools/py/gh_sync.py` reconciles it.

This matters for a specific reason: `gh` needs network. If GitHub were authoritative, a flight, an outage or an expired token would break `/heartbeat`. Instead SENSE calls `gh_sync.py`, which:

- refreshes `state/system/issues.jsonl` when the network is available;
- **degrades silently to the cached view when it is not**, setting `github.reachable: false` in the sense report;
- never blocks the loop, and never fails a heartbeat because GitHub was unreachable.

`state/system/issues.jsonl` record shape:

```json
{
  "number": 42,
  "title": "Add ABSA cheque-account layout fingerprint for 2026-07 format",
  "state": "open",
  "labels": ["kind:adapter", "area:tool/parsers", "phase:3"],
  "milestone": "Phase 3 — Financial flagship",
  "assignees": ["arneschreuder"],
  "url": "https://github.com/<owner>/life-os/issues/42",
  "created_at": "2026-08-15T09:14:22Z",
  "updated_at": "2026-08-15T09:14:22Z",
  "synced_at": "2026-08-15T09:20:00Z",
  "local_only": false
}
```

`local_only: true` marks an issue proposed but not yet filed — so the backlog is complete and usable offline.

## 3. Taxonomy

### Labels

| Prefix | Values | Meaning |
|---|---|---|
| `kind:` | `bug` `feature` `adapter` `rule-refresh` `schema` `refactor` `docs` `test` `security` | what sort of work |
| `area:` | `agent/<name>` `tool/py` `tool/js` `tool/parsers` `schema` `hooks` `commands` `skills` `rules` `packs` `docs` | where in the system |
| `domain:` | `finance` `insurance` `tax` `estate` `trusts` … | which life domain the *capability* serves (never which of your records) |
| `phase:` | `0`–`7` | build phase |
| `needs:human` | — | blocked on a decision only you can make |
| `blocked` | — | blocked on another issue |
| `self-filed` | — | opened by an agent rather than a person |

`self-filed` is not decoration. It makes it trivially auditable which parts of the backlog the system wrote about itself, and lets you review the machine's judgment separately from your own.

### Milestones

One per build phase, `Phase 0 — Plan` … `Phase 7 — Intelligence & closure`. Phase completion is measured as milestone closure, which gives `/status` a real, external progress number instead of a self-assessment.

### Issue templates

`.github/ISSUE_TEMPLATE/` — each carries a standing reminder that no personal data may appear:

| Template | For | Required fields |
|---|---|---|
| `adapter.yml` | a new or broken statement parser | bank, format class, fingerprint, sample **structure** (never a real statement) |
| `rule-refresh.yml` | a stale rulebook | rule file, `as_at`, refresh interval, authoritative source URL |
| `schema-change.yml` | a ledger schema bump | ledger, current version, change, migration sketch, ADR link |
| `agent-refactor.yml` | promoting or splitting an agent | agent, overload evidence *(metrics only)*, proposed split |
| `bug.yml` | tool defect | tool, expected, actual, **redacted** repro against `vault.example/` |

Every bug repro must reproduce against `vault.example/` — the fake vault. If it cannot be reproduced there, the fixture is the first thing to build, and that is itself the issue.

## 4. Self-maintenance loop

This is what the integration is actually for.

```
1. finance hits an ABSA statement no adapter fingerprints
2. it writes the transactions to proposed/ (never guessed into the ledger)
3. it opens a gap record locally, and drafts proposed/issues/absa-2026-07-layout.md
   — describing the LAYOUT CHANGE, with zero statement content
4. you approve; /issues push files it as kind:adapter, area:tool/parsers, phase:3
5. a later /heartbeat sees github.issue.open, dispatches meta-architect
6. meta-architect writes the adapter + a fixture in vault.example/, runs pytest,
   opens a PR that closes the issue
7. you review and merge. Next heartbeat parses the statement natively.
```

The same loop drives rulebook currency: a `.claude/rules/za/*.yaml` past its `refresh_interval` produces a `rule-refresh` issue naming the rule and the authoritative source — a public fact about public tax tables, safe to publish, and a durable reminder that outlives the session that noticed.

## 5. Where GitHub appears in the loop

**SENSE** gains four signal kinds, all sourced from the cached mirror:

| Kind | Meaning |
|---|---|
| `github.issue.open` | actionable system work exists |
| `github.issue.needs_human` | an issue is blocked on your decision |
| `github.pr.review_requested` | a PR is waiting on you |
| `github.ci.failed` | a workflow run failed on the default branch |

**TRIAGE** treats these as system-domain work items owned by `meta-architect`, and — deliberately — at **lower priority than life work**. A failing CI run should not outrank a provisional tax deadline. `profile.yaml → github.priority_ceiling` caps it.

**REFLECT** reports GitHub state in the journal's "what I need from you" section, alongside `proposed/`.

## 6. Ownership

| Concern | Owner |
|---|---|
| Sync, cache, offline degradation | `orchestrator` (via `tools/py/gh_sync.py` in SENSE) |
| Authoring, triage, labelling, milestones, PRs | `meta-architect` |
| Redaction enforcement | `.claude/hooks/pii-guard.py` |
| Human gate | `proposed/issues/` + `/issues push` |

No new agent. `meta-architect` already owns the system itself; issue tracking is that job with a durable backend ([ADR-0010](adr/0010-lean-agent-tree.md)).

## 7. Commands

| Command | Does |
|---|---|
| `/issues` | triaged view of the mirror: open, needs-human, blocked, by phase |
| `/issues propose <desc>` | draft an issue to `proposed/issues/` — redaction-checked, never filed directly |
| `/issues push` | file every approved draft; report numbers and URLs |
| `/issues sync` | force a mirror refresh |

`/status` reports milestone progress and open-issue counts alongside agent health and queue depth.

## 8. Prerequisites and one live finding

**Repository.** This directory is not yet a git repo and has no remote. Phase 1 runs `git init`; creating the GitHub remote is your call, and the choice of **public or private** matters:

- **Private** — `github.autofile: true` is reasonable; the blast radius of a redaction miss is small.
- **Public** — keep filing gated. The brief's definition of done says nothing personal has *ever* entered this repo's history, and a public issue body is history you cannot rewrite.

**Token scopes — action needed for project boards.** Your `gh` token currently carries `gist, read:org, read:project, repo`.

- `repo` covers everything in this design: issues, labels, milestones, PRs. ✅
- `read:project` is **read-only**. A GitHub Projects v2 board for phase tracking would need write access:

```bash
gh auth refresh -s project
```

Phase-tracking via **milestones** works today with `repo` alone, and that is what this design uses. A Projects board is optional sugar — worth the re-auth only if you want a kanban view.

## 9. Prohibited

Agents never: delete a repository or an issue, force-push, rewrite history, alter branch protection or repository settings, add collaborators, publish a release, or push to `main` directly. Every code change from an agent arrives as a pull request you review.
