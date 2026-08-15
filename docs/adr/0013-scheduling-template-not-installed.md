# ADR-0013 — Ship the scheduler, do not install it

**Status** Accepted · Phase 0

## Context

The brief's central promise is a heartbeat that runs hourly, indefinitely. Claude Code is invoked, not resident — there is no daemon, so something outside the system must trigger it. On macOS that is `launchd`, or `cron`.

Installing a job is a decision with consequences the design should not make on the user's behalf. An hourly headless agent writes to real financial records, spends real tokens, and can file GitHub issues, all while nobody is watching. Whether that is desirable depends on how much the user trusts the system, which on day one is correctly not very much.

## Decision

Ship the machinery, install nothing.

- `tools/scheduler/heartbeat.sh` — wraps `claude -p /heartbeat` headless, with a lockfile so runs cannot overlap, a timeout, and output appended to `$VAULT/state/scheduler.log`.
- `tools/scheduler/com.lifeos.heartbeat.plist.template` — a documented `launchd` job with the interval, working directory and environment left as substitutions.
- `docs/scheduling.md` — the one command to install it, the one to remove it, and what to watch for in the first week.

The build never runs `launchctl load`. Turning it on is a deliberate act by the user, and turning it off must be equally easy.

**Preconditions the documentation states plainly**, because an unattended agent that is subtly misconfigured is worse than none: `/heartbeat` should have run clean manually for a while first; `github.autofile` should be considered separately, since an unattended run can file issues; and the first scheduled week should be reviewed through `state/run-log.jsonl` and the journal rather than assumed to be fine.

## Consequences

- Nothing appears in the user's login items without their say-so, and nothing spends tokens unattended by default.
- The idempotency work ([ADR-0003](0003-deterministic-sense.md), [ADR-0006](0006-deterministic-record-ids.md)) is what makes unattended running safe when it is eventually enabled; the scheduler is only the trigger.
- The lockfile matters more than it looks: an hourly job whose predecessor is still running would otherwise produce two concurrent heartbeats, and single-writer discipline ([ADR-0007](0007-single-writer-atomic-writes.md)) assumes one loop at a time.
- Manual `/heartbeat` remains fully supported and is the expected mode for a long time.
- The cost is that an unattended system requires one manual step to become unattended. That is the correct amount of friction.

## Alternatives considered

**Install an hourly job in Phase 1** — real autonomy sooner, and real unsupervised writes before the user has any basis for trusting them. Rejected.

**No scheduling artefacts at all** — leaves the brief's central promise unmet in practice, and pushes the user to improvise a wrapper without the lockfile and timeout that make it safe. Rejected.

**Claude Code scheduled tasks** — a reasonable alternative trigger and worth documenting alongside `launchd`. Not chosen as the primary because a plain shell wrapper plus `launchd` has no dependency on any particular client remaining installed, which matters for something meant to run for years.
