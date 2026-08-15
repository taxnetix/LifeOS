"""Cover extraction, the consolidated cover map, investments and net worth.

The cover map is the second flagship: its findings are the ones no single
document contains, so these tests assert on exactly those.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parents[3] / "vault.example" / "inbox"


@pytest.fixture
def cover_vault(vault_dir, frozen_clock):
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
        "entities:\n  - {ref: ent_co, name: Northwind Software, form: pty_ltd}\n"
        "domains: {finance: true, living: true, insurance: true, investments: true,\n"
        "  readiness: true}\n"
    )

    from lifeos import analyse, classify, cover, covermap, finance, ingest, investments, ledger, readiness
    for m in (readiness, classify, ledger, ingest, cover, covermap, investments,
              finance, analyse):
        importlib.reload(m)
    readiness.load_profile.cache_clear()
    classify.load_rules.cache_clear()
    cover.load_rules.cache_clear()
    ingest.sweep()
    return vault_dir, cover, covermap, investments, finance, analyse, ledger


# ── classification ───────────────────────────────────────────────────────────


def test_gap_cover_is_not_classified_as_a_medical_scheme(cover_vault):
    """Filing gap cover as a scheme would double-count hospital cover and hide
    that day-to-day care is uncovered by both."""
    _, _, _, _, _, _, ledger = cover_vault
    from lifeos import atomic, vault
    types = {d["type"] for d in atomic.read_jsonl(vault.path("documents", "index.jsonl"))}
    assert "gap_cover_policy" in types
    assert "medical_aid_certificate" in types


# ── extraction ───────────────────────────────────────────────────────────────


def test_scheme_fields_come_from_the_labelled_row_not_the_title(cover_vault):
    """A loose /medical scheme/ matches the letterhead and captures the next
    word, 'Membership', as the scheme name."""
    _, cover, _, _, _, _, ledger = cover_vault
    cover.build()
    scheme = next(m for m in ledger.read("medical-aid") if m["kind"] == "scheme")
    assert scheme["provider"] == "Meridian Health Medical Scheme"
    assert scheme["option"] == "Classic Comprehensive"
    assert scheme["premium"]["cents"] == 775284


def test_insurer_falls_back_to_letterhead_when_unlabelled(cover_vault):
    _, cover, _, _, _, _, ledger = cover_vault
    cover.build()
    life = next(p for p in ledger.read("policies") if p["class"] == "life")
    assert life["insurer"] == "SOUTHERN MUTUAL ASSURANCE"
    assert life["insurer"] != "unknown"


def test_income_protection_is_a_monthly_benefit_not_a_sum_assured(cover_vault):
    """R55 000/month in sum_assured would read as R55 000 of total cover."""
    _, cover, _, _, _, _, ledger = cover_vault
    cover.build()
    ip = next(p for p in ledger.read("policies") if p["class"] == "income_protection")
    assert ip["monthly_benefit"]["cents"] == 5500000
    assert "sum_assured" not in ip


def test_cession_is_recorded(cover_vault):
    _, cover, _, _, _, _, ledger = cover_vault
    cover.build()
    life = next(p for p in ledger.read("policies") if p["class"] == "life")
    assert "Northbank" in life["cession"]["to"]


def test_gap_cover_exclusions_are_recorded(cover_vault):
    """What gap cover does NOT do is the most useful line in the document."""
    _, cover, _, _, _, _, ledger = cover_vault
    cover.build()
    gap = next(m for m in ledger.read("medical-aid") if m["kind"] == "gap")
    excludes = " ".join(p["name"] for p in gap.get("providers", []) if p["kind"] == "excludes")
    assert "day_to_day" in excludes and "chronic" in excludes


def test_benefit_statement_yields_one_record_per_benefit(cover_vault):
    _, cover, _, _, _, _, ledger = cover_vault
    cover.build()
    kinds = {b["kind"] for b in ledger.read("employee-benefits")}
    assert {"provident", "group_life", "disability", "income_protection", "funeral"} <= kinds


def test_missing_fields_become_gaps_not_defaults(cover_vault, vault_dir):
    """An unstated waiting period is unknown, not zero."""
    from lifeos import atomic
    _, cover, _, _, _, _, ledger = cover_vault
    cover.build()
    gaps = list(atomic.read_jsonl(vault_dir / "state" / "gaps.jsonl"))
    assert any(g["kind"] == "field.missing" for g in gaps)
    for p in ledger.read("policies"):
        assert p.get("waiting_periods") != [{"kind": "general", "months": 0}]


def test_reextraction_is_idempotent(cover_vault):
    _, cover, _, _, _, _, _ = cover_vault
    cover.build()
    again = cover.build()
    assert all(r["written"] == 0 for r in again["ledgers"].values())


# ── the cover map ────────────────────────────────────────────────────────────


def test_map_covers_every_named_event(cover_vault):
    _, cover, covermap, _, _, _, _ = cover_vault
    cover.build()
    rep = covermap.report()
    assert {r["event"] for r in rep["rows"]} == {k for k, _ in covermap.EVENTS}


def test_income_protection_stacking_is_detected(cover_vault):
    """Employer + personal cover above the aggregate ceiling is premium buying
    nothing — and it is invisible from inside either document."""
    _, cover, covermap, _, _, _, _ = cover_vault
    cover.build()
    dup = [f for f in covermap.report()["findings"] if f["kind"] == "cover_duplication"]
    assert dup, "the stacking finding is the point of the cover map"
    f = dup[0]
    assert f["annual_cost_cents"] > 0
    # It must not read as advice to cancel.
    assert "ENDS WITH EMPLOYMENT" in f["detail"]
    assert "not a statute" in f["detail"]
    assert len(f["evidence"]) >= 2


def test_employer_only_cover_is_flagged_as_not_portable(cover_vault):
    _, cover, covermap, _, _, _, _ = cover_vault
    cover.build()
    port = [f for f in covermap.report()["findings"] if f["kind"] == "cover_portability"]
    assert port
    assert "disability" in port[0]["title"]


def test_ceded_cover_is_flagged_as_unavailable_to_the_family(cover_vault):
    _, cover, covermap, _, _, _, _ = cover_vault
    cover.build()
    ces = [f for f in covermap.report()["findings"] if f["kind"] == "cover_cession"]
    assert ces
    assert "will not reach the family" in ces[0]["title"]


def test_the_health_stack_hole_is_named(cover_vault):
    """Day-to-day falls between the scheme's savings and the gap policy's
    exclusion — visible only when both are read together."""
    _, cover, covermap, _, _, _, _ = cover_vault
    cover.build()
    rep = covermap.report()
    d2d = next(r for r in rep["rows"] if r["event"] == "day_to_day")
    assert d2d["status"] == "partial"
    assert "EXCLUDES" in d2d["note"]


def test_uncovered_events_are_named_not_omitted(cover_vault):
    _, cover, covermap, _, _, _, _ = cover_vault
    cover.build()
    rep = covermap.report()
    assert rep["counts"]["uncovered"] >= 1
    gaps = [f for f in rep["findings"] if f["kind"] == "cover_gap"]
    assert any("Dread disease" in f["title"] for f in gaps)


def test_map_carries_an_as_at_date_for_its_conventions(cover_vault):
    _, cover, covermap, _, _, _, _ = cover_vault
    cover.build()
    rep = covermap.report()
    assert rep["assumptions_as_at"]
    assert rep["assumptions_as_at"] in covermap.to_markdown(rep)


def test_map_disclaims_advice(cover_vault):
    _, cover, covermap, _, _, _, _ = cover_vault
    cover.build()
    md = covermap.to_markdown(covermap.report())
    assert "not advice" in md


# ── investments ──────────────────────────────────────────────────────────────


def test_holdings_are_extracted_from_the_platform_statement(cover_vault):
    _, cover, _, investments, _, _, ledger = cover_vault
    cover.build()
    investments.build()
    mandates = {h.get("mandate") for h in ledger.read("holdings")}
    assert {"Global Equity Feeder", "SA Bond Fund", "Tax Free Savings"} <= mandates


def test_employer_fund_is_pulled_into_holdings(cover_vault):
    """The provident fund and the unit trusts are the same person's retirement,
    and neither document says so."""
    _, cover, _, investments, _, _, ledger = cover_vault
    cover.build()
    investments.build()
    occ = [h for h in ledger.read("holdings") if h["kind"] == "occupational"]
    assert occ and occ[0]["value"]["cents"] == 184250000


def test_tfsa_is_recognised_by_mandate(cover_vault):
    _, cover, _, investments, _, _, ledger = cover_vault
    cover.build()
    investments.build()
    assert any(h["kind"] == "tfsa" for h in ledger.read("holdings"))


def test_fee_drag_grows_with_horizon_and_discloses_unpriced(cover_vault):
    _, cover, _, investments, _, _, _ = cover_vault
    cover.build()
    investments.build()
    fd = investments.fee_drag()
    assert fd["weighted_ter_pct"] > 0
    for h in fd["holdings"]:
        costs = [h["cost_by_horizon_cents"][y] for y in fd["horizons"]]
        assert costs == sorted(costs)
    assert fd["unpriced_holdings"] >= 1, "the employer fund has no TER"
    assert "real drag is higher" in investments.to_markdown(investments.report())


# ── net worth ────────────────────────────────────────────────────────────────


def test_an_account_is_one_record_across_many_statements(cover_vault):
    """Three monthly statements must not mint three accounts — anything summing
    balances would count the same money once per month of history."""
    _, _, _, _, finance, _, ledger = cover_vault
    finance.build()
    accounts = list(ledger.read("accounts"))
    refs = [a["ref"] for a in accounts]
    assert len(refs) == len(set(refs)), f"duplicate account records: {refs}"


def test_net_worth_counts_each_account_once(cover_vault):
    _, _, _, _, finance, analyse, _ = cover_vault
    finance.build()
    nw = analyse.net_worth()
    account_refs = [c["ref"] for c in nw["components"] if c["ledger"] == "accounts"]
    assert len(account_refs) == len(set(account_refs))


def test_net_worth_includes_holdings_once_they_exist(cover_vault):
    _, cover, _, investments, finance, analyse, _ = cover_vault
    cover.build()
    finance.build()
    before = analyse.net_worth()
    investments.build()
    after = analyse.net_worth()
    assert after["assets_cents"] > before["assets_cents"]
    assert "holdings" not in after["missing_ledgers"]
    assert any(c["ledger"] == "holdings" for c in after["components"])


def test_net_worth_names_every_ledger_it_is_missing(cover_vault):
    """A net worth that quietly omits the house is worse than none."""
    _, cover, _, investments, finance, analyse, _ = cover_vault
    cover.build()
    finance.build()
    investments.build()
    nw = analyse.net_worth()
    assert nw["partial"] is True
    assert "assets" in nw["missing_ledgers"] and "liabilities" in nw["missing_ledgers"]
    assert "property and movables" in nw["note"] and "debt" in nw["note"]


def test_every_net_worth_component_traces_to_a_record(cover_vault):
    _, cover, _, investments, finance, analyse, _ = cover_vault
    cover.build()
    finance.build()
    investments.build()
    for c in analyse.net_worth()["components"]:
        assert c["record_id"].startswith("sha256:")
        assert isinstance(c["amount"]["cents"], int)
