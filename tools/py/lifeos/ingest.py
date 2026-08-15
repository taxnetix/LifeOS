"""INGEST — inbox sweep to filed, indexed, routed originals. Backs /ingest.

    inbox/  ->  hash  ->  extract  ->  classify  ->  file immutably  ->  index  ->  route

Three properties this module exists to guarantee:

  * **An original is never lost.** Files are COPIED, the copy's hash is verified
    against the source, and only then is it considered filed. The inbox copy is
    left for the human to delete — this tool never deletes anything.

  * **Re-ingestion is a no-op.** Identity is the content hash, so a file that is
    already in the index is skipped without re-extraction, whatever it is named.

  * **Nothing is silently dropped.** Unreadable, unsupported or unclassifiable
    files stay in the inbox and produce a gap record explaining why.

Usage:  python -m lifeos.ingest [--dry-run] [--path FILE]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path

from . import atomic, classify, clock, extract, vault

INDEX = ("documents", "index.jsonl")
_IGNORE = {".DS_Store", ".gitkeep", "README.md"}


def _slug(name: str, limit: int = 48) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", Path(name).stem.lower()).strip("-")
    return (s[:limit].rstrip("-") or "document")


def _filing_year(period: dict | None) -> str:
    """The document's OWN year, not today's.

    A July 2026 statement ingested in August 2026 belongs under 2026/; one
    ingested in 2028 still belongs under 2026/.
    """
    if period and period.get("to"):
        try:
            return str(date.fromisoformat(period["to"]).year)
        except ValueError:
            pass
    return str(date.today().year)


def _indexed_hashes() -> dict[str, dict]:
    return {r["doc_hash"]: r for r in atomic.read_jsonl(vault.path(*INDEX)) if "doc_hash" in r}


def _gap(kind: str, detail: str, *, run_id: str, blocking: bool = False,
         consequence: str = "moderate", domain: str = "unclassified") -> dict:
    rec = {
        "id": f"sha256:{hashlib.sha256(f'{kind}|{detail}'.encode()).hexdigest()}",
        "kind": kind,
        "domain": domain,
        "detail": detail,
        "blocking": blocking,
        "consequence": consequence,
        "opened_run": run_id,
        "opened_at": clock.stamp(),
        "agent": "librarian",
    }
    atomic.append_jsonl(vault.path("state", "gaps.jsonl"), rec)
    return rec


def ingest_file(path: Path, *, run_id: str, known: dict[str, dict], dry_run: bool = False) -> dict:
    """Process one inbox file. Never raises; every outcome is reported."""
    result: dict = {"source": vault.rel(path), "status": "unknown"}

    try:
        doc_hash = extract.sha256_file(path)
    except OSError as e:
        result.update(status="unreadable", error=str(e))
        if not dry_run:
            _gap("document.unreadable", f"{vault.rel(path)}: {e}", run_id=run_id)
        return result

    result["doc_hash"] = doc_hash

    if doc_hash in known:
        # The identity check that makes /ingest idempotent — same content under
        # any filename is the same document.
        result.update(status="duplicate", filed_path=known[doc_hash].get("filed_path"))
        return result

    if extract.kind_of(path) is None:
        result.update(status="unsupported")
        if not dry_run:
            _gap("document.unreadable",
                 f"{vault.rel(path)}: no extractor for '{path.suffix}'",
                 run_id=run_id)
        return result

    ext = extract.extract(path)
    result["method"] = ext.method
    result["ocr"] = ext.ocr
    result["pages"] = ext.pages
    result["extract_errors"] = ext.errors

    if not ext.blocks and not ext.tables:
        result["status"] = "unreadable"
        if not dry_run:
            _gap("document.unreadable",
                 f"{vault.rel(path)}: extraction produced nothing ({'; '.join(ext.errors) or 'no content'})",
                 run_id=run_id, consequence="severe")
        return result

    cls = classify.classify(ext.text, filename=path.name)
    result["type"] = cls.type
    result["domain"] = cls.domain
    result["classification"] = {"score": cls.score, "reason": cls.reason,
                                "runner_up": cls.runner_up, "matched": cls.matched}

    if cls.type == "unclassified":
        result["status"] = "unclassified"
        if not dry_run:
            kind = "document.type.unseen" if cls.unseen else "document.missing"
            _gap("document.unreadable" if not cls.unseen else "document.unreadable",
                 f"{vault.rel(path)}: {cls.reason}", run_id=run_id)
            result["gap_kind"] = kind
        return result

    year = _filing_year(cls.period)
    filed_rel = Path("documents") / year / cls.domain / f"{doc_hash[7:19]}-{_slug(path.name)}{path.suffix.lower()}"
    filed_abs = vault.path(*filed_rel.parts)
    result["filed_path"] = str(filed_rel)

    if dry_run:
        result["status"] = "would_file"
        return result

    filed_abs.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, filed_abs)

    # Verify the copy before declaring it filed. A truncated copy that we then
    # told the human was safe would be the worst possible failure here.
    if extract.sha256_file(filed_abs) != doc_hash:
        filed_abs.unlink(missing_ok=True)
        result.update(status="copy_failed")
        _gap("document.unreadable",
             f"{vault.rel(path)}: filed copy hash mismatch; not filed",
             run_id=run_id, blocking=True, consequence="severe")
        return result

    filed_abs.chmod(0o444)  # read-only: originals are immutable

    atomic.append_jsonl(vault.path(*INDEX), {
        "doc_hash": doc_hash,
        "original_path": vault.rel(path).replace("$VAULT/", ""),
        "filed_path": str(filed_rel),
        "type": cls.type,
        "domain": cls.domain,
        "period": cls.period,
        "pages": ext.pages,
        "ocr": ext.ocr,
        "bytes": filed_abs.stat().st_size,
        "method": ext.method,
        "ingested_at": clock.stamp(),
        "run_id": run_id,
        "checksum_verified_at": clock.stamp(),
    })

    result.update(status="filed", routes_to=cls.routes_to, period=cls.period)
    return result


def sweep(*, dry_run: bool = False, only: Path | None = None) -> dict:
    run = clock.Run.current()
    inbox = vault.path("inbox")
    out: dict = {
        "schema": "ingest/1",
        "run_id": run.id,
        "at": clock.stamp(),
        "dry_run": dry_run,
        "results": [],
    }

    if not vault.is_initialised():
        out["error"] = "no vault — run /lifeos-init"
        return out
    if not inbox.is_dir():
        out["error"] = "no inbox directory"
        return out

    known = _indexed_hashes()
    files = [only] if only else sorted(
        f for f in inbox.rglob("*")
        if f.is_file() and f.name not in _IGNORE and not f.name.startswith(".")
    )

    for f in files:
        res = ingest_file(f, run_id=run.id, known=known, dry_run=dry_run)
        if res.get("status") == "filed":
            known[res["doc_hash"]] = res
        out["results"].append(res)

    counts: dict[str, int] = {}
    for r in out["results"]:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    out["counts"] = counts
    out["routes"] = sorted({r["routes_to"] for r in out["results"] if r.get("routes_to")})
    out["needs_human"] = [
        {"path": r["source"], "status": r["status"],
         "reason": r.get("classification", {}).get("reason") or r.get("error", "")}
        for r in out["results"]
        if r["status"] in {"unclassified", "unreadable", "unsupported", "copy_failed"}
    ]
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lifeos.ingest")
    ap.add_argument("--dry-run", action="store_true", help="classify and report; file nothing")
    ap.add_argument("--path", help="ingest one file instead of sweeping the inbox")
    args = ap.parse_args(argv)
    print(json.dumps(
        sweep(dry_run=args.dry_run, only=Path(args.path) if args.path else None),
        indent=2, ensure_ascii=False,
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
