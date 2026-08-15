# ADR-0008 — System and vault are separate; vault is `./vault/`

**Status** Accepted, with a flagged risk · Phase 0

## Context

The brief calls system/vault separation "the single most important structural decision", requires that the shared repo contain zero personal data, and sets as definition-of-done #6 that **nothing personal has ever entered this repo's git history**. The repo is meant to be shareable — MIT-licensed, cloneable by a colleague who wants the trusts pack.

Two placements were considered: a separate private git repository at `$LIFEOS_VAULT`, or `./vault/` inside this repo excluded by `.gitignore`. The user chose to keep everything in this folder.

## Decision

**Layout.** The vault lives at `./vault/`, git-ignored. `$LIFEOS_VAULT` remains the primary resolution path and overrides it, so relocation later costs one environment variable.

**Resolution.** `tools/py/vault.py` and `tools/js/vault.mjs` are the only code permitted to compute the vault root. Agents and skills refer to `$VAULT/...` and resolve through a tool. `/selftest` greps the system repo for absolute paths under `/Users` and fails on any hit.

**Defence in depth**, because `.gitignore` alone is not a control:

1. `.gitignore` excludes `vault/`, `.venv/`, `node_modules/`, `*.local.*`.
2. A **pre-commit hook** refuses any commit with a staged path under `vault/`, and additionally greps staged diffs for SA ID-number and account-number patterns and for every proper name in the live `profile.yaml`.
3. The `vault-audit` `PostToolUse` hook logs every vault mutation to `state/audit.jsonl`.
4. `vault.example/` exists so that tests, demos and documentation never need to touch the real vault.

## Consequences

- One directory to back up, one to open, no environment variable to configure on a fresh machine. This is the convenience the choice buys, and it is real.
- **The flagged risk.** `.gitignore` is advisory. `git add -f`, an edited `.gitignore`, `git stash -u`, or a `git clean` mishap each defeat it, and git history cannot be un-rung — a leak discovered later is permanent unless the repo is rewritten and force-pushed everywhere it has been cloned. The pre-commit hook is therefore a hard control, not a convenience, and must never be bypassed with `--no-verify`.
- Publishing the repo carries a review step: before the first push, confirm `git log --all --stat` mentions nothing under `vault/`.
- If the repo is ever made public, the risk changes character — a leak becomes indexed and cached rather than merely committed. Moving the vault out is the right response, and must happen before the first real document lands, not after.
- The separation stands in every other respect: no agent hardcodes a path, the system repo is independently cloneable, and a colleague gets the code with none of the data.

## Alternatives considered

**Separate private git repo at `~/LifeOS-Vault`** — recommended and not chosen. It makes definition-of-done #6 structural rather than hook-enforced, and adds version history and rollback for ledgers and reports. Remains a one-line change if the user reconsiders.

**Outside the repo, no git** — safe from leaks, no history or rollback. Rejected as strictly worse than the private-repo option.

**Encrypted vault at rest** — orthogonal and worth revisiting; full-disk encryption already covers the main threat, and per-file encryption would break the hand-editability the whole design rests on.
