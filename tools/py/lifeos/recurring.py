"""Detect recurring payments from transaction history.

A debit order is not labelled as one on a statement — it is a pattern across
months. This finds them by grouping normalised descriptions and testing whether
the intervals look periodic.

Two things it deliberately does NOT do:

  * **Guess a cancellation route.** That field is required by the schema and it
    is the whole point of the ledger — a recurring cost you cannot work out how
    to stop is a finding. So a detected payment is written with the route left
    as a question for the human, never invented.

  * **Claim a pattern from a single sighting.** Two occurrences is a
    coincidence; the minimum is three, or two with an exact amount match.

Usage:  python -m lifeos.recurring [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from datetime import date

from . import categorise, clock, ledger, money, vault

# Interval tolerance in days for each cadence.
_CADENCES = [
    ("weekly", 7, 2),
    ("fortnightly", 14, 3),
    ("monthly", 30, 6),
    ("quarterly", 91, 10),
    ("biannual", 182, 15),
    ("annual", 365, 20),
]

_MIN_OCCURRENCES = 3

# A commitment's amount is stable until it escalates, and then stable again.
# Each distinct amount must therefore persist, and steps must all go one way.
_MAX_DISTINCT_AMOUNTS = 3
_MAX_STEP_PCT = 20.0        # a bigger jump is a different purchase, not an escalation
_EXACT_TOLERANCE = 0.005    # rounding noise on an otherwise identical amount


def _is_commitment(amounts: list[int]) -> bool:
    """Does this amount series look like a debit order rather than shopping?

    All-equal is the clearest case. Otherwise the series must be monotonic
    (an escalation only ever goes up, or a step-down on renegotiation) with few
    distinct values and no single jump larger than a plausible escalation.
    """
    if len(set(amounts)) == 1:
        return True

    mean_amt = statistics.mean(amounts)
    if mean_amt and (max(amounts) - min(amounts)) / mean_amt <= _EXACT_TOLERANCE:
        return True

    distinct = []
    for a in amounts:
        if not distinct or distinct[-1] != a:
            distinct.append(a)
    if len(distinct) > _MAX_DISTINCT_AMOUNTS:
        return False

    steps = [b - a for a, b in zip(distinct, distinct[1:], strict=False)]
    if not steps:
        return False
    if not (all(s > 0 for s in steps) or all(s < 0 for s in steps)):
        return False

    return all(abs(100 * s / a) <= _MAX_STEP_PCT
               for s, a in zip(steps, distinct, strict=False) if a)


def _cadence(gaps: list[int]) -> tuple[str | None, float]:
    if not gaps:
        return None, 0.0
    med = statistics.median(gaps)
    for name, days, tol in _CADENCES:
        if abs(med - days) <= tol:
            spread = max(abs(g - med) for g in gaps)
            regularity = max(0.0, 1.0 - (spread / (days * 0.6)))
            return name, round(regularity, 3)
    return None, 0.0


def detect(transactions: list[dict]) -> list[dict]:
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for t in transactions:
        if t.get("category") == "transfer":
            continue
        cents = t["amount"]["cents"]
        if cents >= 0:
            continue  # inflows are income, handled elsewhere
        key = (t["account_ref"], categorise._normalise(t["description_raw"]))
        if key[1]:
            groups[key].append(t)

    found = []
    for (acc, norm), rows in groups.items():
        rows.sort(key=lambda r: r["posted_on"])
        amounts = [abs(r["amount"]["cents"]) for r in rows]
        dates = [date.fromisoformat(r["posted_on"]) for r in rows]

        exact = len(set(amounts)) == 1
        if len(rows) < _MIN_OCCURRENCES and not (len(rows) == 2 and exact):
            continue

        gaps = [(b - a).days for a, b in zip(dates, dates[1:], strict=False)]
        cadence, regularity = _cadence(gaps)
        if not cadence:
            continue

        mean_amt = statistics.mean(amounts)
        if not _is_commitment(amounts):
            # Variable spend at a regular merchant is not a commitment. A weekly
            # grocery run is periodic and differently-priced every time; a debit
            # order is the same amount until it escalates. Tolerating drift by
            # percentage alone lets the supermarket in and makes "your monthly
            # commitments" a number the user cannot act on.
            continue

        escalation = None
        if len(amounts) >= 2 and amounts[-1] > amounts[0]:
            pct = round(100 * (amounts[-1] / amounts[0] - 1), 2)
            if pct >= 1.0:
                escalation = {"pct": pct, "month": dates[-1].month}

        found.append({
            "account_ref": acc,
            "counterparty": rows[-1]["description_raw"],
            "normalised": norm,
            "amount_cents": amounts[-1],
            "mean_cents": int(mean_amt),
            "frequency": cadence,
            "regularity": regularity,
            "occurrences": len(rows),
            "started_on": rows[0]["posted_on"],
            "last_seen_on": rows[-1]["posted_on"],
            "last_seen_txn": rows[-1]["id"],
            "category": rows[-1].get("category"),
            "subcategory": rows[-1].get("subcategory"),
            "escalation": escalation,
            "entity_id": rows[-1].get("entity_id"),
            "subject_id": rows[-1]["subject_id"],
            "exact_amount": exact,
        })

    found.sort(key=lambda f: -f["amount_cents"])
    return found


def build(*, dry_run: bool = False) -> dict:
    run = clock.Run.current()
    out: dict = {"schema": "recurring/1", "run_id": run.id, "at": clock.stamp(),
                 "dry_run": dry_run}

    if not vault.is_initialised():
        out["error"] = "no vault — run /lifeos-init"
        return out

    tx = list(ledger.read("transactions"))
    found = detect(tx)

    records = []
    for f in found:
        ref = f"rec_{f['account_ref'].removeprefix('acc_')}_{abs(hash(f['normalised'])) % 10**6}"
        rec_id = ledger.record_id("inferred", f"pattern={f['normalised']}", ref)
        rec = {
            "id": rec_id,
            "schema": "recurring-payments/1",
            "subject_id": f["subject_id"],
            "source": {
                "doc_hash": "inferred",
                "locator": f"pattern={f['normalised']};n={f['occurrences']}",
                "method": "inferred",
                # Inferred, so it is rendered differently in reports and never
                # mistaken for something read off a document.
                "confidence": round(min(0.95, 0.6 + 0.1 * f["occurrences"]) * f["regularity"], 3),
                "extracted_at": clock.stamp(),
            },
            "valid_from": f["started_on"],
            "valid_to": None,
            "superseded_by": None,
            "ref": ref,
            "payer_ref": f["subject_id"],
            "account_ref": f["account_ref"],
            "counterparty": f["counterparty"],
            "kind": "debit_order" if "debit order" in f["counterparty"].lower() else "card_recurring",
            "amount": money.money(-f["amount_cents"]),
            "frequency": f["frequency"],
            "started_on": f["started_on"],
            "last_seen_txn": f["last_seen_txn"],
            "status": "active",
            # REQUIRED by schema and deliberately not invented. A recurring cost
            # nobody can work out how to stop is exactly the finding this ledger
            # exists to surface.
            "cancellation_route": "UNKNOWN — ask the human",
        }
        if f["entity_id"]:
            rec["entity_id"] = f["entity_id"]
        if f["escalation"]:
            rec["escalation"] = f["escalation"]
        records.append(rec)

    out["detected"] = len(found)
    out["ledger"] = ledger.write("recurring-payments", records, agent="finance",
                                 run_id=run.id, dry_run=dry_run)
    out["monthly_total"] = money.fmt(sum(
        f["amount_cents"] for f in found if f["frequency"] == "monthly"
    ))
    out["needs_cancellation_route"] = len(records)
    out["found"] = found
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lifeos.recurring")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    print(json.dumps(build(dry_run=args.dry_run), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
