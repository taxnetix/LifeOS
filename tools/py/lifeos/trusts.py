"""TRUSTS — s7C exposure, independence, compliance calendar, attribution.

Four findings a trustee cannot reach from any single document:

  * **s7C.** An interest-free loan to a trust is a donation of the interest
    forgone, every year, payable in cash by the LENDER. Nothing on the loan
    account says so, and the amount is invisible until it is computed.

  * **Independence.** A trust whose only trustees are the founder and a
    beneficiary is materially easier to attack as the founder's alter ego. The
    deed does not flag it; the letters of authority merely list who is there.

  * **Distributions without resolutions.** The conduit principle depends on
    income being VESTED during the year. Without a dated resolution, SARS may
    tax it in the trust at the flat rate instead of in the beneficiary's hands.

  * **Separation.** Trust affairs and personal affairs must be demonstrably
    distinct — while the relationship graph still links them.

Usage:  python -m lifeos.trusts [--markdown]
"""

from __future__ import annotations

import argparse
import calendar
import json
import sys
from datetime import date

from . import atomic, calendar_za, clock, ledger, money, rules, vault


def _load(name: str):
    return rules.load(name)


# ── s7C ──────────────────────────────────────────────────────────────────────


def s7c_exposure() -> list[dict]:
    """Deemed donation on low-interest loans to a trust, per loan, per year."""
    rule = _load("s7c")
    official = float(rule["official_rate_pct"])
    donations_pct = float(rule["donations_tax_pct"])
    exemption = int(rule["annual_donations_exemption"]) * 100

    out = []
    for la in ledger.read("loan-accounts"):
        if la.get("direction") != "owed_by_trust":
            continue
        balance = (la.get("balance") or {}).get("cents", 0)
        if balance <= 0:
            continue
        actual_rate = float(la.get("interest_rate_pct") or 0.0)
        shortfall_pct = max(0.0, official - actual_rate)
        deemed = int(balance * shortfall_pct / 100)
        if deemed <= 0:
            continue

        # The R100k exemption is shared across ALL of the lender's donations for
        # the year, so applying it in full here is the most favourable case.
        after_exemption = max(0, deemed - exemption)
        tax = int(after_exemption * donations_pct / 100)

        out.append({
            "trust_ref": la.get("trust_ref"),
            "lender_ref": la.get("counterparty_ref"),
            "balance_cents": balance,
            "actual_rate_pct": actual_rate,
            "official_rate_pct": official,
            "shortfall_pct": round(shortfall_pct, 2),
            "deemed_donation_cents": deemed,
            "exemption_applied_cents": min(deemed, exemption),
            "donations_tax_cents": tax,
            "record_id": la["id"],
            "rule": rule,
        })
    return out


# ── independence ─────────────────────────────────────────────────────────────


def independence(trust: dict) -> dict:
    """Is there a trustee independent of the founder and the beneficiaries?"""
    rule = _load("trust-compliance")
    spec = rule["independent_trustee"]
    applies = trust.get("type") in (spec.get("applies_to") or [])

    trustees = [t for t in ledger.read("trustees")
                if t.get("trust_ref") == trust.get("ref")
                and t.get("kind") == "appointment"
                and not t.get("resigned_on")]

    beneficiary_names = {
        str(b.get("person_ref") or b.get("class_description") or "").lower()
        for b in (trust.get("beneficiaries") or [])
    }
    founder = str(trust.get("founder_ref") or "").lower()

    flagged = []
    for t in trustees:
        name = str(t.get("person_ref") or t.get("name") or "").lower()
        if t.get("independent"):
            continue
        if name and (name == founder or name in beneficiary_names):
            flagged.append({"trustee": t.get("name") or t.get("person_ref"),
                            "why": "is the founder" if name == founder else "is a beneficiary"})

    has_independent = any(t.get("independent") for t in trustees)
    return {
        "applies": applies,
        "trustee_count": len(trustees),
        "has_independent": has_independent,
        "conflicted": flagged,
        "compliant": (not applies) or has_independent,
        "why_it_matters": spec["why_it_matters"].strip(),
        "required_by": spec["required_by"],
        "rule": rule,
    }


# ── compliance calendar ──────────────────────────────────────────────────────


def compliance_calendar(trust: dict, horizon_days: int = 365) -> list[dict]:
    rule = _load("trust-compliance")
    today = date.fromisoformat(clock.today())
    ye = str(trust.get("year_end") or "02-28")
    ym, yd = (int(x) for x in ye.split("-"))

    def next_on(month: int, day: int, leap: bool = False) -> date:
        for year in (today.year, today.year + 1):
            d = 29 if (leap and month == 2 and calendar.isleap(year)) else day
            d = min(d, calendar.monthrange(year, month)[1])
            cand = date(year, month, d)
            if cand >= today:
                return cand
        raise AssertionError("unreachable")

    def last_year_end() -> date:
        """The most recent year end that has PASSED.

        Statements and returns are due for the year that has ended, not the one
        still running. Basing them on the next year end pushes every deadline a
        full year out and makes an already-overdue AFS look comfortably distant.
        """
        for year in (today.year, today.year - 1):
            d = 29 if (ym == 2 and calendar.isleap(year)) else yd
            d = min(d, calendar.monthrange(year, ym)[1])
            cand = date(year, ym, d)
            if cand <= today:
                return cand
        raise AssertionError("unreachable")

    out = []
    for ob in rule["obligations"]:
        if ob.get("months_after_year_end"):
            base = last_year_end()
            months = ob["months_after_year_end"]
            year = base.year + months // 12
            month = ((base.month - 1 + months % 12) % 12) + 1
            due = date(year, month, min(base.day, calendar.monthrange(year, month)[1]))
        else:
            due = next_on(ob["month"], ob["day"], ob.get("leap_aware", False))
        days = (due - today).days
        if days > horizon_days:
            continue
        # An overdue statutory obligation must never be hidden by a horizon.
        out.append({
            "kind": ob["kind"], "label": ob["label"], "due_on": due.isoformat(),
            "days_until": days, "lead_days": ob["lead_days"],
            "in_lead_window": days <= ob["lead_days"],
            "note": (ob.get("note") or "").strip(),
        })
    return sorted(out, key=lambda x: x["days_until"])


# ── distributions and the conduit principle ──────────────────────────────────


def distribution_review(trust: dict) -> dict:
    rule = _load("trust-compliance")
    dists = [d for d in ledger.read("distributions") if d.get("trust_ref") == trust.get("ref")]
    resolutions = [t for t in ledger.read("trustees")
                   if t.get("trust_ref") == trust.get("ref") and t.get("kind") == "resolution"]

    unauthorised = [d for d in dists if not d.get("resolution_ref")]
    by_year: dict[str, int] = {}
    for d in dists:
        by_year[d.get("tax_year", "?")] = by_year.get(d.get("tax_year", "?"), 0) + \
            (d.get("amount") or {}).get("cents", 0)

    return {
        "count": len(dists),
        "resolutions": len(resolutions),
        "unauthorised": [{"beneficiary": d.get("beneficiary_ref"),
                          "amount_cents": (d.get("amount") or {}).get("cents", 0),
                          "tax_year": d.get("tax_year"), "record_id": d["id"]}
                         for d in unauthorised],
        "by_tax_year": by_year,
        "conduit_note": rule["taxation"]["conduit_principle"].strip(),
        "attribution_note": rule["taxation"]["attribution_s7"].strip(),
        "flat_rate_pct": rule["taxation"]["flat_rate_pct"],
        "rule": rule,
    }


# ── separation of trust and personal affairs ─────────────────────────────────


def separation(trust: dict) -> dict:
    """Is the trust demonstrably distinct from the founder's own affairs?

    The relationship graph deliberately still links them — the point is not to
    hide the connection, it is to show that the trust is administered as a
    separate person.
    """
    entity_ref = trust.get("entity_ref") or trust.get("ref")
    findings = []

    trust_accounts = [a for a in ledger.read("accounts")
                      if a.get("entity_id") == entity_ref or a.get("owner_ref") == entity_ref]
    if not trust_accounts:
        findings.append({
            "kind": "no_trust_bank_account", "severity": "high",
            "detail": (
                "No bank account is recorded in the trust's name. Trust income "
                "and expenses running through a personal account is the clearest "
                "single indicator of an alter-ego trust, and the easiest to fix."
            ),
        })

    trust_assets = [a for a in ledger.read("assets") if a.get("owner_entity") == entity_ref]
    if not trust_assets:
        findings.append({
            "kind": "no_trust_assets", "severity": "medium",
            "detail": (
                "No assets are recorded as held by the trust. If the trust does "
                "hold assets, they are not on file — and an asset register is "
                "the first thing the Master or a creditor will ask for."
            ),
        })

    return {"entity_ref": entity_ref, "accounts": len(trust_accounts),
            "assets": len(trust_assets), "findings": findings}


# ── report ───────────────────────────────────────────────────────────────────


def report() -> dict:
    if not vault.is_initialised():
        return {"schema": "trusts/1", "error": "no vault — run /lifeos-init"}

    trusts = list(ledger.read("trusts"))
    if not trusts:
        return {"schema": "trusts/1", "at": clock.stamp(), "trusts": [],
                "note": "No trusts recorded. File the trust deed and letters of "
                        "authority in $VAULT/inbox/ and run /heartbeat."}

    s7c = s7c_exposure()
    used_rules: list = []
    out_trusts = []
    for t in trusts:
        ind = independence(t)
        dist = distribution_review(t)
        used_rules += [ind["rule"], dist["rule"]]
        out_trusts.append({
            "ref": t.get("ref"), "name": t.get("name"), "type": t.get("type"),
            "mt_number": t.get("mt_number"), "year_end": t.get("year_end"),
            "beneficiaries": t.get("beneficiaries") or [],
            "independence": {k: v for k, v in ind.items() if k != "rule"},
            "compliance": compliance_calendar(t),
            "distributions": {k: v for k, v in dist.items() if k != "rule"},
            "separation": separation(t),
            "s7c": [{k: v for k, v in e.items() if k != "rule"}
                    for e in s7c if e["trust_ref"] == t.get("ref")],
            "record_id": t["id"],
        })
    used_rules += [e["rule"] for e in s7c]

    comps = [rules.Computation(
        sum(e["deemed_donation_cents"] for e in s7c),
        "s7C deemed donation", rules_used=used_rules)]

    return {
        "schema": "trusts/1",
        "at": clock.stamp(),
        "tax_year": calendar_za.tax_year_of(date.fromisoformat(clock.today())),
        "trusts": out_trusts,
        "total_s7c_deemed_cents": sum(e["deemed_donation_cents"] for e in s7c),
        "total_s7c_tax_cents": sum(e["donations_tax_cents"] for e in s7c),
        "caveat": rules.caveat(comps),
    }


def to_markdown(rep: dict) -> str:
    if rep.get("error"):
        return f"**{rep['error']}**"
    if not rep["trusts"]:
        return f"# Trusts\n\n{rep['note']}"

    lines = [f"# Trust administration — {rep['tax_year']} year of assessment", ""]
    if rep.get("caveat"):
        lines += [f"> {rep['caveat']}", ""]

    for t in rep["trusts"]:
        lines += [f"## {t['name']}", "",
                  f"{t['type'].replace('_', ' ')} · Master's ref {t['mt_number'] or '—'} · "
                  f"year end {t['year_end'] or '—'}", ""]

        # s7C first: it is a cash cost the founder pays personally, every year.
        if t["s7c"]:
            lines += ["### Section 7C exposure", ""]
            for e in t["s7c"]:
                lines += [
                    f"Loan of **{money.fmt(e['balance_cents'])}** at "
                    f"{e['actual_rate_pct']}% against an official rate of "
                    f"{e['official_rate_pct']}%.",
                    "",
                    f"- Deemed donation: **{money.fmt(e['deemed_donation_cents'])}** a year",
                    f"- Less annual exemption: {money.fmt(e['exemption_applied_cents'])}",
                    f"- **Donations tax: {money.fmt(e['donations_tax_cents'])} a year**",
                    "",
                    "This is payable **by the lender, not the trust**, in cash, and it "
                    "repeats every year the loan stays interest-free. The exemption is "
                    "shared across all donations that person makes in the year, so if "
                    "they have donated elsewhere, less of it is available here.",
                    "",
                ]

        ind = t["independence"]
        lines += ["### Independent trustee", ""]
        if not ind["applies"]:
            lines.append("Not required for this trust type.")
        elif ind["compliant"]:
            lines.append(f"Present. {ind['trustee_count']} trustee(s) in office.")
        else:
            lines += [
                f"**None appointed.** {ind['trustee_count']} trustee(s) in office"
                + (", and " + "; ".join(f"{c['trustee']} {c['why']}" for c in ind["conflicted"])
                   if ind["conflicted"] else "") + ".",
                "",
                ind["why_it_matters"],
                "",
                f"_Required by: {ind['required_by']}_",
            ]
        lines.append("")

        d = t["distributions"]
        lines += ["### Distributions", ""]
        if d["count"] == 0:
            lines.append("None recorded.")
        else:
            for year, total in sorted(d["by_tax_year"].items()):
                lines.append(f"- {year}: {money.fmt(total)}")
            if d["unauthorised"]:
                lines += ["", f"**{len(d['unauthorised'])} distribution(s) have no "
                              "resolution recorded.**", "", d["conduit_note"], ""]
        lines.append("")

        sep = t["separation"]
        if sep["findings"]:
            lines += ["### Separation from personal affairs", ""]
            for f in sep["findings"]:
                lines.append(f"- {f['detail']}")
            lines.append("")

        cal = [c for c in t["compliance"] if c["in_lead_window"]]
        lines += ["### Compliance", ""]
        if cal:
            for c in cal:
                lines.append(f"- **{c['label']}** — due {c['due_on']} "
                             f"({c['days_until']} days)")
        else:
            lines.append("Nothing inside its lead window.")
        lines += ["", "| Obligation | Due | Days |", "|---|---|---|"]
        for c in t["compliance"]:
            lines.append(f"| {c['label']} | {c['due_on']} | {c['days_until']} |")
        lines.append("")

    lines += ["---",
              "_Trust administration carries personal liability for trustees. This is "
              "preparation for a conversation with the trust's accountant, an attorney "
              "and — for anything touching the letters of authority — the Master's "
              "Office. It is not advice._"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lifeos.trusts")
    ap.add_argument("--markdown", action="store_true")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)
    rep = report()
    text = to_markdown(rep)
    if args.write and not rep.get("error"):
        atomic.write_text(vault.path("reports", f"trusts-{clock.today()}.md"), text)
    print(text if args.markdown else json.dumps(rep, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
