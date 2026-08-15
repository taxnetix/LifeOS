"""FINANCE — statements to ledgers. The flagship pipeline's write stage.

    filed statement -> parse -> categorise -> accounts + transactions ledgers

Personal and business are kept strictly separate by `entity_id` on every record,
while still rolling up to one consolidated view — that separation is a field, not
a second vault, which is what makes both views possible from one ledger.

Usage:  python -m lifeos.finance [--dry-run] [--doc <hash>]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from . import atomic, categorise, clock, extract, ledger, money, parsers, vault


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:40] or "unknown"


def account_ref(st: parsers.Statement) -> str:
    """Stable account ref. Uses the last 4 digits, never the full number —
    the ref appears in report filenames and log lines."""
    tail = re.sub(r"\D", "", st.account_no or "")[-4:] if st.account_no else ""
    return f"acc_{_slug(st.bank)}{'_' + tail if tail else ''}"


def _envelope(*, rec_id: str, schema: str, subject: str, entity: str | None,
              doc_hash: str, locator: str, method: str, confidence: float,
              valid_from: str) -> dict:
    env = {
        "id": rec_id,
        "schema": schema,
        "subject_id": subject,
        "source": {
            "doc_hash": doc_hash,
            "locator": locator,
            "method": method,
            "confidence": round(confidence, 3),
            "extracted_at": clock.stamp(),
        },
        "valid_from": valid_from,
        "valid_to": None,
        "superseded_by": None,
    }
    if entity:
        env["entity_id"] = entity
    return env


def _subject_for(st: parsers.Statement, profile: dict) -> tuple[str, str | None]:
    """(subject_id, entity_id) for this statement.

    Business statements attach to an entity; personal ones to the `self` person.
    Where the profile cannot answer, a placeholder is used and a gap is opened
    rather than guessing at a real person.
    """
    people = profile.get("people") or []
    entities = profile.get("entities") or []
    if st.is_business and entities:
        # Prefer an operating company. A trust rarely runs the day-to-day
        # trading account, and attaching business turnover to one would
        # misstate both the trust's affairs and the company's.
        operating = [e for e in entities if e.get("form") in {"pty_ltd", "cc", "sole_prop"}]
        ent = (operating or entities)[0]
        ref = ent.get("ref") or f"ent_{_slug(str(ent.get('name', 'entity')))}"
        return ref, ref
    me = next((p for p in people if p.get("relation") == "self"), None)
    if me:
        return me.get("ref") or f"per_{_slug(str(me.get('name', 'self')))}", None
    return "per_unknown", None


def build(*, dry_run: bool = False, only_doc: str | None = None) -> dict:
    from .readiness import load_profile

    run = clock.Run.current()
    out: dict = {"schema": "finance/1", "run_id": run.id, "at": clock.stamp(),
                 "dry_run": dry_run, "statements": [], "totals": {}}

    if not vault.is_initialised():
        out["error"] = "no vault — run /lifeos-init"
        return out

    profile = load_profile()
    index = list(atomic.read_jsonl(vault.path("documents", "index.jsonl")))
    wanted = {"bank_statement", "credit_card_statement", "transaction_export"}
    docs = [d for d in index if d.get("type") in wanted and not d.get("redacted")]
    if only_doc:
        docs = [d for d in docs if d["doc_hash"].startswith(only_doc)]

    history = list(ledger.read("transactions")) if not dry_run else []
    all_accounts: dict[str, dict] = {}
    all_tx: list[dict] = []

    for doc in docs:
        path = vault.path(*Path(doc["filed_path"]).parts)
        if not path.is_file():
            out["statements"].append({"doc": doc["doc_hash"][:19], "error": "filed file missing"})
            continue

        ex = extract.extract(path)
        st = parsers.parse(ex, filename=Path(doc["filed_path"]).name)

        entry = {
            "doc": doc["doc_hash"][:19],
            "file": doc["filed_path"],
            "bank": st.bank,
            "verified_adapter": st.verified,
            "confidence": st.confidence,
            "rows": len(st.rows),
            "warnings": st.warnings,
            "errors": st.errors,
        }

        if not st.rows:
            entry["status"] = "no_rows"
            out["statements"].append(entry)
            continue

        subject, entity = _subject_for(st, profile)
        acc_ref = account_ref(st)

        # An account is ONE thing evidenced by MANY statements. Keying its
        # record by document hash would mint a fresh account per statement, and
        # anything summing balances across accounts — net worth, most obviously —
        # would then count the same money once per month of history.
        #
        # Identity is therefore the account ref, anchored to the lexicographically
        # smallest evidencing document so the id is stable regardless of the
        # order statements happen to be ingested in.
        prior = all_accounts.get(acc_ref)
        anchor = min(doc["doc_hash"], prior["source"]["doc_hash"]) if prior else doc["doc_hash"]
        acc_id = ledger.record_id(anchor, "header", acc_ref)
        if prior is None or anchor != prior["source"]["doc_hash"]:
            all_accounts[acc_ref] = {
                **_envelope(rec_id=acc_id, schema="accounts/1", subject=subject,
                            entity=entity, doc_hash=anchor, locator="header",
                            method=f"parser:{st.bank}/1", confidence=st.confidence,
                            valid_from=(st.period or {}).get("from") or clock.today()),
                "ref": acc_ref,
                "owner_ref": subject,
                "bank": st.label,
                "kind": "business" if st.is_business else "cheque",
                "currency": st.currency,
                "is_business": st.is_business,
                "statement_cadence": "monthly",
            }
            if st.account_no:
                all_accounts[acc_ref]["account_no"] = st.account_no
            if st.branch_code:
                all_accounts[acc_ref]["branch_code"] = st.branch_code

        uncategorised = 0
        for row in st.rows:
            cat = categorise.categorise(row.description, row.amount_cents, history=history)

            # Identity is origin + natural key, so re-ingesting the same
            # statement produces byte-identical records and writes nothing.
            natural = f"{acc_ref}|{row.date}|{row.amount_cents}|{row.description}"
            tx_id = ledger.record_id(doc["doc_hash"], row.locator, natural)

            rec = {
                **_envelope(rec_id=tx_id, schema="transactions/1", subject=subject,
                            entity=entity, doc_hash=doc["doc_hash"], locator=row.locator,
                            method=f"parser:{st.bank}/1", confidence=row.confidence,
                            valid_from=row.date),
                "account_ref": acc_ref,
                "posted_on": row.date,
                "description_raw": row.description,
                "amount": money.money(row.amount_cents, st.currency),
            }
            if row.balance_cents is not None:
                rec["balance_after"] = money.money(row.balance_cents, st.currency)

            if cat.ok and cat.confidence >= categorise.floor():
                rec["category"] = cat.category
                if cat.subcategory:
                    rec["subcategory"] = cat.subcategory
                if cat.tax_relevance:
                    rec["tax_relevance"] = cat.tax_relevance
                rec["category_confidence"] = cat.confidence
                rec["category_method"] = cat.method
            else:
                # Uncategorised is visible; miscategorised is not.
                uncategorised += 1

            all_tx.append(rec)

        entry["status"] = "parsed"
        entry["uncategorised"] = uncategorised
        entry["account_ref"] = acc_ref
        entry["entity"] = entity or subject
        out["statements"].append(entry)

    acc_result = ledger.write("accounts", list(all_accounts.values()),
                              agent="finance", run_id=run.id, dry_run=dry_run)
    tx_result = ledger.write("transactions", all_tx,
                             agent="finance", run_id=run.id, dry_run=dry_run)

    out["ledgers"] = {"accounts": acc_result, "transactions": tx_result}
    out["totals"] = {
        "statements": len(docs),
        "rows_parsed": sum(s.get("rows", 0) for s in out["statements"]),
        "uncategorised": sum(s.get("uncategorised", 0) for s in out["statements"]),
        "unverified_adapters": sorted({
            s["bank"] for s in out["statements"] if s.get("verified_adapter") is False
        }),
    }
    if out["totals"]["unverified_adapters"]:
        out["note"] = (
            "Rows from unverified adapters carry low confidence and land in "
            "$VAULT/proposed/low-confidence/ rather than the ledger. Confirm them, "
            "or add a verified layout to .claude/rules/bank-formats.yaml."
        )
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lifeos.finance")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--doc", help="limit to one document hash prefix")
    args = ap.parse_args(argv)
    print(json.dumps(build(dry_run=args.dry_run, only_doc=args.doc), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
