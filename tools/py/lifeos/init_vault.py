"""Scaffold a vault. Backs /lifeos-init.

Refuses to overwrite an existing vault — re-running offers amend or scaffold
elsewhere, but never clobbers.  Usage:

    python -m lifeos.init_vault [--example] [--force-empty-dir]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import atomic, clock, vault

PROFILE_TEMPLATE = """\
# LifeOS profile — who you are and how the system should behave.
# Hand-edit this freely. It is round-tripped with ruamel.yaml, so your comments
# and ordering survive every automated update.
schema: profile/1

jurisdiction: za
currency: ZAR
fiscal_year_end: "02-28"        # last day of Feb; leap years handled automatically
timezone: Africa/Johannesburg

people: []                       # per_<slug> entries — /lifeos-init interviews you
entities: []                     # ent_<slug> entries

communication:
  report_length: short           # short | normal | full
  tone: direct
  language: en-ZA

domains:                         # disable a domain and it degrades to
  identity: true                 # "not tracked" with an explicit note —
  living: false                  # it never breaks the graph
  finance: false
  insurance: false
  investments: false
  assets: false
  tax: false
  estate: false
  trusts: false
  final-wishes: false
  readiness: false

packs: []                        # trusts | sme-owner | expat | phd-researcher | landlord

heartbeat:
  max_items: 5                   # a heartbeat may leave work queued; that is normal
  max_waves: 4                   # depth becomes waves, not stack frames
  quiet_journal: true            # a quiet run writes one line, not a page

thresholds:
  variance_pct: 15               # budget breach raises variance.breach
  agent_overload:                # meta-architect proposes promoting a specialist
    avg_duration_ms: 120000      # when these are crossed
    failures_recent: 3
    open_loops: 10

github:
  enabled: true
  autofile: false                # true files issues without asking. Only sensible
                                 # for a PRIVATE system repo — an issue body is
                                 # publication, and it cannot be un-sent.
  priority_ceiling: 3            # system work never outranks a tax deadline

finance:
  category_floor: 0.90           # below this a transaction lands UNCATEGORISED
                                 # with a question, never guessed into a bucket
"""

CURSORS_TEMPLATE = {
    "schema": "cursors/1",
    "inbox": {},
    "cadence": {},
    "ledgers": {},
    "rules": {},
    "github": {},
}

QUEUE_TEMPLATE = {"schema": "queue/1", "updated_at": None, "items": []}

READMES = {
    "inbox": (
        "# inbox/\n\n"
        "**Drop documents here. This is the only thing you do manually.**\n\n"
        "Bank statements, policy schedules, medical aid certificates, tax certificates,\n"
        "wills, trust deeds, payslips, invoices — any format.\n\n"
        "`/heartbeat` or `/ingest` classifies each one, files an immutable original\n"
        "under `documents/`, and routes it to the domain that owns it.\n\n"
        "Nothing here is ever deleted by the system. A file that cannot be classified\n"
        "stays put with a gap record explaining why.\n"
    ),
    "proposed": (
        "# proposed/\n\n"
        "**Everything waiting on you.**\n\n"
        "Agents read, analyse, recommend and draft. They do not send, submit,\n"
        "transact or delete. Anything irreversible or externally visible lands here\n"
        "and waits.\n\n"
        "- `issues/` — GitHub issue drafts. `/issues push` files the approved ones.\n"
        "- `rejected/` — records that failed schema validation, with the error.\n"
        "- `low-confidence/` — extractions below the ledger's confidence floor.\n"
    ),
    "documents": (
        "# documents/\n\n"
        "**Filed originals. Immutable.**\n\n"
        "`documents/<year>/<domain>/<hash>-<slug>.<ext>`\n\n"
        "Never modified, never overwritten, never deleted — a `PreToolUse` hook\n"
        "blocks writes here. `index.jsonl` is the searchable index.\n\n"
        "Every number in every report traces back to a page of a file in this\n"
        "directory. That is what makes `/audit` possible.\n"
    ),
    "journal": (
        "# journal/\n\n"
        "One file per day: what the system did, what it means, what's next, and\n"
        "what it needs from you. Written by the orchestrator at REFLECT.\n\n"
        "A quiet day is one line. That is correct, not a failure.\n"
    ),
    "memory": (
        "# memory/\n\n"
        "Three tiers, owned by `memory-keeper`, all hand-editable — you are\n"
        "expected to edit them, and `/consolidate` must preserve your edits.\n\n"
        "- `short/` — this session and the last 7 days\n"
        "- `medium/` — about 90 days: active projects, pending deadlines, promises\n"
        "- `long/` — durable: preferences, standing instructions, decisions, patterns\n\n"
        "`audit.jsonl` records every promotion, demotion and expiry, so memory is\n"
        "never a black box.\n"
    ),
}


def scaffold(root: Path, *, example: bool = False) -> dict:
    created: list[str] = []

    for sub in vault.SUBDIRS:
        d = root / sub
        if not d.is_dir():
            d.mkdir(parents=True, exist_ok=True)
            created.append(f"{sub}/")

    profile = root / "profile" / "profile.yaml"
    if not profile.exists():
        atomic.write_text(profile, PROFILE_TEMPLATE)
        created.append("profile/profile.yaml")

    cursors = root / "state" / "cursors.json"
    if not cursors.exists():
        atomic.write_json(cursors, CURSORS_TEMPLATE)
        created.append("state/cursors.json")

    queue = root / "state" / "queue.json"
    if not queue.exists():
        q = dict(QUEUE_TEMPLATE)
        q["updated_at"] = clock.stamp()
        atomic.write_json(queue, q)
        created.append("state/queue.json")

    for name, body in READMES.items():
        f = root / name / "README.md"
        if not f.exists():
            atomic.write_text(f, body)
            created.append(f"{name}/README.md")

    # Keep otherwise-empty directories present in a fresh clone.
    for sub in ("ledgers", "reports", "state/agents", "state/system",
                "memory/short", "memory/medium", "memory/long", "proposed/issues"):
        keep = root / sub / ".gitkeep"
        if not keep.exists():
            keep.touch()

    return {"root": str(root), "created": created, "count": len(created)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lifeos.init_vault")
    ap.add_argument("--example", action="store_true", help="scaffold vault.example/ instead of the real vault")
    ap.add_argument("--path", help="explicit target (overrides both)")
    args = ap.parse_args(argv)

    if args.path:
        root = Path(args.path).expanduser().resolve()
    elif args.example:
        root = vault.repo_root() / "vault.example"
    else:
        root = vault.vault_root()

    already = (root / "profile" / "profile.yaml").is_file()
    result = scaffold(root, example=args.example)
    result["already_initialised"] = already
    if already:
        result["note"] = (
            "Vault already initialised — existing files were left untouched. "
            "Missing directories were created."
        )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
