"""THE COVER MAP — what is covered, by whom, at what cost, and where the holes are.

The second flagship, and the one that justifies holding everything in one graph.
No single document answers "am I covered if I cannot work for six months" — the
medical scheme covers hospital, the gap policy covers the shortfall the scheme
leaves, the employer covers a portion of income, and a personal policy covers
another portion that may not stack with it. Each document is silent about the
others.

Two findings here are the ones a person cannot reach on their own:

  * **Income protection cannot stack indefinitely.** SA insurers underwrite to
    roughly 75% of pre-tax income in aggregate. Holding employer cover AND a
    personal policy above that ceiling means paying a premium for a benefit
    that will not be paid.

  * **Day-to-day and chronic care fall between the stools.** Gap cover excludes
    them and the scheme's savings run out; the hole only appears when the two
    are read together.

Usage:  python -m lifeos.covermap [--markdown]
"""

from __future__ import annotations

import argparse
import json
import sys

from . import atomic, clock, ledger, money, vault

# SA insurers underwrite income protection to roughly this share of pre-tax
# income in aggregate across all policies. It is an industry convention rather
# than a statute, so it lives here as a documented assumption with a date, and
# the finding it drives says so.
INCOME_PROTECTION_CEILING_PCT = 75.0
ASSUMPTIONS_AS_AT = "2026-08-15"

# The events a household actually needs covering, in the order they hurt.
EVENTS = [
    ("hospital",        "Hospital admission"),
    ("day_to_day",      "Day-to-day medical (GP, dentist, optometry)"),
    ("chronic",         "Chronic medication"),
    ("shortfall",       "Specialist shortfall above scheme rate"),
    ("dread_disease",   "Dread disease / severe illness"),
    ("disability_lump", "Permanent disability (lump sum)"),
    ("income_loss",     "Loss of income through illness or injury"),
    ("death",           "Death"),
    ("funeral",         "Funeral costs"),
]


def _annual(cents: int | None, frequency: str = "monthly") -> int:
    if cents is None:
        return 0
    return cents * {"monthly": 12, "quarterly": 4, "annual": 1, "single": 0}.get(frequency, 12)


def _sources() -> dict:
    return {
        "medical": list(ledger.read("medical-aid")),
        "benefits": list(ledger.read("employee-benefits")),
        "policies": list(ledger.read("policies")),
    }


def build_map() -> dict:
    src = _sources()
    scheme = next((m for m in src["medical"] if m["kind"] == "scheme"), None)
    gap = next((m for m in src["medical"] if m["kind"] == "gap"), None)
    benefits = {b["kind"]: b for b in src["benefits"]}
    policies = src["policies"]

    def by_class(cls: str) -> list[dict]:
        return [p for p in policies if p.get("class") == cls]

    gap_excludes = ""
    if gap:
        for p in gap.get("providers", []):
            if p.get("kind") == "excludes":
                gap_excludes = p.get("name", "")

    rows: list[dict] = []

    def row(key, label, covered_by, limit, annual_cost, note="", status="covered"):
        rows.append({
            "event": key, "label": label, "covered_by": covered_by,
            "limit": limit, "annual_cost_cents": annual_cost,
            "status": status, "note": note,
        })

    # ── hospital ─────────────────────────────────────────────────────────────
    if scheme:
        row("hospital", "Hospital admission", [scheme["provider"]],
            "Scheme hospital benefit",
            _annual((scheme.get("premium") or {}).get("cents")),
            "Cover is at the SCHEME RATE. Specialists commonly charge a multiple of "
            "it; the difference is the shortfall row below.")
    else:
        row("hospital", "Hospital admission", [], None, 0,
            "No medical scheme recorded. A single admission is routinely six figures.",
            status="uncovered")

    # ── shortfall ────────────────────────────────────────────────────────────
    if gap:
        limit = next((s for s in gap.get("sublimits", []) if s["kind"] == "annual_limit"), None)
        row("shortfall", "Specialist shortfall above scheme rate", [gap["provider"]],
            f"up to {money.fmt(limit['limit']['cents'])}/yr" if limit else "see schedule",
            _annual((gap.get("premium") or {}).get("cents")))
    else:
        row("shortfall", "Specialist shortfall above scheme rate", [], None, 0,
            "No gap cover recorded. The scheme pays its rate; the balance is yours.",
            status="uncovered")

    # ── day-to-day and chronic — the hole only visible when read together ────
    savings = ((scheme or {}).get("savings") or {}).get("annual")
    for key, label, word in (("day_to_day", "Day-to-day medical (GP, dentist, optometry)", "day_to_day"),
                             ("chronic", "Chronic medication", "chronic")):
        excluded_by_gap = word in gap_excludes
        if savings and savings.get("cents"):
            row(key, label, [(scheme or {}).get("provider", "scheme")],
                f"{money.fmt(savings['cents'])}/yr medical savings", 0,
                ("Gap cover explicitly EXCLUDES this. Once the savings account is "
                 "spent, and until the above-threshold benefit begins, this is paid "
                 "in cash." if excluded_by_gap else ""),
                status="partial" if excluded_by_gap else "covered")
        else:
            row(key, label, [], None, 0,
                "No medical savings recorded and gap cover excludes it."
                if excluded_by_gap else "Not recorded.",
                status="uncovered")

    # ── dread disease ────────────────────────────────────────────────────────
    dd = by_class("dread_disease")
    if dd:
        row("dread_disease", "Dread disease / severe illness",
            [p["insurer"] for p in dd],
            money.fmt(sum((p.get("sum_assured") or {}).get("cents", 0) for p in dd)),
            sum(_annual((p.get("premium") or {}).get("cents")) for p in dd))
    else:
        row("dread_disease", "Dread disease / severe illness", [], None, 0,
            "No dread disease cover recorded. A cancer diagnosis brings costs a "
            "medical scheme does not pay: travel, home alterations, lost income.",
            status="uncovered")

    # ── disability lump sum ──────────────────────────────────────────────────
    dis_pol = by_class("disability")
    dis_emp = benefits.get("disability")
    sources = [p["insurer"] for p in dis_pol] + ([dis_emp["employer"]] if dis_emp else [])
    total = sum((p.get("sum_assured") or {}).get("cents", 0) for p in dis_pol) + \
        ((dis_emp or {}).get("benefit") or {}).get("cents", 0)
    row("disability_lump", "Permanent disability (lump sum)", sources,
        money.fmt(total) if total else None,
        sum(_annual((p.get("premium") or {}).get("cents")) for p in dis_pol),
        "Employer cover ends when employment does — it is not portable."
        if dis_emp and not dis_pol else "",
        status="covered" if total else "uncovered")

    # ── income protection ────────────────────────────────────────────────────
    ip_pol = by_class("income_protection")
    ip_emp = benefits.get("income_protection")
    ip_monthly = sum((p.get("monthly_benefit") or {}).get("cents", 0) for p in ip_pol) + \
        ((ip_emp or {}).get("benefit") or {}).get("cents", 0)
    row("income_loss", "Loss of income through illness or injury",
        [p["insurer"] for p in ip_pol] + ([ip_emp["employer"]] if ip_emp else []),
        f"{money.fmt(ip_monthly)}/month" if ip_monthly else None,
        sum(_annual((p.get("premium") or {}).get("cents")) for p in ip_pol),
        status="covered" if ip_monthly else "uncovered")

    # ── death ────────────────────────────────────────────────────────────────
    life_pol = by_class("life")
    life_emp = benefits.get("group_life")
    death_total = sum((p.get("sum_assured") or {}).get("cents", 0) for p in life_pol) + \
        ((life_emp or {}).get("benefit") or {}).get("cents", 0)
    row("death", "Death", [p["insurer"] for p in life_pol] +
        ([life_emp["employer"]] if life_emp else []),
        money.fmt(death_total) if death_total else None,
        sum(_annual((p.get("premium") or {}).get("cents")) for p in life_pol),
        "Group life ends with employment. If the personal policy is ceded to a "
        "bond, its proceeds settle the bond first."
        if life_emp and any(p.get("cession") for p in life_pol) else "",
        status="covered" if death_total else "uncovered")

    # ── funeral ──────────────────────────────────────────────────────────────
    fun_pol = by_class("funeral")
    fun_emp = benefits.get("funeral")
    fun_total = sum((p.get("sum_assured") or {}).get("cents", 0) for p in fun_pol) + \
        ((fun_emp or {}).get("benefit") or {}).get("cents", 0)
    row("funeral", "Funeral costs",
        [p["insurer"] for p in fun_pol] + ([fun_emp["employer"]] if fun_emp else []),
        money.fmt(fun_total) if fun_total else None, 0,
        "Funeral cover usually pays within 48 hours, which is why it matters "
        "separately from life cover — an estate is frozen.",
        status="covered" if fun_total else "uncovered")

    order = {k: i for i, (k, _) in enumerate(EVENTS)}
    rows.sort(key=lambda r: order.get(r["event"], 99))

    return {
        "rows": rows,
        "annual_cost_cents": sum(r["annual_cost_cents"] for r in rows),
        "scheme": scheme, "gap": gap, "benefits": benefits, "policies": policies,
    }


def findings(cover: dict) -> list[dict]:
    """Cross-domain findings. Each is invisible from inside a single document."""
    out: list[dict] = []
    benefits = cover["benefits"]
    policies = cover["policies"]

    def by_class(cls):
        return [p for p in policies if p.get("class") == cls]

    # ── income protection stacking ───────────────────────────────────────────
    ip_pol = by_class("income_protection")
    ip_emp = benefits.get("income_protection")
    if ip_pol and ip_emp:
        emp_monthly = (ip_emp.get("benefit") or {}).get("cents", 0)
        pol_monthly = sum((p.get("monthly_benefit") or {}).get("cents", 0) for p in ip_pol)
        combined = emp_monthly + pol_monthly

        salary_annual = None
        for b in ledger.read("employee-benefits"):
            if b.get("multiple_of_salary") and b.get("benefit") and b["kind"] == "group_life":
                salary_annual = int(b["benefit"]["cents"] / b["multiple_of_salary"])
                break
        if salary_annual:
            ceiling = int(salary_annual / 12 * INCOME_PROTECTION_CEILING_PCT / 100)
            if combined > ceiling:
                excess = combined - ceiling
                wasted = sum((p.get("premium") or {}).get("cents", 0) for p in ip_pol) * 12
                out.append({
                    "kind": "cover_duplication",
                    "severity": "high",
                    "title": (
                        f"Income protection is over-insured by {money.fmt(excess)}/month"
                    ),
                    "detail": (
                        f"Employer cover pays {money.fmt(emp_monthly)}/month and the personal "
                        f"policy pays {money.fmt(pol_monthly)}/month — {money.fmt(combined)} "
                        f"combined. SA insurers underwrite to about "
                        f"{INCOME_PROTECTION_CEILING_PCT:.0f}% of pre-tax income in aggregate, "
                        f"roughly {money.fmt(ceiling)}/month here. Cover above that ceiling is "
                        f"unlikely to be paid, so up to {money.fmt(wasted)} a year of premium "
                        f"may be buying nothing.\n\n"
                        f"Before cancelling anything: employer cover ENDS WITH EMPLOYMENT and "
                        f"the personal policy does not. The usual answer is to keep the "
                        f"personal policy and reduce it, not to drop it. Confirm the aggregate "
                        f"limit with the insurer — it is an industry convention, not a statute."
                    ),
                    "annual_cost_cents": wasted,
                    "evidence": [p["id"] for p in ip_pol] + [ip_emp["id"]],
                    "as_at": ASSUMPTIONS_AS_AT,
                })

    # ── employer-only cover is not portable ──────────────────────────────────
    for kind, label in (("group_life", "life"), ("disability", "disability")):
        emp = benefits.get(kind)
        personal = by_class("life" if kind == "group_life" else "disability")
        if emp and not personal:
            out.append({
                "kind": "cover_portability",
                "severity": "high",
                "title": f"All {label} cover is through the employer",
                "detail": (
                    f"{money.fmt((emp.get('benefit') or {}).get('cents', 0))} of {label} cover "
                    f"is provided by {emp['employer']}. It ends on the day employment ends — "
                    "resignation, retrenchment or retirement — and re-insuring later is priced "
                    "at the age and health you are then, not now."
                ),
                "annual_cost_cents": 0,
                "evidence": [emp["id"]],
            })

    # ── ceded life cover is not available to the family ──────────────────────
    for p in by_class("life"):
        if p.get("cession"):
            sa = (p.get("sum_assured") or {}).get("cents", 0)
            out.append({
                "kind": "cover_cession",
                "severity": "high",
                "title": f"{money.fmt(sa)} of life cover is ceded and will not reach the family",
                "detail": (
                    f"Policy {p.get('policy_no', p['ref'])} is ceded to "
                    f"{p['cession']['to']}. On death the proceeds settle that debt first. "
                    "Any needs analysis that counts this policy as available to dependants "
                    "is overstating cover by the ceded amount."
                ),
                "annual_cost_cents": 0,
                "evidence": [p["id"]],
            })

    # ── health stack holes ───────────────────────────────────────────────────
    for r in cover["rows"]:
        if r["status"] == "uncovered":
            out.append({
                "kind": "cover_gap", "severity": "high",
                "title": f"No cover recorded for: {r['label']}",
                "detail": r["note"] or "Nothing in the vault covers this event.",
                "annual_cost_cents": 0, "evidence": [],
            })
        elif r["status"] == "partial":
            out.append({
                "kind": "cover_partial", "severity": "medium",
                "title": f"Partially covered: {r['label']}",
                "detail": r["note"], "annual_cost_cents": 0, "evidence": [],
            })

    severity_rank = {"high": 0, "medium": 1, "low": 2}
    out.sort(key=lambda f: (severity_rank.get(f["severity"], 3), -f.get("annual_cost_cents", 0)))
    return out


def report() -> dict:
    if not vault.is_initialised():
        return {"schema": "covermap/1", "error": "no vault — run /lifeos-init"}
    cover = build_map()
    return {
        "schema": "covermap/1",
        "at": clock.stamp(),
        "assumptions_as_at": ASSUMPTIONS_AS_AT,
        "rows": cover["rows"],
        "annual_cost_cents": cover["annual_cost_cents"],
        "findings": findings(cover),
        "counts": {
            s: sum(1 for r in cover["rows"] if r["status"] == s)
            for s in ("covered", "partial", "uncovered")
        },
    }


_ICON = {"covered": "yes", "partial": "PARTIAL", "uncovered": "NO"}


def to_markdown(rep: dict) -> str:
    if rep.get("error"):
        return f"**{rep['error']}**"
    lines = [
        "# Health and risk cover map",
        "",
        f"Total known annual cost: **{money.fmt(rep['annual_cost_cents'])}**",
        f"{rep['counts']['covered']} covered · {rep['counts']['partial']} partial · "
        f"**{rep['counts']['uncovered']} uncovered**",
        "",
        "| Event | Covered | By | Limit |",
        "|---|---|---|---|",
    ]
    for r in rep["rows"]:
        lines.append(
            f"| {r['label']} | {_ICON[r['status']]} | "
            f"{', '.join(r['covered_by']) or '—'} | {r['limit'] or '—'} |"
        )
    lines += ["", "## What no single document told you", ""]
    for f in rep["findings"]:
        cost = f" — up to {money.fmt(f['annual_cost_cents'])}/yr" if f.get("annual_cost_cents") else ""
        lines += [f"### {f['title']}{cost}", "", f["detail"], ""]
    lines += [
        "---",
        f"_Industry conventions used here are as at {rep['assumptions_as_at']}. "
        "This is preparation for a conversation with a registered financial "
        "advisor, not advice._",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lifeos.covermap")
    ap.add_argument("--markdown", action="store_true")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)
    rep = report()
    text = to_markdown(rep)
    if args.write and not rep.get("error"):
        path = vault.path("reports", f"cover-map-{clock.today()}.md")
        atomic.write_text(path, text)
        rep["written"] = vault.rel(path)
    print(text if args.markdown else json.dumps(rep, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
