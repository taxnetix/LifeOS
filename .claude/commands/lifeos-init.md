---
description: Interview the user, scaffold the vault, write the profile, select packs, set cadences.
allowed-tools: Bash, Read, Write, Edit, AskUserQuestion
---

# /lifeos-init

Bootstrap a vault. **Never overwrite an existing one.**

## Step 1 — check

!`.venv/bin/python -m lifeos.vault`

If `$VAULT/profile/profile.yaml` already exists, do **not** proceed silently. Offer:
- **amend** the existing profile, or
- scaffold **elsewhere** via `$LIFEOS_VAULT`.

## Step 2 — interview

Ask with `AskUserQuestion`, in this order. Keep it short — this is the first minute of the system's life, and a 40-question interrogation is how people abandon it. Everything unasked becomes a gap record, which is a perfectly good outcome.

1. **People** — self, spouse, children, dependants, parents. Names and roles only. *ID numbers come later, from documents.*
2. **Entities** — companies, CCs, trusts. Names and forms.
3. **Domains** — which to enable now. Recommend starting with `identity` + `readiness`, then `finance`. A disabled domain degrades to "not tracked"; it never breaks anything.
4. **Packs** — `trusts`, `sme-owner`, `expat`, `phd-researcher`, `landlord`.
5. **Communication** — report length, tone, language.
6. **GitHub** — enable the system backlog? If the repo is **public**, keep `autofile: false`; an issue body is publication and cannot be un-sent.

## Step 3 — scaffold

!`.venv/bin/python -m lifeos.init_vault`

Then edit `$VAULT/profile/profile.yaml` with the interview answers. Preserve the comments in that file — the user is meant to read and edit it.

## Step 4 — install the leak guard

```bash
bash tools/scripts/install-hooks.sh
```

Explain plainly: `.gitignore` is advisory, this hook is not, and `--no-verify` must never be used.

## Step 5 — hand over

Report what was created, then tell them exactly one next step: **drop a document in `$VAULT/inbox/` and run `/heartbeat`.**

## Rules

- Confirm the vault path and pack selection **before** writing anything.
- Never invent a person, entity or number. Unknown → leave it out and record a gap.
- Never ask for a password, PIN, safe code or account credential. LifeOS stores *pointers*, never secrets.
- Do not ask for ID numbers in the interview. They arrive with documents, carrying provenance.
