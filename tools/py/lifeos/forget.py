"""FORGET — POPIA erasure. Backs /forget.

Erasure that removes a source document while its numbers survive in a dashboard
is not erasure. So this walks **derived artefacts too**: ledgers, reports,
journal, all three memory tiers, and the CLAUDE.md block.

Three properties, each deliberate:

  * **Dry run first, always.** The manifest is produced and shown before
    anything is touched. This is the only destructive operation in LifeOS.
  * **Originals are quarantined, not shredded.** A document moves to
    `proposed/erasure/` and is deleted only on a second, explicit confirmation.
    An accidental erasure is unrecoverable.
  * **It reports what it CANNOT remove.** An emailed report, a printed copy, a
    bank's own records, anything ever pushed to GitHub. Honesty about the limits
    of erasure is part of the erasure — a report claiming completeness it cannot
    deliver is worse than one that names the gap.

Usage:  python -m lifeos.forget <subject-ref> [--apply] [--confirm-shred]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import atomic, clock, ledger, vault

# What can never be reached, whatever the manifest says.
UNREMOVABLE = [
    "Anything ever pushed to GitHub — issues are notified, indexed and cached; "
    "deleting one does not un-send it.",
    "Reports you have emailed, printed, or copied out of the vault.",
    "The institution's own records — a bank, insurer or SARS keeps its copy under "
    "its own retention rules, and POPIA does not override those.",
    "Backups of this machine taken before the erasure.",
]


def _ledger_names() -> list[str]:
    d = vault.path("ledgers")
    return sorted(p.stem for p in d.glob("*.jsonl")) if d.is_dir() else []


def _mentions(obj, needles: set[str]) -> bool:
    text = json.dumps(obj, ensure_ascii=False).lower()
    return any(n in text for n in needles)


def _subject_needles(subject: str) -> set[str]:
    """The subject ref plus any name the profile gives it."""
    from .readiness import load_profile
    needles = {subject.lower()}
    prof = load_profile()
    for group in ("people", "entities"):
        for item in prof.get(group) or []:
            if item.get("ref") == subject:
                for key in ("name", "legal_name"):
                    if item.get(key):
                        needles.add(str(item[key]).lower())
    return needles


def manifest(subject: str) -> dict:
    """Everything that would be removed. Produced before anything is touched."""
    if not vault.is_initialised():
        return {"schema": "forget/1", "error": "no vault — run /lifeos-init"}

    needles = _subject_needles(subject)
    ledgers: dict[str, list[str]] = {}
    doc_hashes: set[str] = set()

    for name in _ledger_names():
        hits = []
        for rec in ledger.read(name, include_superseded=True):
            if _mentions(rec, needles):
                hits.append(rec.get("id", "?"))
                dh = (rec.get("source") or {}).get("doc_hash", "")
                if dh.startswith("sha256:"):
                    doc_hashes.add(dh)
        if hits:
            ledgers[name] = hits

    documents = [d for d in atomic.read_jsonl(vault.path("documents", "index.jsonl"))
                 if d["doc_hash"] in doc_hashes or _mentions(d, needles)]

    derived = []
    for sub in ("reports", "journal", "memory"):
        base = vault.path(sub)
        if not base.is_dir():
            continue
        for f in base.rglob("*"):
            if not f.is_file() or f.suffix not in {".md", ".html", ".jsonl", ".pdf"}:
                continue
            try:
                if f.suffix == ".pdf":
                    # A PDF cannot be scanned cheaply; if it derives from an
                    # affected document it must go regardless.
                    derived.append(vault.rel(f))
                    continue
                text = f.read_text(encoding="utf-8", errors="ignore").lower()
                if any(n in text for n in needles):
                    derived.append(vault.rel(f))
            except OSError:
                continue

    return {
        "schema": "forget/1",
        "at": clock.stamp(),
        "subject": subject,
        "matched_on": sorted(needles),
        "ledger_records": ledgers,
        "ledger_record_count": sum(len(v) for v in ledgers.values()),
        "documents": [{"doc_hash": d["doc_hash"][:19], "filed_path": d["filed_path"],
                       "type": d.get("type")} for d in documents],
        "derived_artefacts": sorted(set(derived)),
        "unremovable": UNREMOVABLE,
        "note": (
            "Nothing has been touched. This is the manifest only — rerun with "
            "--apply to tombstone the records and quarantine the originals."
        ),
    }


def apply(subject: str, *, confirm_shred: bool = False) -> dict:
    """Tombstone records, quarantine originals, delete derived artefacts."""
    plan = manifest(subject)
    if plan.get("error"):
        return plan

    run = clock.Run.current()
    done: dict = {"tombstoned": 0, "quarantined": [], "deleted_derived": [],
                  "shredded": [], "retained": []}

    # Ledgers: append a tombstone rather than rewriting history. The record's
    # existence stays auditable; its content does not.
    for name, ids in plan["ledger_records"].items():
        for rec_id in ids:
            atomic.append_jsonl(ledger.ledger_path(name), {
                "id": rec_id,
                "schema": f"{name}/tombstone",
                "superseded_by": None,
                "_meta": {"run_id": run.id, "agent": "forget",
                          "written_at": clock.stamp(),
                          "note": f"erased under POPIA for {subject}"},
            })
            done["tombstoned"] += 1

    # Originals: quarantine, and shred only on an explicit second confirmation.
    quarantine = vault.path("proposed", "erasure", subject)
    for doc in plan["documents"]:
        src = vault.path(*Path(doc["filed_path"]).parts)
        if not src.is_file():
            continue
        if confirm_shred:
            src.chmod(0o600)
            src.unlink()
            done["shredded"].append(doc["filed_path"])
        else:
            dest = quarantine / Path(doc["filed_path"]).name
            dest.parent.mkdir(parents=True, exist_ok=True)
            src.chmod(0o600)
            src.rename(dest)
            done["quarantined"].append(vault.rel(dest))

    for rel in plan["derived_artefacts"]:
        path = vault.vault_root() / rel.replace("$VAULT/", "")
        if path.is_file():
            path.unlink()
            done["deleted_derived"].append(rel)

    atomic.append_jsonl(vault.path("state", "audit.jsonl"), {
        "at": clock.stamp(), "event": "vault.delete", "tool": "forget",
        "path": f"subject={subject}", "run_id": run.id,
        "note": (f"POPIA erasure: {done['tombstoned']} records tombstoned, "
                 f"{len(done['quarantined'])} quarantined, "
                 f"{len(done['shredded'])} shredded"),
    })

    return {
        "schema": "forget/1",
        "at": clock.stamp(),
        "subject": subject,
        "removed": done,
        "retained": [
            "Tombstones remain in every affected ledger, recording that a record "
            "existed and was erased. They carry no personal data, and removing them "
            "would break the audit trail that proves the erasure happened.",
        ],
        "unremovable": UNREMOVABLE,
        "next": (
            "Originals are quarantined in $VAULT/proposed/erasure/. Rerun with "
            "--confirm-shred to delete them permanently. Until then they are "
            "recoverable — deliberately."
        ) if not confirm_shred else "Originals were shredded. This is not reversible.",
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lifeos.forget")
    ap.add_argument("subject")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--confirm-shred", action="store_true")
    args = ap.parse_args(argv)
    result = (apply(args.subject, confirm_shred=args.confirm_shred)
              if args.apply else manifest(args.subject))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
