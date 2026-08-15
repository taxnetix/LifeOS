"""Rulebook staleness, tax deadlines, estate modelling and nomination conflicts.

The through-line: nothing computes from a remembered rate, and no figure built
on an unverified rule may be presented without its caveat.
"""

from __future__ import annotations

import importlib
from datetime import date
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parents[3] / "vault.example" / "inbox"


@pytest.fixture
def estate_vault(vault_dir, frozen_clock):
    if not FIXTURES.is_dir():
        pytest.skip("fixtures not generated")
    import shutil
    for f in FIXTURES.iterdir():
        if f.is_file() and f.name != "README.md":
            shutil.copy2(f, vault_dir / "inbox" / f.name)

    (vault_dir / "profile" / "profile.yaml").write_text(
        "schema: profile/1\njurisdiction: za\ncurrency: ZAR\n"
        "people:\n"
        "  - {ref: per_a, name: A Sample, relation: self}\n"
        "  - {ref: per_m, name: M Sample, relation: spouse}\n"
        "entities:\n"
        "  - {ref: ent_trust, name: The Sample Family Trust, form: trust}\n"
        "  - {ref: ent_co, name: Northwind Software (Pty) Ltd, form: pty_ltd, year_end: '02-28'}\n"
        "domains: {finance: true, living: true, insurance: true, investments: true,\n"
        "  assets: true, tax: true, estate: true, readiness: true}\n"
    )

    from lifeos import (
        analyse,
        classify,
        cover,
        estate,
        finance,
        ingest,
        investments,
        ledger,
        readiness,
        rules,
        tax,
    )
    for m in (readiness, classify, rules, ledger, ingest, cover, investments,
              finance, analyse, tax, estate):
        importlib.reload(m)
    for fn in (readiness.load_profile, classify.load_rules, cover.load_rules, rules.load):
        fn.cache_clear()
    ingest.sweep()
    cover.build()
    finance.build()
    investments.build()
    return vault_dir, rules, tax, estate, ledger


# ── rulebooks ────────────────────────────────────────────────────────────────


def test_every_rulebook_declares_its_provenance(estate_vault):
    _, rules, *_ = estate_vault
    for r in rules.all_rules():
        assert r.as_at, f"{r.name} has no as_at"
        assert r.source, f"{r.name} has no source"
        assert isinstance(r.verified, bool)


def test_shipped_rulebooks_are_honestly_marked_unverified(estate_vault):
    """They were written from memory. Claiming otherwise is the failure this
    whole mechanism exists to prevent."""
    _, rules, *_ = estate_vault
    assert all(not r.verified for r in rules.all_rules())


def test_rulebooks_from_a_past_tax_year_are_stale(estate_vault):
    _, rules, *_ = estate_vault
    duty = rules.load("estate-duty")
    assert duty.tax_year < duty.current_tax_year
    assert duty.stale is True
    assert any("tax-year figures" in w for w in duty.status["why"])


def test_a_computation_carries_verification_forward(estate_vault):
    _, rules, tax, *_ = estate_vault
    c = tax.medical_credits()
    assert c.requires_verification is True
    assert c.stale is True
    assert c.rules_used


def test_the_caveat_names_the_rules_and_says_not_to_plan_on_them(estate_vault):
    _, rules, tax, *_ = estate_vault
    text = rules.caveat([tax.medical_credits(), tax.retirement_headroom()])
    assert "not been verified" in text
    assert "not as a calculation to plan around" in text


def test_a_missing_rulebook_raises_rather_than_defaulting(estate_vault):
    _, rules, *_ = estate_vault
    with pytest.raises(rules.RuleNotFound):
        rules.load("no-such-rule")


# ── tax ──────────────────────────────────────────────────────────────────────


def test_deadlines_are_sorted_and_dated(estate_vault):
    _, _, tax, *_ = estate_vault
    dl = tax.deadlines()
    assert dl
    assert [d["days_until"] for d in dl] == sorted(d["days_until"] for d in dl)
    for d in dl:
        date.fromisoformat(d["due_on"])


def test_irp6_period_1_is_inside_its_lead_window_in_august(estate_vault):
    _, _, tax, *_ = estate_vault
    urgent = tax.report()["in_lead_window"]
    assert any(d["kind"] == "irp6_1" for d in urgent)


def test_provisional_status_is_explained_not_assumed(estate_vault):
    """'That isn't mine' is the reply a bare obligation invites."""
    _, _, tax, *_ = estate_vault
    prov = [d for d in tax.deadlines() if d["kind"] == "irp6_1"]
    assert prov
    assert all(d["applies_because"] for d in prov)


def test_trust_and_company_get_their_own_obligations(estate_vault):
    _, _, tax, *_ = estate_vault
    kinds_by_taxpayer = {}
    for d in tax.deadlines():
        kinds_by_taxpayer.setdefault(d["taxpayer"], set()).add(d["kind"])
    assert any("it12tr" in v for v in kinds_by_taxpayer.values())


def test_retirement_headroom_says_over_contributing_is_not_waste(estate_vault):
    _, _, tax, *_ = estate_vault
    c = tax.retirement_headroom()
    assert c.value is not None
    assert any("roll forward" in n for n in c.notes)


def test_tfsa_admits_it_cannot_compute_remaining_room(estate_vault):
    """Value is not contribution history, and saying otherwise would be wrong."""
    _, _, tax, *_ = estate_vault
    c = tax.tfsa_position()
    assert any("cannot tell you how much room is left" in n for n in c.notes)


def test_tax_report_carries_the_caveat(estate_vault):
    _, _, tax, *_ = estate_vault
    md = tax.to_markdown(tax.report())
    assert "not been verified" in md
    assert "does not determine deductibility" in md or "not determine deductibility" in md


# ── estate ───────────────────────────────────────────────────────────────────


def test_retirement_interests_are_excluded_from_the_dutiable_estate(estate_vault):
    _, _, _, estate, _ = estate_vault
    calc = estate.report()["calculation"]
    assert calc["retirement_excluded_cents"] > 0


def test_life_policy_proceeds_are_deemed_property(estate_vault):
    """Deemed property applies even when a nomination bypasses the estate."""
    _, _, _, estate, _ = estate_vault
    assert estate.report()["calculation"]["deemed_property_cents"] > 0


def test_spousal_rollover_is_applied_and_flagged_as_deferral(estate_vault):
    _, _, _, estate, _ = estate_vault
    rep = estate.report()
    assert rep["calculation"]["spouse_inherits"] is True
    assert rep["calculation"]["s4q_deduction_cents"] > 0
    assert "defers duty, it does not remove it" in estate.to_markdown(rep)


def test_executor_fee_is_computed_with_vat(estate_vault):
    _, rules, _, estate, _ = estate_vault
    calc = estate.report()["calculation"]
    gross = calc["gross_estate_cents"]
    fee_rule = rules.load("estate-fees")
    bare = gross * fee_rule["executor"]["max_pct_of_gross_estate"] / 100
    assert calc["executor_fee_cents"] > bare


def test_a_ceded_policy_offsets_the_debt_it_secures(estate_vault):
    """Counting the bond as due while excluding the policy would overstate the
    shortfall by the entire bond."""
    _, _, _, estate, _ = estate_vault
    liq = estate.report()["liquidity"]
    assert liq["ceded_applied_to_debt"]
    applied = sum(c["applied_to_debt_cents"] for c in liq["ceded_applied_to_debt"])
    assert applied > 0
    assert liq["breakdown"]["debts_after_cession"] == 0


def test_liquidity_leads_with_timing_not_solvency(estate_vault):
    """An estate can be solvent and still leave a family unable to buy food."""
    _, _, _, estate, _ = estate_vault
    rep = estate.report()
    liq = rep["liquidity"]
    assert liq["shortfall_cents"] == 0, "this fixture estate is solvent"
    assert liq["timing_risk"] is True
    assert liq["immediate_30day_cents"] < liq["available_cents"]
    md = estate.to_markdown(rep)
    assert "in the first 30 days" in md
    assert "months of expenses" in md


def test_frozen_accounts_are_not_counted_as_reachable(estate_vault):
    _, _, _, estate, _ = estate_vault
    liq = estate.report()["liquidity"]
    bank = next(s for s in liq["sources"] if s["label"] == "Bank accounts")
    assert bank["available"] is False
    assert "frozen" in bank["why"]


def test_business_cash_is_not_part_of_the_personal_estate(estate_vault):
    """Company money belongs to the company, not to the deceased. Including it
    would inflate the estate and the executor's fee computed on it."""
    _, _, _, estate, ledger = estate_vault
    accounts = {a["ref"]: a for a in ledger.read("accounts")}
    business_refs = {r for r, a in accounts.items() if a.get("is_business")}
    assert business_refs, "the fixture has a business account"

    latest = {}
    for t in ledger.read("transactions"):
        if "balance_after" not in t:
            continue
        cur = latest.get(t["account_ref"])
        if cur is None or t["posted_on"] >= cur["posted_on"]:
            latest[t["account_ref"]] = t

    personal_only = sum(
        t["balance_after"]["cents"] for ref, t in latest.items() if ref not in business_refs
    )
    business_cash = sum(
        t["balance_after"]["cents"] for ref, t in latest.items() if ref in business_refs
    )
    assert business_cash > 0, "the fixture business account has a balance"
    assert estate.gather()["cash_cents"] == personal_only


# ── nominations versus the will ──────────────────────────────────────────────


def test_nomination_away_from_the_will_heir_is_detected(estate_vault):
    """The highest-value estate finding: neither document mentions the other."""
    _, _, _, estate, _ = estate_vault
    conflicts = estate.report()["conflicts"]
    diverted = [c for c in conflicts if c["kind"] == "beneficiary_vs_will"]
    assert diverted
    f = diverted[0]
    assert "OVERRIDES the will" in f["detail"]
    assert len(f["evidence"]) >= 2


def test_the_conflict_is_framed_as_a_decision_not_an_error(estate_vault):
    """Nominating a trust for minor children is common and sensible."""
    _, _, _, estate, _ = estate_vault
    f = next(c for c in estate.report()["conflicts"] if c["kind"] == "beneficiary_vs_will")
    assert "may well be deliberate" in f["detail"]


def test_ceded_and_nominated_policy_is_flagged(estate_vault):
    _, _, _, estate, _ = estate_vault
    conflicts = estate.report()["conflicts"]
    assert any(c["kind"] == "ceded_and_nominated" for c in conflicts)


def test_estate_report_disclaims_advice(estate_vault):
    _, _, _, estate, _ = estate_vault
    md = estate.to_markdown(estate.report())
    assert "Master's Office" in md
    assert "not a calculation to plan around" in md


# ── net worth completeness ───────────────────────────────────────────────────


def test_net_worth_is_no_longer_partial_once_every_ledger_has_records(estate_vault):
    from lifeos import analyse
    rep = analyse.net_worth()
    assert rep["missing_ledgers"] == []
    assert rep["partial"] is False
    assert rep["liabilities_cents"] > 0


def test_property_uses_a_dated_valuation_with_its_basis(estate_vault):
    """A municipal valuation is not a market value, and the basis must survive."""
    from lifeos import analyse
    prop = next(c for c in analyse.net_worth()["components"] if c["ledger"] == "assets")
    assert prop["basis"] == "municipal"
    assert prop["as_at"]
