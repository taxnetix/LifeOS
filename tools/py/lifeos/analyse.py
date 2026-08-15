"""ANALYSE — cashflow, category breakdown, budget variance, savings rate, net worth.

Every figure returned carries the record IDs it was computed from, so /audit can
walk any number in any dashboard back to a page of a real document.

Personal and business are reported separately AND consolidated. That is the
whole claim of the flagship: one ledger, two correct views, and neither
contaminating the other — a business VAT payment is not household spending, and
counting it as such would make every personal ratio wrong.

Usage:  python -m lifeos.analyse [--months N]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict

from . import clock, ledger, vault

# Not spending, and not income. Counting an internal transfer as either would
# double-count the same rand and inflate both sides of the cashflow.
_EXCLUDED = {"transfer"}


def _month(iso: str) -> str:
    return iso[:7]


def _load_budgets() -> dict:
    from ruamel.yaml import YAML

    p = vault.path("ledgers", "budgets.yaml")
    if not p.is_file():
        return {}
    yaml = YAML(typ="safe")
    with p.open(encoding="utf-8") as fh:
        return yaml.load(fh) or {}


def cashflow(months: int | None = None) -> dict:
    tx = [t for t in ledger.read("transactions") if t.get("category") not in _EXCLUDED]
    accounts = {a["ref"]: a for a in ledger.read("accounts")}

    by_month: dict[str, dict] = defaultdict(
        lambda: {"in": 0, "out": 0, "personal_in": 0, "personal_out": 0,
                 "business_in": 0, "business_out": 0, "n": 0, "ids": []}
    )
    by_category: dict[str, dict] = defaultdict(lambda: {"cents": 0, "n": 0, "ids": []})
    by_entity: dict[str, dict] = defaultdict(lambda: {"in": 0, "out": 0, "n": 0})

    for t in tx:
        m = _month(t["posted_on"])
        cents = t["amount"]["cents"]
        acc = accounts.get(t["account_ref"], {})
        is_biz = bool(acc.get("is_business") or t.get("entity_id"))
        scope = "business" if is_biz else "personal"
        entity = t.get("entity_id") or t["subject_id"]

        bucket = by_month[m]
        bucket["n"] += 1
        bucket["ids"].append(t["id"])
        if cents >= 0:
            bucket["in"] += cents
            bucket[f"{scope}_in"] += cents
            by_entity[entity]["in"] += cents
        else:
            bucket["out"] += cents
            bucket[f"{scope}_out"] += cents
            by_entity[entity]["out"] += cents
        by_entity[entity]["n"] += 1

        if cents < 0:
            key = f"{scope}:{t.get('category') or 'uncategorised'}"
            by_category[key]["cents"] += cents
            by_category[key]["n"] += 1
            by_category[key]["ids"].append(t["id"])

    ordered = sorted(by_month)
    if months:
        ordered = ordered[-months:]

    series = []
    for m in ordered:
        b = by_month[m]
        series.append({
            "month": m,
            "in_cents": b["in"], "out_cents": b["out"], "net_cents": b["in"] + b["out"],
            "personal_net_cents": b["personal_in"] + b["personal_out"],
            "business_net_cents": b["business_in"] + b["business_out"],
            "transactions": b["n"],
            # Provenance: every monthly figure names the records behind it.
            "record_ids": b["ids"],
        })

    personal_in = sum(by_month[m]["personal_in"] for m in ordered)
    personal_out = sum(by_month[m]["personal_out"] for m in ordered)
    savings_rate = (
        round(100 * (personal_in + personal_out) / personal_in, 1) if personal_in else None
    )

    return {
        "months": ordered,
        "series": series,
        "by_category": {
            k: {**v, "cents": v["cents"]}
            for k, v in sorted(by_category.items(), key=lambda kv: kv[1]["cents"])
        },
        "by_entity": dict(by_entity),
        "totals": {
            "in_cents": sum(s["in_cents"] for s in series),
            "out_cents": sum(s["out_cents"] for s in series),
            "net_cents": sum(s["net_cents"] for s in series),
            "personal_in_cents": personal_in,
            "personal_out_cents": personal_out,
            "savings_rate_pct": savings_rate,
        },
        "excluded_categories": sorted(_EXCLUDED),
    }


def budget_variance(flow: dict) -> list[dict]:
    """Compare average monthly spend per category against budgets.yaml."""
    budgets = _load_budgets()
    if not budgets:
        return []
    n = max(1, len(flow["months"]))
    out = []
    for entity_ref, spec in (budgets.get("entities") or {}).items():
        for cat, target in (spec.get("categories") or {}).items():
            actual = 0
            for key, v in flow["by_category"].items():
                if key.endswith(f":{cat}"):
                    actual += v["cents"]
            avg = abs(actual) // n
            tgt = int(target["target_cents"])
            tol = float(target.get("tolerance_pct", 10))
            delta_pct = round(100 * (avg - tgt) / tgt, 1) if tgt else 0.0
            out.append({
                "entity": entity_ref, "category": cat,
                "target_cents": tgt, "actual_cents": avg,
                "delta_cents": avg - tgt, "delta_pct": delta_pct,
                "breached": abs(delta_pct) > tol,
                "tolerance_pct": tol,
            })
    return sorted(out, key=lambda x: -abs(x["delta_pct"]))


def net_worth() -> dict:
    """Snapshot from the ledgers that exist today.

    In Phase 3 that is bank balances plus any recorded assets and liabilities.
    Investments and property land in Phase 4, so the figure is explicitly
    partial and says which ledgers were empty — a net worth that quietly omits
    the house is worse than none.
    """
    accounts = list(ledger.read("accounts"))
    tx = list(ledger.read("transactions"))
    assets = list(ledger.read("assets"))
    liabilities = list(ledger.read("liabilities"))
    holdings = list(ledger.read("holdings"))

    latest: dict[str, dict] = {}
    for t in tx:
        if "balance_after" not in t:
            continue
        cur = latest.get(t["account_ref"])
        if cur is None or t["posted_on"] >= cur["posted_on"]:
            latest[t["account_ref"]] = t

    components = []
    total_assets = total_liabs = 0
    # Belt and braces: collapse by ref before summing, so a duplicated account
    # row can never inflate the total even if one is written by mistake.
    seen_refs: set[str] = set()
    for acc in accounts:
        if acc["ref"] in seen_refs:
            continue
        seen_refs.add(acc["ref"])
        t = latest.get(acc["ref"])
        if not t:
            continue
        cents = t["balance_after"]["cents"]
        components.append({
            "ledger": "accounts", "record_id": t["id"], "label": acc["bank"],
            "ref": acc["ref"], "as_at": t["posted_on"],
            "amount": {"cents": cents, "currency": t["balance_after"]["currency"]},
        })
        if cents >= 0:
            total_assets += cents
        else:
            total_liabs += -cents

    for h in holdings:
        if "value" in h:
            total_assets += h["value"]["cents"]
            components.append({
                "ledger": "holdings", "record_id": h["id"],
                "label": h.get("mandate") or h.get("platform", "holding"),
                "ref": h.get("ref"), "as_at": h.get("value_as_at"),
                "amount": h["value"],
            })

    for a in assets:
        latest_val = None
        for v in ledger.read("valuations"):
            if v.get("asset_ref") == a.get("ref") and (
                latest_val is None or v["as_at"] >= latest_val["as_at"]
            ):
                latest_val = v
        amount = (latest_val or {}).get("value") or a.get("base_cost")
        if amount:
            total_assets += amount["cents"]
            components.append({
                "ledger": "assets", "record_id": a["id"],
                "label": a.get("description", "asset"), "ref": a.get("ref"),
                "as_at": (latest_val or {}).get("as_at"), "amount": amount,
                "basis": (latest_val or {}).get("basis", "base_cost"),
            })

    for liab in liabilities:
        if "balance" in liab:
            total_liabs += abs(liab["balance"]["cents"])
            components.append({
                "ledger": "liabilities", "record_id": liab["id"],
                "label": liab.get("creditor", "liability"), "ref": liab.get("ref"),
                "as_at": liab.get("balance_as_at"), "amount": liab["balance"],
            })

    missing = [name for name, rows in
               (("assets", assets), ("liabilities", liabilities), ("holdings", holdings))
               if not rows]

    labels = {"assets": "property and movables", "liabilities": "debt",
              "holdings": "investments"}
    return {
        "as_at": clock.today(),
        "assets_cents": total_assets,
        "liabilities_cents": total_liabs,
        "net_cents": total_assets - total_liabs,
        "components": components,
        "partial": bool(missing),
        "missing_ledgers": missing,
        # A net worth that quietly omits the house or the bond is worse than
        # none, so every empty ledger is named in the caveat rather than
        # silently treated as zero.
        "note": (
            "PARTIAL: no records in " + ", ".join(missing) + ", so "
            + ", ".join(labels[m] for m in missing) + " are excluded."
        ) if missing else "",
    }


def report(months: int | None = None) -> dict:
    if not vault.is_initialised():
        return {"schema": "analysis/1", "error": "no vault — run /lifeos-init"}
    flow = cashflow(months)
    return {
        "schema": "analysis/1",
        "at": clock.stamp(),
        "cashflow": flow,
        "budget_variance": budget_variance(flow),
        "net_worth": net_worth(),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lifeos.analyse")
    ap.add_argument("--months", type=int)
    args = ap.parse_args(argv)
    print(json.dumps(report(args.months), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
