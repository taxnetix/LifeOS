"""ESTATE — duty, CGT at death, fees, liquidity shortfall, beneficiary conflicts.

The liquidity question is the one that matters most and is asked least:
**on the day you die, can your family reach cash?** An estate is frozen. Duty,
CGT, executor's fees and the Master's fee all fall due, and the assets that
would pay them cannot be sold until the executor is appointed — which takes
months. A solvent estate and a liquid one are different things, and families
discover the difference at the worst possible moment.

The beneficiary-versus-will check is the highest-value finding here. A
nomination on a policy or a fund OVERRIDES the will for that asset. Neither
document knows about the other, so the conflict is invisible from inside either.

Every figure computes from `.claude/rules/za/` and carries that rulebook's
"as at" date and verification status. Nothing here is advice, and estate
planning decisions must not be made on unverified figures.

Usage:  python -m lifeos.estate [--markdown]
"""

from __future__ import annotations

import argparse
import json
import sys

from . import atomic, clock, ledger, money, rules, vault

# How long an estate typically takes to wind up before assets can be realised.
# Used only to frame the liquidity question, and stated as an assumption.
TYPICAL_MONTHS_TO_WIND_UP = 12
IMMEDIATE_NEED_DAYS = 30


def _latest_valuation(asset_ref: str) -> dict | None:
    best = None
    for v in ledger.read("valuations"):
        if v.get("asset_ref") == asset_ref and (best is None or v["as_at"] >= best["as_at"]):
            best = v
    return best


def gather() -> dict:
    """Everything the estate calculations need, with its provenance."""
    accounts_cash = 0
    cash_ids = []
    latest: dict[str, dict] = {}
    for t in ledger.read("transactions"):
        if "balance_after" not in t:
            continue
        cur = latest.get(t["account_ref"])
        if cur is None or t["posted_on"] >= cur["posted_on"]:
            latest[t["account_ref"]] = t
    business_refs = {a["ref"] for a in ledger.read("accounts") if a.get("is_business")}
    for ref, t in latest.items():
        if ref in business_refs:
            continue          # company money is not the deceased's estate
        accounts_cash += t["balance_after"]["cents"]
        cash_ids.append(t["id"])

    assets = []
    for a in ledger.read("assets"):
        val = _latest_valuation(a.get("ref", ""))
        amount = (val or {}).get("value") or a.get("base_cost")
        if not amount:
            continue
        assets.append({
            "ref": a.get("ref"), "description": a.get("description"),
            "value_cents": amount["cents"],
            "base_cost_cents": (a.get("base_cost") or {}).get("cents"),
            "basis": (val or {}).get("basis", "base_cost"),
            "record_id": a["id"],
        })

    holdings = [{
        "ref": h["ref"], "kind": h["kind"], "mandate": h.get("mandate"),
        "value_cents": h["value"]["cents"], "record_id": h["id"],
    } for h in ledger.read("holdings")]

    liabilities = [{
        "ref": lb.get("ref"), "creditor": lb.get("creditor"), "kind": lb.get("kind"),
        "balance_cents": (lb.get("balance") or {}).get("cents", 0),
        "record_id": lb["id"],
    } for lb in ledger.read("liabilities")]

    policies = [{
        "ref": p["ref"], "class": p.get("class"), "insurer": p.get("insurer"),
        "sum_assured_cents": (p.get("sum_assured") or {}).get("cents", 0),
        "beneficiaries": p.get("beneficiaries") or [],
        "cession": p.get("cession"),
        "record_id": p["id"],
    } for p in ledger.read("policies") if p.get("class") in {"life", "funeral"}]

    benefits = [{
        "ref": b["ref"], "kind": b["kind"], "employer": b.get("employer"),
        "benefit_cents": (b.get("benefit") or {}).get("cents", 0),
        "beneficiaries": b.get("beneficiaries") or [],
        "record_id": b["id"],
    } for b in ledger.read("employee-benefits")]

    return {"cash_cents": accounts_cash, "cash_ids": cash_ids, "assets": assets,
            "holdings": holdings, "liabilities": liabilities,
            "policies": policies, "benefits": benefits,
            "wills": list(ledger.read("wills"))}


def _spouse_inherits(data: dict) -> tuple[bool, str]:
    from .readiness import load_profile
    spouses = [p.get("name", "").lower() for p in (load_profile().get("people") or [])
               if p.get("relation") == "spouse"]
    for w in data["wills"]:
        for trigger in w.get("review_triggers", []):
            if trigger.startswith("residuary heir:"):
                heir = trigger.split(":", 1)[1].strip().lower()
                if any(s and s in heir for s in spouses):
                    return True, trigger.split(":", 1)[1].strip()
    return False, ""


def duty_and_cgt(data: dict) -> dict:
    duty_rule = rules.load("estate-duty")
    cgt_rule = rules.load("cgt")
    fee_rule = rules.load("estate-fees")

    asset_total = sum(a["value_cents"] for a in data["assets"])
    holdings_total = sum(h["value_cents"] for h in data["holdings"])
    retirement = sum(h["value_cents"] for h in data["holdings"]
                     if h["kind"] in {"ra", "preservation", "occupational"})
    discretionary_holdings = holdings_total - retirement
    liabilities_total = sum(lb["balance_cents"] for lb in data["liabilities"])

    # Deemed property: domestic life policy proceeds are in the dutiable estate
    # even when a nomination sends them straight to a beneficiary.
    deemed = sum(p["sum_assured_cents"] for p in data["policies"] if p["class"] == "life")

    # Retirement fund interests are NOT property in the estate for duty.
    gross_estate = data["cash_cents"] + asset_total + discretionary_holdings + deemed
    net_estate = gross_estate - liabilities_total

    executor_fee = int(gross_estate * fee_rule["executor"]["max_pct_of_gross_estate"] / 100)
    if fee_rule["executor"]["vat_applies"]:
        executor_fee = int(executor_fee * (1 + fee_rule["executor"]["vat_pct"] / 100))
    master_fee = fee_rule["master"]["cap"] * 100
    for band in fee_rule["master"]["scale"]:
        if band["upto"] is not None and gross_estate <= band["upto"] * 100:
            master_fee = band["fee"] * 100
            break

    spouse_inherits, heir = _spouse_inherits(data)
    # s4(q): property accruing to the surviving spouse is deducted. It DEFERS
    # duty into the second estate; it does not remove it.
    s4q = max(0, net_estate - executor_fee - master_fee) if spouse_inherits else 0

    abatement = duty_rule["abatement_s4a"] * 100
    dutiable = max(0, net_estate - executor_fee - master_fee - s4q - abatement)

    duty = 0
    remaining, previous = dutiable, 0
    for band in duty_rule["rates"]:
        ceiling = band["upto"] * 100 if band["upto"] is not None else None
        slice_size = remaining if ceiling is None else min(remaining, max(0, ceiling - previous))
        duty += int(slice_size * band["rate_pct"] / 100)
        remaining -= slice_size
        previous = ceiling or previous
        if remaining <= 0:
            break

    # CGT: death is a deemed disposal at market value.
    gains = 0
    cgt_notes = []
    for a in data["assets"]:
        if a["base_cost_cents"] is None:
            cgt_notes.append(
                f"{a['description']}: no base cost recorded, so its gain cannot be "
                "computed and the CGT figure below is understated."
            )
            continue
        gains += max(0, a["value_cents"] - a["base_cost_cents"])
    cgt_exempt_note = ""
    if spouse_inherits:
        gains = 0
        cgt_exempt_note = (
            f"Assets accruing to {heir} roll over at base cost, so no CGT arises "
            "on this death — it arises on the second."
        )
    taxable_gain = max(0, gains - cgt_rule["death_year_exclusion"] * 100)
    included = int(taxable_gain * cgt_rule["inclusion_rate_pct"]["individual"] / 100)
    # Applied at the top marginal rate: at death most estates are in the top band.
    marginal = rules.load("income-tax")["brackets"][-1]["rate_pct"]
    cgt = int(included * marginal / 100)

    return {
        "gross_estate_cents": gross_estate,
        "liabilities_cents": liabilities_total,
        "net_estate_cents": net_estate,
        "deemed_property_cents": deemed,
        "retirement_excluded_cents": retirement,
        "executor_fee_cents": executor_fee,
        "master_fee_cents": master_fee,
        "spouse_inherits": spouse_inherits,
        "residuary_heir": heir,
        "s4q_deduction_cents": s4q,
        "abatement_cents": abatement,
        "dutiable_cents": dutiable,
        "estate_duty_cents": duty,
        "cgt_cents": cgt,
        "cgt_notes": cgt_notes,
        "cgt_exempt_note": cgt_exempt_note,
        "rules": [duty_rule, cgt_rule, fee_rule],
    }


def liquidity(data: dict, calc: dict) -> dict:
    """Cash needed at death, against cash the family can actually reach."""
    needed = (calc["estate_duty_cents"] + calc["cgt_cents"] +
              calc["executor_fee_cents"] + calc["master_fee_cents"])

    # Bond and short-term debt fall due; a bank may call the loan.
    debts = sum(lb["balance_cents"] for lb in data["liabilities"])

    # A ceded policy SETTLES the debt it secures. Counting the debt as needed
    # while excluding the policy from available would overstate the shortfall by
    # the whole bond — the policy is unavailable to the family precisely BECAUSE
    # it is discharging that liability.
    ceded_offset = 0
    ceded_notes = []
    for p in data["policies"]:
        if p["cession"] and p["sum_assured_cents"]:
            applied = min(p["sum_assured_cents"], max(0, debts - ceded_offset))
            ceded_offset += applied
            residual = p["sum_assured_cents"] - applied
            ceded_notes.append({
                "policy": p["insurer"], "proceeds_cents": p["sum_assured_cents"],
                "applied_to_debt_cents": applied, "residual_cents": residual,
                "record_id": p["record_id"],
            })
    debts_after_cession = max(0, debts - ceded_offset)
    needed += debts_after_cession

    sources, immediate = [], []
    for p in data["policies"]:
        if not p["sum_assured_cents"]:
            continue
        if p["cession"]:
            note = next((c for c in ceded_notes if c["record_id"] == p["record_id"]), None)
            residual = (note or {}).get("residual_cents", 0)
            sources.append({
                "label": f"{p['insurer']} ({p['class']})",
                "amount_cents": p["sum_assured_cents"],
                "available": bool(residual),
                "amount_available_cents": residual,
                "days_to_access": 30 * TYPICAL_MONTHS_TO_WIND_UP if residual else None,
                "why": (
                    f"ceded to {p['cession']['to']}: {money.fmt((note or {}).get('applied_to_debt_cents', 0))} "
                    f"settles that debt, leaving {money.fmt(residual)}"
                ),
                "record_id": p["record_id"],
            })
            continue
        nominated = bool(p["beneficiaries"])
        sources.append({
            "label": f"{p['insurer']} ({p['class']})",
            "amount_cents": p["sum_assured_cents"],
            "available": True,
            "days_to_access": 30 if nominated else 30 * TYPICAL_MONTHS_TO_WIND_UP,
            "why": ("paid to a nominated beneficiary, bypassing the estate"
                    if nominated else "falls into the estate; not reachable until wound up"),
            "record_id": p["record_id"],
        })

    for b in data["benefits"]:
        if b["kind"] in {"group_life", "funeral"} and b["benefit_cents"]:
            sources.append({
                "label": f"{b['employer']} ({b['kind'].replace('_', ' ')})",
                "amount_cents": b["benefit_cents"], "available": True,
                "days_to_access": 7 if b["kind"] == "funeral" else 60,
                "why": "employer benefit, paid outside the estate",
                "record_id": b["record_id"],
            })

    if data["cash_cents"] > 0:
        sources.append({
            "label": "Bank accounts",
            "amount_cents": data["cash_cents"], "available": False,
            "why": "frozen at death until the executor is appointed",
            "record_id": data["cash_ids"][0] if data["cash_ids"] else None,
        })

    available = sum(s.get("amount_available_cents", s["amount_cents"])
                    for s in sources if s.get("available"))
    immediate = [s for s in sources
                 if s.get("available") and s.get("days_to_access", 999) <= IMMEDIATE_NEED_DAYS]
    immediate_total = sum(s.get("amount_available_cents", s["amount_cents"])
                          for s in immediate)

    # The headline risk is not solvency, it is TIMING. An estate can be
    # comfortably solvent and still leave a family unable to buy groceries,
    # because everything that makes it solvent takes months to reach.
    monthly_need = 0
    try:
        from . import analyse
        flow = analyse.cashflow()
        months = max(1, len(flow["months"]))
        monthly_need = abs(flow["totals"]["personal_out_cents"]) // months
    except Exception:  # noqa: BLE001 — the liquidity view must survive without it
        pass

    months_covered = round(immediate_total / monthly_need, 1) if monthly_need else None
    return {
        "needed_cents": needed,
        "available_cents": available,
        "shortfall_cents": max(0, needed - available),
        "surplus_cents": max(0, available - needed),
        "immediate_30day_cents": immediate_total,
        "immediate_sources": immediate,
        "monthly_household_need_cents": monthly_need,
        "months_of_expenses_covered": months_covered,
        "timing_risk": bool(monthly_need and immediate_total < monthly_need * 3),
        "sources": sources,
        "ceded_applied_to_debt": ceded_notes,
        "breakdown": {
            "estate_duty": calc["estate_duty_cents"],
            "cgt": calc["cgt_cents"],
            "executor_fee": calc["executor_fee_cents"],
            "master_fee": calc["master_fee_cents"],
            "debts_after_cession": debts_after_cession,
        },
    }


def beneficiary_conflicts(data: dict) -> list[dict]:
    """Nominations that contradict the will.

    A nomination overrides the will for that asset. Neither document mentions
    the other, so this is invisible unless they are read together — and getting
    it wrong means the person the will names receives materially less than the
    testator intended.
    """
    out = []
    spouse_inherits, heir = _spouse_inherits(data)
    if not data["wills"]:
        return out
    if not heir:
        return [{
            "kind": "will_unreadable", "severity": "high",
            "title": "The will's residuary heir could not be determined",
            "detail": "Nominations cannot be checked against it. Confirm by hand.",
            "evidence": [w["id"] for w in data["wills"]],
        }]

    heir_low = heir.lower()
    for source, label in ((data["policies"], "policy"), (data["benefits"], "employee benefit")):
        for item in source:
            bens = item.get("beneficiaries") or []
            if not bens:
                continue
            amount = item.get("sum_assured_cents") or item.get("benefit_cents") or 0
            total_pct = sum(b.get("pct", 0) for b in bens)

            if abs(total_pct - 100) > 0.01:
                out.append({
                    "kind": "nomination_incomplete", "severity": "high",
                    "title": f"{label.title()} nominations total {total_pct:g}%, not 100%",
                    "detail": (
                        f"{item.get('insurer') or item.get('employer')} — the unallocated "
                        "share falls into the estate, where it attracts executor's fees "
                        "and is delayed by the winding-up."
                    ),
                    "evidence": [item["record_id"]],
                })

            elsewhere = [b for b in bens if heir_low not in b.get("name", "").lower()]
            if elsewhere and amount:
                diverted = sum(int(amount * b.get("pct", 0) / 100) for b in elsewhere)
                names = ", ".join(f"{b['name']} ({b['pct']:g}%)" for b in elsewhere)
                out.append({
                    "kind": "beneficiary_vs_will", "severity": "high",
                    "title": (
                        f"{money.fmt(diverted)} is nominated away from the will's heir"
                    ),
                    "detail": (
                        f"The will leaves the residue to **{heir}**, but the "
                        f"{label} from {item.get('insurer') or item.get('employer')} "
                        f"nominates {names}. A nomination OVERRIDES the will for that "
                        f"asset, so {heir} receives {money.fmt(diverted)} less than the "
                        "will appears to provide.\n\n"
                        "This may well be deliberate — nominating a trust for minor "
                        "children is common and sensible. But it should be a decision, "
                        "not a surprise, and neither document mentions the other."
                    ),
                    "evidence": [item["record_id"]] + [w["id"] for w in data["wills"]],
                })

    for p in data["policies"]:
        if p["cession"] and p["beneficiaries"]:
            out.append({
                "kind": "ceded_and_nominated", "severity": "high",
                "title": f"{p['insurer']} is both ceded AND has beneficiary nominations",
                "detail": (
                    f"The policy is ceded to {p['cession']['to']}, so proceeds settle that "
                    "debt first. The nominated beneficiaries receive only what remains — "
                    "possibly nothing. Anyone reading the nomination alone would expect "
                    f"{money.fmt(p['sum_assured_cents'])}."
                ),
                "evidence": [p["record_id"]],
            })
    return out


def report() -> dict:
    if not vault.is_initialised():
        return {"schema": "estate/1", "error": "no vault — run /lifeos-init"}

    data = gather()
    calc = duty_and_cgt(data)
    liq = liquidity(data, calc)
    conflicts = beneficiary_conflicts(data)

    comps = [rules.Computation(
        calc["estate_duty_cents"], "Estate duty", rules_used=calc["rules"])]

    missing = []
    if not data["assets"]:
        missing.append("no property or movables recorded")
    if not data["wills"]:
        missing.append("no will recorded")
    if not data["policies"]:
        missing.append("no life cover recorded")

    return {
        "schema": "estate/1",
        "at": clock.stamp(),
        "as_at": clock.today(),
        "calculation": {k: v for k, v in calc.items() if k != "rules"},
        "liquidity": liq,
        "conflicts": conflicts,
        "missing": missing,
        "caveat": rules.caveat(comps),
        "assumptions": {
            "months_to_wind_up": TYPICAL_MONTHS_TO_WIND_UP,
            "executor_fee": "the maximum prescribed tariff, which is negotiable",
            "cgt_marginal_rate": "top marginal rate assumed",
        },
    }


def to_markdown(rep: dict) -> str:
    if rep.get("error"):
        return f"**{rep['error']}**"
    c, liq = rep["calculation"], rep["liquidity"]
    lines = [f"# Estate — modelled at {rep['as_at']}", ""]
    if rep["caveat"]:
        lines += [f"> {rep['caveat']}", ""]
    if rep["missing"]:
        lines += ["> **Incomplete picture:** " + "; ".join(rep["missing"]) +
                  ". Every figure below is understated.", ""]

    short = liq["shortfall_cents"]
    lines += [
        "## Can the family reach cash?",
        "",
        f"**Needed at death: {money.fmt(liq['needed_cents'])}**  ·  "
        f"reachable: {money.fmt(liq['available_cents'])}",
        "",
        (f"### Shortfall: {money.fmt(short)}" if short
         else f"### Solvent, with {money.fmt(liq['surplus_cents'])} to spare"),
        "",
        f"**But in the first 30 days the family can reach only "
        f"{money.fmt(liq['immediate_30day_cents'])}.**",
        "",]
    if liq.get("timing_risk"):
        lines += [
            f"> Household spending runs at about "
            f"{money.fmt(liq['monthly_household_need_cents'])} a month, so that is "
            f"**{liq['months_of_expenses_covered']} months of expenses**. An estate can be "
            "comfortably solvent and still leave a family unable to buy groceries: "
            "everything that makes it solvent takes months to reach. This is the single "
            "most common failure in an otherwise well-planned estate, and the fix is "
            "usually a small policy paid to a nominated beneficiary rather than to the "
            "estate.",
            "",
        ]
    lines += [
        "| What falls due | Amount |", "|---|---|",
    ]
    for k, v in liq["breakdown"].items():
        lines.append(f"| {k.replace('_', ' ').title()} | {money.fmt(v)} |")
    lines += ["", "| Source | Amount | Reachable? |", "|---|---|---|"]
    for s in liq["sources"]:
        when = (f"yes, ~{s['days_to_access']} days" if s.get("available")
                else f"**no** — {s['why']}")
        lines.append(f"| {s['label']} | {money.fmt(s['amount_cents'])} | {when} |")

    lines += ["", "## Duty and CGT", "", "| | |", "|---|---|",
              f"| Gross estate | {money.fmt(c['gross_estate_cents'])} |",
              f"| Less liabilities | {money.fmt(-c['liabilities_cents'])} |",
              f"| Deemed property (life policies, s3(3)(a)(ii)) | {money.fmt(c['deemed_property_cents'])} |",
              f"| Retirement interests excluded | {money.fmt(c['retirement_excluded_cents'])} |",
              f"| Executor's fee (max tariff, incl. VAT) | {money.fmt(-c['executor_fee_cents'])} |",
              f"| Master's fee | {money.fmt(-c['master_fee_cents'])} |",
              f"| s4(q) spousal roll-over | {money.fmt(-c['s4q_deduction_cents'])} |",
              f"| s4A abatement | {money.fmt(-c['abatement_cents'])} |",
              f"| **Dutiable amount** | **{money.fmt(c['dutiable_cents'])}** |",
              f"| **Estate duty** | **{money.fmt(c['estate_duty_cents'])}** |",
              f"| **CGT on deemed disposal** | **{money.fmt(c['cgt_cents'])}** |", ""]
    if c["cgt_exempt_note"]:
        lines += [f"_{c['cgt_exempt_note']}_", ""]
    for n in c["cgt_notes"]:
        lines += [f"- {n}"]
    if c["spouse_inherits"]:
        lines += ["", "**s4(q) defers duty, it does not remove it.** The assets rolling "
                      f"over to {c['residuary_heir']} are taxed in the second dying "
                      "spouse's estate. A plan that shows zero duty on the first death "
                      "has moved the problem, not solved it.", ""]

    lines += ["## Nominations versus the will", ""]
    if not rep["conflicts"]:
        lines.append("No conflicts detected.")
    for f in rep["conflicts"]:
        lines += [f"### {f['title']}", "", f["detail"], ""]

    lines += ["---",
              "_Estate duty, CGT and fee figures are modelled from cached rules and are "
              "not a calculation to plan around. Estate planning requires a registered "
              "financial advisor, an attorney, and — for the wind-up — the Master's Office._"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lifeos.estate")
    ap.add_argument("--markdown", action="store_true")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)
    rep = report()
    text = to_markdown(rep)
    if args.write and not rep.get("error"):
        atomic.write_text(vault.path("reports", f"estate-{clock.today()}.md"), text)
    print(text if args.markdown else json.dumps(rep, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
