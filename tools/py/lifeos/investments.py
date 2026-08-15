"""INVESTMENTS — platform statements into holdings, plus fee-drag analysis.

Two things this produces that a platform statement does not:

  * **Fee drag over a horizon.** A 1.4% total expense ratio reads as nothing on
    a statement. Compounded over thirty years it is a third of the terminal
    value. The number only becomes visible when it is projected.

  * **Retirement-fund holdings alongside discretionary ones.** The provident
    fund on an employee benefit statement and the unit trusts on a platform
    statement are the same person's retirement, and neither document says so.

Usage:  python -m lifeos.investments [--dry-run] [--markdown]
"""

from __future__ import annotations

import argparse
import contextlib
import json
import re
import sys
from pathlib import Path

from . import atomic, clock, extract, ledger, money, vault

# Header aliases for a platform holdings table. Matched by NAME, not position.
_COLS = {
    "platform": ["platform", "provider", "administrator"],
    "account": ["account", "account number", "portfolio", "reference"],
    "fund": ["fund", "instrument", "security", "holding", "description"],
    "units": ["units", "shares", "quantity"],
    "price": ["price", "unit price", "nav"],
    "value": ["value", "market value", "current value", "closing value"],
    "ter": ["ter %", "ter", "total expense ratio", "ter (%)"],
}

_KIND_HINTS = [
    (("tax free", "tfsa"), "tfsa"),
    (("retirement annuity", " ra ", "ra "), "ra"),
    (("preservation",), "preservation"),
    (("provident", "pension"), "occupational"),
    (("money market", "income fund"), "money_market"),
    (("bond fund", "bond "), "unit_trust"),
    (("equity", "feeder", "global", "satrix", "index"), "unit_trust"),
    (("crypto", "bitcoin"), "crypto"),
]

# Projection horizons for fee drag, in years.
_HORIZONS = (10, 20, 30)
_ASSUMED_GROSS_RETURN_PCT = 10.0   # nominal, documented as an assumption


def _kind_for(fund: str) -> str:
    low = f" {fund.lower()} "
    for needles, kind in _KIND_HINTS:
        if any(n in low for n in needles):
            return kind
    return "unit_trust"


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_")[:32] or "unknown"


def _match_columns(header: list[str]) -> dict[str, int]:
    idx: dict[str, int] = {}
    lows = [h.strip().lower() for h in header]
    for field, aliases in _COLS.items():
        for i, h in enumerate(lows):
            if h in aliases:
                idx[field] = i
                break
    return idx


def build(*, dry_run: bool = False) -> dict:
    from .readiness import load_profile

    run = clock.Run.current()
    out: dict = {"schema": "investments/1", "run_id": run.id, "at": clock.stamp(),
                 "dry_run": dry_run, "documents": []}

    if not vault.is_initialised():
        out["error"] = "no vault — run /lifeos-init"
        return out

    profile = load_profile()
    me = next((p for p in (profile.get("people") or []) if p.get("relation") == "self"), {})
    subject = me.get("ref", "per_unknown")

    index = list(atomic.read_jsonl(vault.path("documents", "index.jsonl")))
    records: list[dict] = []

    for doc in index:
        if doc.get("type") != "investment_statement" or doc.get("redacted"):
            continue
        path = vault.path(*Path(doc["filed_path"]).parts)
        if not path.is_file():
            continue

        ex = extract.extract(path)
        entry = {"doc": doc["doc_hash"][:19], "holdings": 0, "errors": []}

        table = max(ex.tables, key=lambda t: len(t.rows), default=None)
        if not table or len(table.rows) < 2:
            entry["errors"].append("no holdings table found")
            out["documents"].append(entry)
            continue

        idx = _match_columns(table.rows[0])
        if "fund" not in idx or "value" not in idx:
            entry["errors"].append(f"could not identify fund/value columns in {table.rows[0]}")
            out["documents"].append(entry)
            continue

        for n, raw in enumerate(table.rows[1:], start=2):
            if len(raw) <= max(idx.values()):
                continue
            fund = raw[idx["fund"]].strip()
            value = money.parse(raw[idx["value"]])
            if not fund or value is None:
                continue

            platform = raw[idx["platform"]].strip() if "platform" in idx else "unknown"
            account = raw[idx["account"]].strip() if "account" in idx else None
            kind = _kind_for(fund)
            ref = f"hol_{_slug(platform)}_{_slug(fund)}"

            rec = {
                "id": ledger.record_id(doc["doc_hash"], f"{table.locator};row={n}", ref),
                "schema": "holdings/1",
                "subject_id": subject,
                "source": {
                    "doc_hash": doc["doc_hash"],
                    "locator": f"{table.locator};row={n}",
                    "method": "investments/1",
                    "confidence": 0.95,
                    "extracted_at": clock.stamp(),
                },
                "valid_from": (doc.get("period") or {}).get("to") or clock.today(),
                "valid_to": None, "superseded_by": None,
                "ref": ref, "owner_ref": subject, "kind": kind,
                "platform": platform, "currency": "ZAR",
                "value": money.money(value),
                "value_as_at": (doc.get("period") or {}).get("to") or clock.today(),
                "mandate": fund,
                "doc_hash": doc["doc_hash"],
            }
            if account:
                rec["account_no"] = account
            if "ter" in idx:
                # A TER that will not parse is simply absent; fee drag then
                # reports one fewer priced holding rather than assuming zero.
                with contextlib.suppress(ValueError, IndexError):
                    rec["fees"] = {"fund_ter_pct": float(raw[idx["ter"]])}
            records.append(rec)
            entry["holdings"] += 1

        out["documents"].append(entry)

    # Retirement fund from the employee benefit statement — same person's
    # retirement money, and neither document mentions the other.
    for b in ledger.read("employee-benefits"):
        if b["kind"] not in {"provident", "pension"} or not b.get("benefit"):
            continue
        ref = f"hol_{_slug(b['employer'])}_{b['kind']}"
        records.append({
            "id": ledger.record_id(b["source"]["doc_hash"], "benefit=fund", ref),
            "schema": "holdings/1",
            "subject_id": b.get("person_ref", subject),
            "source": {
                "doc_hash": b["source"]["doc_hash"], "locator": "benefit=fund",
                "method": "investments/1", "confidence": b["source"]["confidence"],
                "extracted_at": clock.stamp(),
            },
            "valid_from": b.get("statement_as_at") or clock.today(),
            "valid_to": None, "superseded_by": None,
            "ref": ref, "owner_ref": b.get("person_ref", subject),
            "kind": "occupational", "platform": b["employer"],
            "currency": "ZAR", "value": b["benefit"],
            "value_as_at": b.get("statement_as_at") or clock.today(),
            "reg28_applicable": True,
            "mandate": "Employer retirement fund",
            **({"account_no": b["member_no"]} if b.get("member_no") else {}),
        })

    out["ledger"] = ledger.write("holdings", records, agent="investments",
                                 run_id=run.id, dry_run=dry_run)
    out["totals"] = {"holdings": len(records),
                     "value_cents": sum(r["value"]["cents"] for r in records)}
    return out


def fee_drag() -> dict:
    """What the total expense ratio costs over a horizon.

    A TER is quoted as a fraction of a percent and reads as noise. Projected,
    it is one of the largest single costs in a lifetime — and unlike market
    returns, it is knowable in advance and negotiable.
    """
    holdings = [h for h in ledger.read("holdings") if (h.get("fees") or {}).get("fund_ter_pct")]
    rows = []
    for h in holdings:
        ter = h["fees"]["fund_ter_pct"]
        value = h["value"]["cents"]
        projections = {}
        for years in _HORIZONS:
            gross = value * ((1 + _ASSUMED_GROSS_RETURN_PCT / 100) ** years)
            net = value * ((1 + (_ASSUMED_GROSS_RETURN_PCT - ter) / 100) ** years)
            projections[years] = int(gross - net)
        rows.append({
            "ref": h["ref"], "mandate": h.get("mandate"), "platform": h["platform"],
            "value_cents": value, "ter_pct": ter,
            "annual_cost_cents": int(value * ter / 100),
            "cost_by_horizon_cents": projections,
            "record_id": h["id"],
        })
    rows.sort(key=lambda r: -r["cost_by_horizon_cents"][_HORIZONS[-1]])

    total_value = sum(r["value_cents"] for r in rows)
    weighted = (
        sum(r["ter_pct"] * r["value_cents"] for r in rows) / total_value if total_value else 0
    )
    return {
        "holdings": rows,
        "weighted_ter_pct": round(weighted, 3),
        "annual_cost_cents": sum(r["annual_cost_cents"] for r in rows),
        "assumed_gross_return_pct": _ASSUMED_GROSS_RETURN_PCT,
        "horizons": list(_HORIZONS),
        "unpriced_holdings": sum(1 for h in ledger.read("holdings")
                                 if not (h.get("fees") or {}).get("fund_ter_pct")),
    }


def report() -> dict:
    if not vault.is_initialised():
        return {"schema": "investments-report/1", "error": "no vault"}
    holdings = list(ledger.read("holdings"))
    by_kind: dict[str, int] = {}
    for h in holdings:
        by_kind[h["kind"]] = by_kind.get(h["kind"], 0) + h["value"]["cents"]
    total = sum(by_kind.values())
    return {
        "schema": "investments-report/1",
        "at": clock.stamp(),
        "total_cents": total,
        "by_kind": by_kind,
        "retirement_cents": sum(v for k, v in by_kind.items()
                                if k in {"ra", "preservation", "occupational"}),
        "discretionary_cents": sum(v for k, v in by_kind.items()
                                   if k not in {"ra", "preservation", "occupational", "tfsa"}),
        "tfsa_cents": by_kind.get("tfsa", 0),
        "fee_drag": fee_drag(),
        "holdings": [{"ref": h["ref"], "kind": h["kind"], "platform": h["platform"],
                      "mandate": h.get("mandate"), "value_cents": h["value"]["cents"],
                      "as_at": h.get("value_as_at"), "record_id": h["id"]}
                     for h in sorted(holdings, key=lambda x: -x["value"]["cents"])],
    }


def to_markdown(rep: dict) -> str:
    if rep.get("error"):
        return f"**{rep['error']}**"
    fd = rep["fee_drag"]
    lines = [
        "# Investments",
        "",
        f"Total: **{money.fmt(rep['total_cents'])}**  ·  "
        f"retirement {money.fmt(rep['retirement_cents'])}  ·  "
        f"discretionary {money.fmt(rep['discretionary_cents'])}  ·  "
        f"TFSA {money.fmt(rep['tfsa_cents'])}",
        "",
        "| Holding | Type | Platform | Value | As at |",
        "|---|---|---|---|---|",
    ]
    for h in rep["holdings"]:
        lines.append(
            f"| {h['mandate'] or h['ref']} | {h['kind']} | {h['platform']} | "
            f"{money.fmt(h['value_cents'])} | {h['as_at']} |"
        )
    lines += [
        "",
        "## Fee drag",
        "",
        f"Weighted average TER: **{fd['weighted_ter_pct']}%** — "
        f"{money.fmt(fd['annual_cost_cents'])} this year.",
        "",
        f"Projected at {fd['assumed_gross_return_pct']}% nominal gross return, "
        "fees cost you:",
        "",
        "| Holding | TER | " + " | ".join(f"over {y}y" for y in fd["horizons"]) + " |",
        "|---|---|" + "---|" * len(fd["horizons"]),
    ]
    for h in fd["holdings"]:
        cells = " | ".join(money.fmt(h["cost_by_horizon_cents"][y]) for y in fd["horizons"])
        lines.append(f"| {h['mandate']} | {h['ter_pct']}% | {cells} |")
    if fd["unpriced_holdings"]:
        lines += ["", f"_{fd['unpriced_holdings']} holding(s) have no TER recorded and are "
                      "excluded from this projection — the real drag is higher._"]
    lines += ["", "_The return assumption is nominal and illustrative. Fees are not: "
                  "they are knowable in advance and negotiable._"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lifeos.investments")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--markdown", action="store_true")
    args = ap.parse_args(argv)
    if args.markdown:
        print(to_markdown(report()))
    else:
        print(json.dumps(build(dry_run=args.dry_run), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
