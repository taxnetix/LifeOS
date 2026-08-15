"""OPTIMISE — ranked, costed findings with evidence.

Every finding carries: what it is, what it is worth per year, what it would take
to act, and the record IDs that prove it. A recommendation without a number
attached is an opinion, and a number without records behind it is a guess.

Findings are PROPOSALS. This module never cancels a subscription, moves money,
or contacts a provider — it writes to reports/ and proposed/ and waits.

Usage:  python -m lifeos.optimise [--markdown]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict

from . import analyse, atomic, clock, ledger, money, vault

EFFORT_MINUTES = {"minutes": 1, "hours": 3, "days": 8}


def _finding(**kw) -> dict:
    kw.setdefault("evidence", [])
    kw.setdefault("confidence", "high")
    return kw


def duplicate_subscriptions() -> list[dict]:
    """The same service paid from more than one account.

    Works on TRANSACTIONS rather than detected commitments on purpose: a
    subscription billed personally every month and once through the business
    would never reach the recurring threshold on the business side, so a
    commitments-only check misses exactly the case that matters. This is also
    the cross-account finding that is invisible on either statement alone.
    """
    from . import categorise

    tx = [t for t in ledger.read("transactions")
          if t["amount"]["cents"] < 0
          and t.get("category") in {"subscriptions", "insurance", "medical", "utilities"}]

    by_service: dict[str, list[dict]] = defaultdict(list)
    for t in tx:
        key = categorise._normalise(t["description_raw"])[:20]
        if key:
            by_service[key].append(t)

    accounts = {a["ref"]: a for a in ledger.read("accounts")}
    out = []
    for _key, rows in by_service.items():
        refs = {t["account_ref"] for t in rows}
        if len(refs) < 2:
            continue

        # Charge the smaller side: cancelling the duplicate keeps the cheaper
        # or the business one, whichever the human decides.
        per_account = defaultdict(int)
        for t in rows:
            per_account[t["account_ref"]] += abs(t["amount"]["cents"])
        smallest = min(per_account.values())

        where = ", ".join(
            f"{accounts.get(r, {}).get('bank', r)}"
            f"{' (business)' if accounts.get(r, {}).get('is_business') else ''}"
            for r in sorted(refs)
        )
        out.append(_finding(
            kind="duplicate_subscription",
            title=f"{rows[0]['description_raw']} is paid from {len(refs)} accounts",
            detail=(
                f"Charged on: {where}. If this is one service billed twice, cancelling "
                "the duplicate saves the full amount. If the two are genuinely separate "
                "— a personal and a business seat — record why, so it stops surfacing. "
                "Neither statement shows this on its own."
            ),
            annual_saving_cents=smallest * 12,
            effort="minutes",
            confidence="medium",
            evidence=[t["id"] for t in rows],
        ))
    return out


def fee_leakage(flow: dict, months: int) -> list[dict]:
    """Bank charges are individually trivial and annually significant, which is
    precisely why nobody looks at them."""
    out = []
    for key, v in flow["by_category"].items():
        if not key.endswith(":fees"):
            continue
        scope = key.split(":")[0]
        monthly = abs(v["cents"]) // max(1, months)
        annual = monthly * 12
        if annual < 50_000:      # under R500/yr is not worth a recommendation
            continue
        out.append(_finding(
            kind="fee_leakage",
            title=f"{money.fmt(annual)} a year in {scope} bank charges",
            detail=(
                f"{v['n']} fee transactions over {months} months, averaging "
                f"{money.fmt(monthly)} a month. Compare the account's fee structure "
                "against a bundled or lower-tier option — this is usually a single "
                "phone call, and the saving repeats every year."
            ),
            annual_saving_cents=annual // 2,   # assume roughly half is avoidable
            effort="hours",
            confidence="medium",
            evidence=v["ids"][:20],
        ))
    return out


def escalation_creep(recurring: list[dict]) -> list[dict]:
    """An annual escalation is invisible month to month and compounds."""
    out = []
    for r in recurring:
        esc = r.get("escalation")
        if not esc or esc.get("pct", 0) < 5:
            continue
        current = abs(r["amount"]["cents"])
        # Five years of compounding at the observed rate, against holding flat.
        five_year = sum(
            int(current * ((1 + esc["pct"] / 100) ** y)) * 12 for y in range(1, 6)
        ) - current * 12 * 5
        out.append(_finding(
            kind="escalation_creep",
            title=f"{r['counterparty']} escalates {esc['pct']}% a year",
            detail=(
                f"Now {money.fmt(current)} a month. At this rate it costs an extra "
                f"{money.fmt(five_year)} over five years compared with holding flat. "
                "Escalation is usually negotiable at renewal, and almost never "
                "renegotiated because nobody notices it."
            ),
            annual_saving_cents=int(current * 12 * esc["pct"] / 100),
            effort="hours",
            evidence=[r["id"]],
        ))
    return out


def missed_deductions(flow: dict) -> list[dict]:
    """Spending a tax practitioner would want to see, flagged for review.

    This is emphatically NOT a claim that anything is deductible — that
    determination belongs to a registered practitioner and to the tax domain.
    """
    tx = list(ledger.read("transactions"))
    by_flag: dict[str, list[dict]] = defaultdict(list)
    for t in tx:
        for flag in t.get("tax_relevance", []) or []:
            if flag != "none":
                by_flag[flag].append(t)

    labels = {
        "medical": "Medical scheme and healthcare spend",
        "retirement": "Retirement contributions",
        "rental_income": "Rental income received",
        "travel": "Fuel and travel spend",
        "business_expense": "Business expenses paid",
        "home_office": "Home office costs",
    }
    out = []
    for flag, rows in by_flag.items():
        total = sum(abs(t["amount"]["cents"]) for t in rows)
        if total < 100_000:
            continue
        out.append(_finding(
            kind="tax_review",
            title=f"{labels.get(flag, flag)}: {money.fmt(total)} over the period",
            detail=(
                f"{len(rows)} transactions carry the '{flag}' flag. Take this to your "
                "tax practitioner — LifeOS flags what is worth asking about and does "
                "not decide what is deductible."
            ),
            annual_saving_cents=0,
            effort="hours",
            confidence="review_required",
            evidence=[t["id"] for t in rows[:20]],
        ))
    return out


def savings_rate(flow: dict) -> list[dict]:
    from .readiness import load_profile

    rate = flow["totals"].get("savings_rate_pct")
    if rate is None:
        return []
    target = float(
        ((load_profile().get("finance") or {}).get("savings_rate_target_pct")) or 20
    )
    if rate >= target:
        return [_finding(
            kind="savings_rate",
            title=f"Savings rate is {rate}%, above your {target:.0f}% target",
            detail="Personal income less personal spending, excluding transfers.",
            annual_saving_cents=0,
            effort="minutes",
            confidence="high",
        )]
    shortfall = int(flow["totals"]["personal_in_cents"] * (target - rate) / 100)
    return [_finding(
        kind="savings_rate",
        title=f"Savings rate is {rate}%, below your {target:.0f}% target",
        detail=(
            f"Closing the gap over this period means finding {money.fmt(shortfall)}. "
            "The commitments list is the place to look first."
        ),
        annual_saving_cents=0,
        effort="days",
    )]


def unknown_cancellation_routes(recurring: list[dict]) -> list[dict]:
    unknown = [r for r in recurring if str(r.get("cancellation_route", "")).startswith("UNKNOWN")]
    if not unknown:
        return []
    monthly = sum(abs(r["amount"]["cents"]) for r in unknown)
    return [_finding(
        kind="unknown_cancellation_route",
        title=f"{len(unknown)} commitments worth {money.fmt(monthly)}/month have no recorded way to stop them",
        detail=(
            "A recurring cost you cannot work out how to cancel is a finding in "
            "itself, and it is the thing an executor struggles with most. Record "
            "the cancellation route for each while it is easy to find."
        ),
        annual_saving_cents=0,
        effort="hours",
        evidence=[r["id"] for r in unknown[:20]],
    )]


def report(months: int | None = None) -> dict:
    if not vault.is_initialised():
        return {"schema": "optimise/1", "error": "no vault — run /lifeos-init"}

    flow = analyse.cashflow(months)
    n = max(1, len(flow["months"]))
    recurring = list(ledger.read("recurring-payments"))

    findings: list[dict] = []
    findings += duplicate_subscriptions()
    findings += escalation_creep(recurring)
    findings += fee_leakage(flow, n)
    findings += unknown_cancellation_routes(recurring)
    findings += missed_deductions(flow)
    findings += savings_rate(flow)

    # Rank by annual rand recovered per unit of effort — the same shape as the
    # readiness shortest path, for the same reason: the best next action is
    # usually not the biggest number.
    for f in findings:
        f["value_per_effort"] = round(
            f.get("annual_saving_cents", 0) / EFFORT_MINUTES.get(f.get("effort", "hours"), 3), 0
        )
    findings.sort(key=lambda f: (-f["value_per_effort"], -f.get("annual_saving_cents", 0)))

    return {
        "schema": "optimise/1",
        "at": clock.stamp(),
        "months_analysed": flow["months"],
        "findings": findings,
        "total_annual_saving_cents": sum(f.get("annual_saving_cents", 0) for f in findings),
        "note": "Findings are proposals. Nothing here has been actioned.",
    }


def to_markdown(rep: dict) -> str:
    if rep.get("error"):
        return f"**{rep['error']}**"
    total = rep["total_annual_saving_cents"]
    lines = [
        "# Optimisation findings",
        "",
        f"Period: {', '.join(rep['months_analysed'])}",
        f"**Identified: {money.fmt(total)} a year** across {len(rep['findings'])} findings.",
        "",
        "_Proposals only. Nothing has been actioned._",
        "",
    ]
    for i, f in enumerate(rep["findings"], 1):
        worth = f" — **{money.fmt(f['annual_saving_cents'])}/yr**" if f.get("annual_saving_cents") else ""
        lines += [f"### {i}. {f['title']}{worth}", "",
                  f"{f['detail']}", "",
                  f"*Effort: {f['effort']} · confidence: {f['confidence']} · "
                  f"{len(f.get('evidence', []))} source records*", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lifeos.optimise")
    ap.add_argument("--months", type=int)
    ap.add_argument("--markdown", action="store_true")
    ap.add_argument("--write", action="store_true", help="write the report into the vault")
    args = ap.parse_args(argv)

    rep = report(args.months)
    text = to_markdown(rep)
    if args.write and not rep.get("error"):
        path = vault.path("reports", f"optimise-{clock.today()}.md")
        atomic.write_text(path, text)
        rep["written"] = vault.rel(path)
    print(text if args.markdown else json.dumps(rep, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
