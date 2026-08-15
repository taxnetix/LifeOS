"""TAX — deadline calendar, credits, deduction headroom, effective rate.

Everything here computes from `.claude/rules/za/`, never from memory, and every
figure carries the rulebook it used with that rulebook's "as at" date and
verification status. See lifeos.rules.

What this module does NOT do, deliberately:

  * decide that anything is deductible — it computes headroom and flags spend
    a practitioner should see
  * file, submit, or calculate a final liability — the assessment needs the
    full picture, including items LifeOS has never seen

Usage:  python -m lifeos.tax [--markdown]
"""

from __future__ import annotations

import argparse
import calendar
import json
import sys
from datetime import date

from . import atomic, calendar_za, clock, ledger, money, rules, vault

# ── deadlines ────────────────────────────────────────────────────────────────


def _next_fixed(today: date, month: int, day: int, leap_aware: bool = False) -> date:
    for year in (today.year, today.year + 1):
        d = day
        if leap_aware and month == 2:
            d = 29 if calendar.isleap(year) else 28
        d = min(d, calendar.monthrange(year, month)[1])
        candidate = date(year, month, d)
        if candidate >= today:
            return candidate
    raise AssertionError("unreachable")


def _applies(obligation: dict, subject: dict) -> bool:
    applies = obligation.get("applies_to")
    kinds = applies if isinstance(applies, list) else [applies]
    return subject["kind"] in kinds


def _subjects() -> list[dict]:
    """Taxpayers derived from the profile and the ledgers.

    A person with business income is a provisional taxpayer; an entity is a
    company or a trust. Getting this wrong means missing an IRP6, so where it
    cannot be determined the subject is listed with a note rather than assumed
    not to apply.
    """
    from .readiness import load_profile

    prof = load_profile()
    out = []
    entity_refs = {e.get("ref") for e in (prof.get("entities") or [])}
    has_business = any(
        t.get("entity_id") in entity_refs for t in ledger.read("transactions")
    )
    has_rental = any(
        t.get("category") == "income" and t.get("subcategory") == "rental"
        for t in ledger.read("transactions")
    )

    for p in prof.get("people") or []:
        if p.get("relation") not in {"self", "spouse"}:
            continue
        out.append({"ref": p.get("ref"), "label": p.get("name"), "kind": "individual"})
        if has_business or has_rental:
            out.append({
                "ref": p.get("ref"), "label": p.get("name"), "kind": "provisional_taxpayer",
                "why": "income outside PAYE (business or rental) was seen in the ledger",
            })
    for e in prof.get("entities") or []:
        kind = "trust" if e.get("form") == "trust" else "company"
        out.append({"ref": e.get("ref"), "label": e.get("name"), "kind": kind,
                    "year_end": e.get("year_end")})
        out.append({"ref": e.get("ref"), "label": e.get("name"), "kind": "provisional_taxpayer"})
    return out


def deadlines(horizon_days: int = 365) -> list[dict]:
    rule = rules.load("deadlines")
    today = date.fromisoformat(clock.today())
    out: list[dict] = []

    for subject in _subjects():
        for ob in rule["obligations"]:
            if not _applies(ob, subject):
                continue

            if ob.get("frequency") == "monthly":
                due = _next_fixed(today, today.month if today.day <= ob["day"]
                                  else (today.month % 12) + 1, ob["day"])
            elif ob.get("frequency") == "bi_monthly":
                month = today.month if today.day <= ob["day"] else (today.month % 12) + 1
                if month % 2:
                    month = (month % 12) + 1
                due = _next_fixed(today, month, ob["day"])
            elif ob.get("months_after_year_end"):
                ye = subject.get("year_end") or "02-28"
                m, d = (int(x) for x in str(ye).split("-"))
                base = _next_fixed(today, m, d, leap_aware=(m == 2))
                months = ob["months_after_year_end"]
                year = base.year + (months // 12)
                due = date(year, base.month, min(base.day, calendar.monthrange(year, base.month)[1]))
            else:
                due = _next_fixed(today, ob["month"], ob["day"], ob.get("leap_aware", False))

            days = (due - today).days
            if days > horizon_days:
                continue
            out.append({
                "kind": ob["kind"], "label": ob["label"],
                "taxpayer_ref": subject["ref"], "taxpayer": subject["label"],
                "applies_because": subject.get("why", subject["kind"]),
                "due_on": due.isoformat(), "days_until": days,
                "lead_days": ob["lead_days"],
                "in_lead_window": days <= ob["lead_days"],
                "tax_year": calendar_za.tax_year_of(due),
            })

    out.sort(key=lambda x: x["days_until"])
    return out


# ── computations ─────────────────────────────────────────────────────────────


def medical_credits() -> rules.Computation:
    rule = rules.load("medical-credits")
    schemes = [m for m in ledger.read("medical-aid") if m["kind"] == "scheme"]
    if not schemes:
        return rules.Computation(None, "Medical scheme fees tax credit",
                                 rules_used=[rule],
                                 notes=["No medical scheme recorded."])
    scheme = schemes[0]
    members = scheme.get("members") or []
    # The certificate lists dependants in a table the field extractor does not
    # read, so fall back to the profile and say so rather than assuming one.
    if members:
        n = len(members)
        basis = "scheme member list"
    else:
        from .readiness import load_profile
        n = len(load_profile().get("people") or []) or 1
        basis = "profile household size (the certificate's dependant table was not parsed)"

    monthly = rule["main_member"]
    if n >= 2:
        monthly += rule["first_dependant"]
    if n > 2:
        monthly += rule["each_additional_dependant"] * (n - 2)

    return rules.Computation(
        value=monthly * 12 * 100,   # cents
        label="Medical scheme fees tax credit (annual)",
        formula=(
            f"({rule['main_member']} main"
            + (f" + {rule['first_dependant']} first dependant" if n >= 2 else "")
            + (f" + {rule['each_additional_dependant']} x {n - 2} additional" if n > 2 else "")
            + ") x 12 months"
        ),
        rules_used=[rule],
        inputs={"beneficiaries": n, "basis": basis},
        record_ids=[scheme["id"]],
        notes=[
            "This is the s6A credit only. A further s6B credit may apply to "
            "out-of-pocket expense and to contributions above a multiple of s6A; "
            "it needs the full assessment and is not computed here.",
        ],
    )


def retirement_headroom() -> rules.Computation:
    rule = rules.load("retirement-deduction")
    salary = None
    salary_id = None
    for b in ledger.read("employee-benefits"):
        if b.get("multiple_of_salary") and b.get("benefit") and b["kind"] == "group_life":
            salary = int(b["benefit"]["cents"] / b["multiple_of_salary"])
            salary_id = b["id"]
            break
    if salary is None:
        return rules.Computation(None, "Retirement contribution headroom",
                                 rules_used=[rule],
                                 notes=["No pensionable salary found in the ledgers."])

    tax_year = calendar_za.tax_year_of(date.fromisoformat(clock.today()))
    start, end = calendar_za.tax_year_bounds(tax_year)
    contributed = 0
    ids = []
    for t in ledger.read("transactions"):
        if ("retirement" in (t.get("tax_relevance") or [])
                and t["amount"]["cents"] < 0
                and start.isoformat() <= t["posted_on"] <= end.isoformat()):
            contributed += abs(t["amount"]["cents"])
            ids.append(t["id"])
    for b in ledger.read("employee-benefits"):
        c = (b.get("contribution") or {})
        for who in ("employee", "employer"):
            if c.get(who):
                contributed += c[who]["cents"] * 12
                ids.append(b["id"])

    pct_cap = int(salary * rule["percentage_of_income"] / 100)
    cap = min(pct_cap, rule["annual_cap"] * 100)
    return rules.Computation(
        value=max(0, cap - contributed),
        label="Retirement contribution headroom for this tax year",
        formula=(
            f"min({rule['percentage_of_income']}% x {money.fmt(salary)} = {money.fmt(pct_cap)}, "
            f"cap {money.fmt(rule['annual_cap'] * 100)}) - contributed {money.fmt(contributed)}"
        ),
        rules_used=[rule],
        inputs={"salary_cents": salary, "contributed_cents": contributed,
                "deductible_cap_cents": cap, "tax_year": tax_year},
        record_ids=([salary_id] if salary_id else []) + ids[:20],
        notes=[
            "Contributions above the cap are NOT lost: they roll forward and "
            "reduce the taxable portion of the eventual lump sum or annuity. "
            "Over-contributing is a timing question, not waste.",
            "The salary is inferred from group life cover as a multiple of "
            "salary, so it is pensionable salary and may differ from total "
            "remuneration, which is the base the deduction actually uses.",
        ],
    )


def tfsa_position() -> rules.Computation:
    rule = rules.load("tfsa-limits")
    holdings = [h for h in ledger.read("holdings") if h["kind"] == "tfsa"]
    if not holdings:
        return rules.Computation(None, "TFSA position", rules_used=[rule],
                                 notes=["No tax-free savings account recorded."])
    value = sum(h["value"]["cents"] for h in holdings)
    return rules.Computation(
        value=value,
        label="TFSA value",
        formula="sum of tax-free holdings",
        rules_used=[rule],
        inputs={"annual_limit_cents": rule["annual_limit"] * 100,
                "lifetime_limit_cents": rule["lifetime_limit"] * 100},
        record_ids=[h["id"] for h in holdings],
        notes=[
            "The lifetime limit counts CONTRIBUTIONS, not value, so this figure "
            "cannot tell you how much room is left — growth does not consume "
            "room and a withdrawal does not restore it. Contribution history is "
            "needed, and LifeOS does not have it.",
            f"Excess contributions are taxed at {rule['penalty_pct']}%.",
        ],
    )


def report(horizon_days: int = 365) -> dict:
    if not vault.is_initialised():
        return {"schema": "tax/1", "error": "no vault — run /lifeos-init"}

    comps = [medical_credits(), retirement_headroom(), tfsa_position()]
    dl = deadlines(horizon_days)
    return {
        "schema": "tax/1",
        "at": clock.stamp(),
        "current_tax_year": calendar_za.tax_year_of(date.fromisoformat(clock.today())),
        "deadlines": dl,
        "in_lead_window": [d for d in dl if d["in_lead_window"]],
        "computations": [c.to_dict() for c in comps],
        "caveat": rules.caveat(comps),
        "rules_status": rules.check(),
    }


def to_markdown(rep: dict) -> str:
    if rep.get("error"):
        return f"**{rep['error']}**"
    lines = [f"# Tax — {rep['current_tax_year']} year of assessment", ""]

    if rep["caveat"]:
        lines += [f"> {rep['caveat']}", ""]

    urgent = rep["in_lead_window"]
    lines += ["## Due now", ""]
    if urgent:
        for d in urgent:
            when = ("**OVERDUE**" if d["days_until"] < 0
                    else f"in {d['days_until']} days")
            lines.append(f"- **{d['label']}** — {d['taxpayer']}, {d['due_on']} ({when})")
    else:
        lines.append("Nothing inside its lead window.")

    lines += ["", "## Next 12 months", "", "| Due | Obligation | Taxpayer | Days |",
              "|---|---|---|---|"]
    for d in rep["deadlines"][:20]:
        lines.append(f"| {d['due_on']} | {d['label']} | {d['taxpayer']} | {d['days_until']} |")

    lines += ["", "## Positions", ""]
    for c in rep["computations"]:
        if c["value"] is None:
            lines += [f"**{c['label']}** — not computed. {' '.join(c['notes'])}", ""]
            continue
        flag = " ⚠︎ unverified rules" if c["requires_verification"] else ""
        lines += [f"### {c['label']}: {money.fmt(c['value'])}{flag}", "",
                  f"`{c['formula']}`", ""]
        for n in c["notes"]:
            lines.append(f"- {n}")
        lines.append("")

    lines += ["---",
              "_LifeOS computes headroom and flags what a practitioner should see. "
              "It does not determine deductibility, and it does not file._"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lifeos.tax")
    ap.add_argument("--markdown", action="store_true")
    ap.add_argument("--horizon", type=int, default=365)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)
    rep = report(args.horizon)
    text = to_markdown(rep)
    if args.write and not rep.get("error"):
        atomic.write_text(vault.path("reports", f"tax-{clock.today()}.md"), text)
    print(text if args.markdown else json.dumps(rep, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
