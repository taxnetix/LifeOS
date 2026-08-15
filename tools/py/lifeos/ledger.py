"""Ledger read/write with schema validation and deterministic identity.

Two rules are enforced here rather than trusted to callers:

  1. A record that fails schema validation is NEVER written to a ledger.  It
     goes to proposed/rejected/ with the validation error attached.
  2. Identity is derived from origin, not assigned:
         id = sha256(doc_hash | locator | natural_key)
     so re-ingesting the same document is a byte-identical no-op.  This — not
     cleverness in the agent — is what prevents redone work.

See docs/adr/0006-deterministic-record-ids.md and 0012-schema-versioning.md.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from . import atomic, clock, vault

SCHEMA_DIR = vault.repo_root() / "templates" / "schemas"
SCHEMA_BASE = "https://lifeos.local/schemas"

# Ledgers whose records must clear this confidence before they may be written.
# Below the floor the record goes to proposed/, never to the ledger.
CONFIDENCE_FLOOR: dict[str, float] = {
    "transactions": 0.90,
    "policies": 0.85,
    "holdings": 0.85,
    "liabilities": 0.85,
    "tax-events": 0.90,
    "_default": 0.70,
}


class ValidationFailed(ValueError):
    def __init__(self, ledger: str, errors: list[str]) -> None:
        super().__init__(f"{ledger}: " + "; ".join(errors))
        self.ledger = ledger
        self.errors = errors


@cache
def _schema_store() -> dict[str, dict]:
    """Every schema keyed by $id, so cross-file $refs resolve entirely offline."""
    store: dict[str, dict] = {}
    for f in SCHEMA_DIR.rglob("*.json"):
        doc = json.loads(f.read_text(encoding="utf-8"))
        if "$id" in doc:
            store[doc["$id"]] = doc
    return store


@cache
def _registry() -> Registry:
    store = _schema_store()
    return Registry().with_resources(
        (sid, Resource.from_contents(doc, default_specification=DRAFT202012))
        for sid, doc in store.items()
    )


@cache
def validator_for(ledger: str) -> Draft202012Validator:
    sid = f"{SCHEMA_BASE}/ledgers/{ledger}.schema.json"
    store = _schema_store()
    if sid not in store:
        raise KeyError(f"no schema for ledger '{ledger}' (expected {sid})")
    return Draft202012Validator(store[sid], registry=_registry())


def validate(ledger: str, record: dict) -> list[str]:
    """Return a list of human-readable errors; empty means valid."""
    v = validator_for(ledger)
    return [
        f"{'/'.join(str(x) for x in e.path) or '<root>'}: {e.message}"
        for e in sorted(v.iter_errors(record), key=lambda e: list(e.path))
    ]


def record_id(doc_hash: str, locator: str, natural_key: str) -> str:
    """Deterministic identity. Same origin + same key -> same id, always."""
    payload = f"{doc_hash}|{locator}|{natural_key}".encode()
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def ledger_path(ledger: str) -> Path:
    return vault.path("ledgers", f"{ledger}.jsonl")


def read(ledger: str, *, include_superseded: bool = False) -> Iterator[dict]:
    """Yield live records. Superseded records are hidden unless asked for."""
    for rec in atomic.read_jsonl(ledger_path(ledger)):
        if not include_superseded and rec.get("superseded_by"):
            continue
        yield rec


def existing_ids(ledger: str) -> set[str]:
    return {r["id"] for r in atomic.read_jsonl(ledger_path(ledger)) if "id" in r}


def confidence_floor(ledger: str) -> float:
    return CONFIDENCE_FLOOR.get(ledger, CONFIDENCE_FLOOR["_default"])


def write(
    ledger: str,
    records: list[dict],
    *,
    agent: str,
    run_id: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Append records to a ledger.

    Returns counts: written / unchanged / rejected / low_confidence.

    - unchanged        id already present — the no-op that makes /heartbeat
                       idempotent under re-ingestion.
    - rejected         failed schema validation -> proposed/rejected/
    - low_confidence   below the ledger's floor  -> proposed/low-confidence/
    """
    run_id = run_id or clock.Run.current().id
    written = unchanged = 0
    rejected: list[dict] = []
    low_conf: list[dict] = []
    seen = existing_ids(ledger)
    floor = confidence_floor(ledger)
    target = ledger_path(ledger)

    for rec in records:
        rec = dict(rec)
        rec.setdefault("_meta", {})
        rec["_meta"].update({"run_id": run_id, "agent": agent, "written_at": clock.stamp()})
        rec.setdefault("valid_to", None)
        rec.setdefault("superseded_by", None)

        errors = validate(ledger, rec)
        if errors:
            rejected.append({"record": rec, "errors": errors})
            continue

        if float(rec["source"]["confidence"]) < floor:
            low_conf.append({"record": rec, "floor": floor})
            continue

        if rec["id"] in seen:
            unchanged += 1
            continue

        if not dry_run:
            atomic.append_jsonl(target, rec)
        seen.add(rec["id"])
        written += 1

    if not dry_run:
        _park(rejected, "rejected", ledger, run_id)
        _park(low_conf, "low-confidence", ledger, run_id)

    return {
        "ledger": ledger,
        "written": written,
        "unchanged": unchanged,
        "rejected": len(rejected),
        "low_confidence": len(low_conf),
        "rejected_detail": [r["errors"] for r in rejected][:10],
    }


def _park(items: list[dict], bucket: str, ledger: str, run_id: str) -> None:
    """A record we will not write still has to go somewhere visible — silence
    is the one outcome that is never acceptable."""
    if not items:
        return
    out = vault.path("proposed", bucket, f"{ledger}-{run_id}.jsonl")
    for item in items:
        atomic.append_jsonl(out, item)


def supersede(ledger: str, old_id: str, new_record: dict, *, agent: str, run_id: str | None = None) -> dict:
    """Correct a record by appending a replacement and a tombstone.

    Records are never mutated, so history stays complete and auditable.
    """
    run_id = run_id or clock.Run.current().id
    result = write(ledger, [new_record], agent=agent, run_id=run_id)
    if result["written"]:
        atomic.append_jsonl(
            ledger_path(ledger),
            {
                "id": old_id,
                "schema": f"{ledger}/tombstone",
                "superseded_by": new_record["id"],
                "_meta": {"run_id": run_id, "agent": agent, "written_at": clock.stamp()},
            },
        )
    return result
