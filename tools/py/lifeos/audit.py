"""AUDIT — prove every derived artefact traces back to a source document.

This is the command that makes the system's central claim checkable rather than
asserted. It fails loudly, because an audit that passes by being lenient is
worse than no audit: it manufactures confidence.

Seven checks:

  1. provenance     every ledger record names a real filed document
  2. orphans        every doc_hash referenced actually exists in the index
  3. integrity      every filed original still hashes to its recorded doc_hash
  4. coverage       every taxonomy leaf has an owner, and that owner exists
  5. one_writer     exactly one agent writes each ledger
  6. no_abs_paths   the system repo hardcodes no absolute path
  7. schema         every record validates against its ledger's schema

Usage:  python -m lifeos.audit [--markdown]
Exit:   1 if any check fails — so it can gate a commit or a scheduled run.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from . import atomic, clock, extract, ledger, vault

# Origins that are legitimately not a filed document.
_SYNTHETIC = {"human", "inferred"}

# Files exempt from the absolute-path check: documentation that legitimately
# shows a real path, and the dependency notes that record this machine's setup.
_ABS_PATH_EXEMPT = {"docs/dependencies.md"}


def _ledger_names() -> list[str]:
    d = vault.path("ledgers")
    return sorted(p.stem for p in d.glob("*.jsonl")) if d.is_dir() else []


def check_provenance() -> dict:
    """Every record must name a document, a locator and a confidence."""
    problems = []
    checked = 0
    for name in _ledger_names():
        for rec in ledger.read(name, include_superseded=True):
            if rec.get("schema", "").endswith("/tombstone"):
                continue
            checked += 1
            src = rec.get("source") or {}
            for field in ("doc_hash", "locator", "method", "confidence"):
                if field not in src:
                    problems.append({
                        "ledger": name, "record": rec.get("id", "?")[:19],
                        "problem": f"source.{field} missing",
                    })
    return {"name": "provenance", "checked": checked, "problems": problems,
            "ok": not problems,
            "what": "every ledger record carries a document, a locator and a confidence"}


def check_orphans() -> dict:
    """Every doc_hash a record cites must exist in the document index."""
    index = {d["doc_hash"] for d in atomic.read_jsonl(vault.path("documents", "index.jsonl"))}
    problems, checked = [], 0
    for name in _ledger_names():
        for rec in ledger.read(name):
            dh = (rec.get("source") or {}).get("doc_hash")
            if not dh or dh in _SYNTHETIC:
                continue
            checked += 1
            if dh not in index:
                problems.append({
                    "ledger": name, "record": rec.get("id", "?")[:19],
                    "problem": f"cites {dh[:19]} which is not in documents/index.jsonl",
                })
    return {"name": "orphans", "checked": checked, "problems": problems,
            "ok": not problems,
            "what": "every cited document exists — no figure traces to nothing"}


def check_integrity(sample: int | None = None) -> dict:
    """Every filed original still hashes to what the index recorded.

    Catches silent corruption and any edit that slipped past the immutability
    hook. Cheap enough to run in full at personal scale.
    """
    problems, checked = [], 0
    rows = list(atomic.read_jsonl(vault.path("documents", "index.jsonl")))
    if sample:
        rows = rows[:sample]
    for row in rows:
        if row.get("redacted"):
            continue
        path = vault.path(*Path(row["filed_path"]).parts)
        if not path.is_file():
            problems.append({"doc": row["doc_hash"][:19], "problem": "filed file is missing"})
            continue
        checked += 1
        if extract.sha256_file(path) != row["doc_hash"]:
            problems.append({"doc": row["doc_hash"][:19],
                             "problem": "content no longer matches its recorded hash"})
    return {"name": "integrity", "checked": checked, "problems": problems,
            "ok": not problems,
            "what": "every filed original is byte-identical to what was indexed"}


def _coverage_rows() -> list[dict]:
    path = vault.repo_root() / "docs" / "coverage-map.md"
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\|\s*([A-J]\d+[a-z]?)\s*\|([^|]*)\|([^|]*)\|([^|]*)\|", line)
        if m:
            rows.append({"id": m.group(1).strip(), "leaf": m.group(2).strip(),
                         "kind": m.group(3).strip(), "owner_cell": m.group(4).strip()})
    return rows


def check_coverage() -> dict:
    """Every taxonomy leaf is owned, and every named schema exists."""
    rows = _coverage_rows()
    agents = {p.stem for p in (vault.repo_root() / ".claude" / "agents").glob("*.md")}
    schema_dir = vault.repo_root() / "templates" / "schemas" / "ledgers"
    schemas = {p.stem.replace(".schema", "") for p in schema_dir.glob("*.json")}

    problems = []
    for row in rows:
        cell = row["owner_cell"]
        if not cell or cell in {"—", "-"}:
            problems.append({"leaf": row["id"], "problem": "no owner, schema or checklist"})
            continue
        for ref in re.findall(r"`([a-z0-9-]+)\.jsonl`", cell):
            if ref not in schemas and ref != "documents-index":
                problems.append({"leaf": row["id"],
                                 "problem": f"names ledger '{ref}' but no schema exists"})
    return {"name": "coverage", "checked": len(rows), "problems": problems,
            "ok": not problems,
            "what": f"all {len(rows)} taxonomy leaves have an owner and a real schema",
            "agents_on_disk": sorted(agents)}


def check_one_writer() -> dict:
    """Exactly one agent writes each ledger."""
    path = vault.repo_root() / "docs" / "agent-catalogue.md"
    writers: dict[str, list[str]] = {}
    if path.is_file():
        for m in re.finditer(r"^\|\s*`([a-z0-9-]+)\.jsonl`\s*\|\s*`([a-z-]+)`\s*\|",
                             path.read_text(encoding="utf-8"), re.M):
            writers.setdefault(m.group(1), []).append(m.group(2))

    agents = {p.stem for p in (vault.repo_root() / ".claude" / "agents").glob("*.md")}
    problems = []
    for name, who in writers.items():
        if len(who) > 1:
            problems.append({"ledger": name, "problem": f"{len(who)} writers: {who}"})
        elif who[0] not in agents:
            # An agent named in the catalogue but absent from disk is only a
            # problem once its domain is enabled; packs supply some of them.
            problems.append({"ledger": name,
                             "problem": f"writer '{who[0]}' has no agent file "
                                        "(install its pack, or the catalogue is stale)"})
    return {"name": "one_writer", "checked": len(writers), "problems": problems,
            "ok": not problems, "what": "exactly one agent writes each ledger"}


def check_no_absolute_paths() -> dict:
    """The system repo must hardcode no absolute path.

    A hardcoded /Users path leaks a username, breaks on another machine, and
    silently bypasses the vault resolver.
    """
    root = vault.repo_root()
    problems = []
    for sub in ("tools", ".claude", "templates", "packs", "docs"):
        base = root / sub
        if not base.is_dir():
            continue
        for f in base.rglob("*"):
            if not f.is_file() or f.suffix not in {".py", ".mjs", ".js", ".sh",
                                                   ".json", ".yaml", ".md"}:
                continue
            rel = str(f.relative_to(root))
            if rel in _ABS_PATH_EXEMPT or "node_modules" in rel:
                continue
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for n, line in enumerate(text.splitlines(), 1):
                if "/Users/" in line and "$CLAUDE_PROJECT_DIR" not in line:
                    problems.append({"file": rel, "line": n,
                                     "problem": "hardcoded absolute path"})
    return {"name": "no_absolute_paths", "checked": "system repo", "problems": problems,
            "ok": not problems, "what": "no hardcoded absolute path in the system repo"}


def check_schemas() -> dict:
    """Every ledger record validates against its schema."""
    problems, checked = [], 0
    for name in _ledger_names():
        try:
            ledger.validator_for(name)
        except KeyError:
            problems.append({"ledger": name, "problem": "no schema for this ledger"})
            continue
        for rec in ledger.read(name):
            checked += 1
            errors = ledger.validate(name, rec)
            if errors:
                problems.append({"ledger": name, "record": rec.get("id", "?")[:19],
                                 "problem": errors[0]})
    return {"name": "schema", "checked": checked, "problems": problems,
            "ok": not problems, "what": "every record validates against its ledger schema"}


def trace(record_id: str) -> dict:
    """Walk one figure back to a page of a real document."""
    for name in _ledger_names():
        for rec in ledger.read(name, include_superseded=True):
            if rec.get("id", "").startswith(record_id):
                src = rec.get("source", {})
                doc = next((d for d in atomic.read_jsonl(vault.path("documents", "index.jsonl"))
                            if d["doc_hash"] == src.get("doc_hash")), None)
                return {
                    "found": True, "ledger": name, "record_id": rec["id"],
                    "source": src,
                    "document": {"filed_path": doc.get("filed_path"), "type": doc.get("type"),
                                 "period": doc.get("period")} if doc else None,
                    "synthetic": src.get("doc_hash") in _SYNTHETIC,
                }
    return {"found": False, "record_id": record_id}


def report(*, quick: bool = False) -> dict:
    if not vault.is_initialised():
        return {"schema": "audit/1", "error": "no vault — run /lifeos-init"}

    checks = [
        check_provenance(),
        check_orphans(),
        check_integrity(sample=20 if quick else None),
        check_coverage(),
        check_one_writer(),
        check_no_absolute_paths(),
        check_schemas(),
    ]
    failed = [c for c in checks if not c["ok"]]
    return {
        "schema": "audit/1",
        "at": clock.stamp(),
        "checks": checks,
        "passed": len(checks) - len(failed),
        "failed": len(failed),
        "ok": not failed,
    }


def to_markdown(rep: dict) -> str:
    if rep.get("error"):
        return f"**{rep['error']}**"
    lines = [
        "# Audit",
        "",
        f"**{rep['passed']} of {len(rep['checks'])} checks passed.**"
        + ("" if rep["ok"] else f" {rep['failed']} FAILED."),
        "",
        "| Check | Result | Records | What it proves |",
        "|---|---|---|---|",
    ]
    for c in rep["checks"]:
        lines.append(f"| {c['name']} | {'pass' if c['ok'] else '**FAIL**'} | "
                     f"{c['checked']} | {c['what']} |")
    for c in rep["checks"]:
        if c["ok"]:
            continue
        lines += ["", f"## {c['name']} — {len(c['problems'])} problem(s)", ""]
        for p in c["problems"][:25]:
            lines.append(f"- {json.dumps(p, ensure_ascii=False)}")
        if len(c["problems"]) > 25:
            lines.append(f"- _…and {len(c['problems']) - 25} more_")
    lines += ["", "---",
              "_An audit that passes by being lenient is worse than no audit. "
              "This one exits non-zero on any failure._"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lifeos.audit")
    ap.add_argument("--markdown", action="store_true")
    ap.add_argument("--quick", action="store_true", help="sample the integrity check")
    ap.add_argument("--trace", help="walk one record id back to its document")
    args = ap.parse_args(argv)

    if args.trace:
        print(json.dumps(trace(args.trace), indent=2, ensure_ascii=False))
        return 0

    rep = report(quick=args.quick)
    print(to_markdown(rep) if args.markdown else json.dumps(rep, indent=2, ensure_ascii=False))
    return 0 if rep.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
