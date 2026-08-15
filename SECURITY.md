# Security

Read this before you put real documents in a vault.

## Threat model

LifeOS holds, for one household and its businesses: identity numbers, bank and policy numbers, medical scheme membership, asset registers, trust deeds, wills, and the location of physical originals. That is a complete identity-theft kit and a map of an estate.

The threats it is designed against, in order of likelihood:

| # | Threat | Control |
|---|---|---|
| 1 | **Accidental commit** of vault content to a shared repo | `.gitignore` + a pre-commit hook that is not advisory |
| 2 | **Accidental exfiltration** by an agent doing a helpful web lookup | `PreToolUse` guard on every egress channel |
| 3 | **A published GitHub issue** containing personal data | same guard, plus a human gate on filing |
| 4 | **Loss of the Life File** as a physical document | audience tiering; no secrets at any tier |
| 5 | **Silent corruption** — a wrong number nobody can trace | provenance on every record; `/audit` |
| 6 | Device theft | out of scope — use full-disk encryption |
| 7 | A determined attacker with local access | out of scope |

## Controls

### The vault never enters git

`vault/` is git-ignored. **`.gitignore` is advisory** — `git add -f`, an edited `.gitignore`, or `git stash -u` each defeat it, and git history cannot be un-rung.

The hard control is `.claude/hooks/pre-commit`. Install it once per clone:

```bash
bash tools/scripts/install-hooks.sh
```

It refuses any commit that stages a path under `vault/`, and greps staged diffs for SA ID patterns, long digit runs, credential shapes, and proper names from your live profile.

**Never use `git commit --no-verify`.** It is denied in `.claude/settings.json`, and that denial is there because bypassing this hook once is enough to make definition-of-done #6 permanently false.

### Nothing personal leaves the machine

`.claude/hooks/pii-guard.py` runs on `PreToolUse` for `WebFetch`, `WebSearch`, and `Bash` commands matching `gh`, `curl`, `wget`, `nc`, `ssh`, `scp`, `rsync`.

The matcher is built from your **live profile**, not a static list — a static regex set would miss the names that matter most, which are your own. It blocks SA ID numbers, long digit runs, email addresses, credential shapes, and every proper name and identifier in `profile.yaml`.

On ambiguity it **blocks**. A rewritten query costs seconds; a leak cannot be undone. If the guard itself crashes, it **fails closed**.

Every block is logged to `$VAULT/state/audit.jsonl` with the matched pattern *class* — never the matched value, because a redaction log containing the redacted values would defeat itself.

Verify it yourself:

```bash
echo '{"tool_name":"WebSearch","tool_input":{"query":"tax for 8801015800086"}}' | .venv/bin/python .claude/hooks/pii-guard.py
```

### Originals are immutable

Files under `$VAULT/documents/` are never modified, overwritten or deleted — a hook blocks it. Every figure in every report traces back to one of them, so mutating one would silently invalidate history.

### Secrets are never stored

LifeOS records **where a credential lives**, never what it is: `"1Password/Personal/FNB Online"`. The schema rejects values resembling a password, key or seed phrase. Household access records store the custodian and where the code is documented, never the code.

If you find a secret in a ledger, that is a bug — report it.

### Human gates

Agents read, analyse, recommend and draft. They do **not** send email, submit forms, transact, publish, or delete originals. Anything irreversible lands in `$VAULT/proposed/` and waits.

Filing a GitHub issue is publication and is gated by default. `github.autofile: true` opts out — sensible only for a **private** repo.

## Known limitations

State these plainly, because a control you overestimate is worse than one you know is weak.

1. **The vault lives inside the repo.** By configuration, at `./vault/`. The hook is a real control, but a separate private repository would make the guarantee structural rather than enforced. Moving it is one `$LIFEOS_VAULT` change — do it before the first real document lands, not after. [ADR-0008](docs/adr/0008-vault-location-and-separation.md)

2. **Redaction can only guard channels it knows about.** A new egress mechanism must be added to the matcher. `/selftest` includes a live block test so a broken guard fails the suite rather than failing open.

3. **False positives are expected.** A common surname in your profile will block innocuous queries. Rewrite the query; do not disable the guard.

4. **Anything that reaches GitHub is unremovable.** Deleting an issue does not un-send the notification, the index or the cache. `/forget` reports GitHub content as unremovable and tells you to treat it as disclosed.

5. **The vault is not encrypted at rest.** It relies on full-disk encryption. Per-file encryption would break the hand-editability the whole design rests on.

6. **A printed Life File has no controls at all.** This is why it is tiered: the copy most likely to be lying around discloses almost nothing. [ADR-0018](docs/adr/0018-life-file-document.md)

7. **LifeOS is not professional advice.** It prepares you to have a sharper conversation with a registered financial advisor, tax practitioner, attorney or the Master's Office. It never replaces one.

## POPIA

Purpose limitation and minimality are design constraints. Every data category in [docs/data-dictionary.md](docs/data-dictionary.md) carries a documented erasure path covering **derived artefacts** as well as source records — deleting a document while its numbers survive in a dashboard is not erasure.

`/forget <subject>` executes it, dry-run first, and reports three things: what it removed, what it retained and under which legal basis, and what it **could not** remove. Honesty about the limits of erasure is part of the erasure.

## Reporting a problem

Found a way to get personal data out of a vault, or into git history? Open a GitHub issue describing **the mechanism, with no personal data in it** — the same rule the agents follow.
