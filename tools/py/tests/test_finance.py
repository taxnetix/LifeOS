"""Statement parsing, categorisation, commitment detection, cashflow, findings."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parents[3] / "vault.example" / "inbox"


@pytest.fixture
def money_vault(vault_dir, frozen_clock):
    """A temp vault loaded with the statement fixtures and a real profile."""
    if not FIXTURES.is_dir():
        pytest.skip("fixtures not generated")
    import shutil
    for f in FIXTURES.iterdir():
        if f.is_file() and f.name != "README.md":
            shutil.copy2(f, vault_dir / "inbox" / f.name)

    (vault_dir / "profile" / "profile.yaml").write_text(
        "schema: profile/1\njurisdiction: za\ncurrency: ZAR\n"
        "people:\n  - {ref: per_a, name: A Sample, relation: self}\n"
        "entities:\n"
        "  - {ref: ent_trust, name: The Sample Family Trust, form: trust}\n"
        "  - {ref: ent_co, name: Northwind Software, form: pty_ltd}\n"
        "domains: {finance: true, readiness: true}\n"
        "finance: {category_floor: 0.90, savings_rate_target_pct: 20}\n"
    )

    from lifeos import analyse, categorise, finance, ingest, ledger, optimise, parsers, readiness, recurring
    for m in (readiness, categorise, parsers, ledger, ingest, finance, recurring, analyse, optimise):
        importlib.reload(m)
    readiness.load_profile.cache_clear()
    ingest.sweep()
    return vault_dir, finance, recurring, analyse, optimise, ledger, parsers


# ── parsing ──────────────────────────────────────────────────────────────────


def test_bank_is_fingerprinted_from_content_not_filename(money_vault):
    from lifeos import extract, parsers
    ex = extract.extract(FIXTURES / "northbank-cheque-2026-07.pdf")
    st = parsers.parse(ex, filename="totally-misleading-name.pdf")
    assert st.bank == "northbank"


def test_statement_header_fields_are_extracted_precisely(money_vault):
    from lifeos import extract, parsers
    ex = extract.extract(FIXTURES / "northbank-cheque-2026-07.pdf")
    st = parsers.parse(ex, filename="northbank-cheque-2026-07.pdf")
    assert st.holder == "A SAMPLE", "a greedy pattern would swallow the next label"
    assert st.branch_code == "250655"
    assert st.account_no.replace(" ", "") == "10495560118"
    assert st.period == {"from": "2026-07-01", "to": "2026-07-31"}


def test_running_balance_reconciles_on_every_fixture(money_vault):
    """The cheapest possible proof the column order, signs and decimal
    convention are all correct."""
    from lifeos import extract, parsers
    for name in ("northbank-cheque-2026-05.pdf", "northbank-cheque-2026-06.pdf",
                 "northbank-cheque-2026-07.pdf", "meridian-business-2026-07.csv"):
        ex = extract.extract(FIXTURES / name)
        st = parsers.parse(ex, filename=name)
        assert st.rows, f"{name}: no rows"
        assert any("reconciles" in w for w in st.warnings), f"{name}: {st.warnings}"
        assert not st.errors, f"{name}: {st.errors}"


def test_signs_are_correct_income_positive_outflow_negative(money_vault):
    from lifeos import extract, parsers
    ex = extract.extract(FIXTURES / "northbank-cheque-2026-07.pdf")
    st = parsers.parse(ex, filename="northbank-cheque-2026-07.pdf")
    salary = next(r for r in st.rows if "SALARY" in r.description)
    bond = next(r for r in st.rows if "BOND" in r.description)
    assert salary.amount_cents > 0
    assert bond.amount_cents < 0


def test_opening_and_closing_balance_rows_are_not_transactions(money_vault):
    from lifeos import extract, parsers
    ex = extract.extract(FIXTURES / "northbank-cheque-2026-07.pdf")
    st = parsers.parse(ex, filename="northbank-cheque-2026-07.pdf")
    assert not any("BALANCE" in r.description.upper() for r in st.rows)


def test_description_digits_are_not_eaten_as_amounts(money_vault):
    """'OUTSURANCE 4471' — reading amounts from the left would consume the ref."""
    from lifeos import extract, parsers
    ex = extract.extract(FIXTURES / "northbank-cheque-2026-07.pdf")
    st = parsers.parse(ex, filename="northbank-cheque-2026-07.pdf")
    row = next(r for r in st.rows if "OUTSURANCE" in r.description)
    assert row.description.endswith("4471")
    assert row.amount_cents == -184200


def test_unknown_institution_produces_an_actionable_error(money_vault):
    from lifeos import parsers
    from lifeos.extract import Block, Extraction
    ex = Extraction(doc_hash="sha256:" + "0" * 64, method="text",
                    blocks=[Block("page=1;line=1", "Some bank nobody has heard of", 1.0)])
    st = parsers.parse(ex)
    assert st.bank == "unknown"
    assert "bank-formats.yaml" in st.errors[0]


def test_unverified_adapter_confidence_sits_below_the_write_floor(money_vault):
    """An unverified layout must not be able to put numbers in a ledger."""
    from lifeos import ledger, parsers
    fmts = parsers.load_formats()
    unverified = fmts["defaults"]["confidence_unverified"]
    assert unverified < ledger.confidence_floor("transactions")


# ── categorisation ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "desc,amount,category",
    [
        ("SALARY NORTHWIND SOFTWARE", 6842000, "income"),
        ("BOND REPAYMENT HOMELOAN 9921", -1875000, "housing"),
        ("DEBIT ORDER DISCOVERY HEALTH", -731400, "medical"),
        ("NETFLIX.COM", -19900, "subscriptions"),
        ("WOOLWORTHS SANDTON", -80000, "groceries"),
        ("ENGEN GARAGE", -100000, "transport"),
        ("SARS EFILING IRP6", -1240000, "tax"),
        ("SERVICE FEE", -12100, "fees"),
        ("ALLAN GRAY RA CONTRIB", -650000, "savings"),
        ("MTN PREPAID DATA", -59900, "utilities"),
    ],
)
def test_known_sa_merchants_are_categorised(money_vault, desc, amount, category):
    from lifeos import categorise
    c = categorise.categorise(desc, amount)
    assert c.category == category, f"{desc} -> {c.category}"
    assert c.confidence >= categorise.floor()


def test_unknown_merchant_is_left_uncategorised_not_guessed(money_vault):
    """Uncategorised is visible; miscategorised is not."""
    from lifeos import categorise
    assert not categorise.categorise("QWERTY ZXCVB 9931", -50000).ok


def test_direction_matters_for_ambiguous_words(money_vault):
    """'rent received' is income; it must not match on an outflow."""
    from lifeos import categorise
    assert categorise.categorise("RENT RECEIVED JHB PROPS", 950000).category == "income"
    assert categorise.categorise("RENT RECEIVED JHB PROPS", -950000).category != "income"


def test_human_history_outranks_a_generic_rule(money_vault):
    from lifeos import categorise
    history = [{
        "description_raw": "TAKEALOT.COM 4471",
        "category": "business", "subcategory": "equipment",
        "category_method": "human",
    }]
    c = categorise.categorise("TAKEALOT.COM 8892", -120000, history=history)
    assert c.category == "business" and c.method == "history"


def test_machine_history_does_not_feed_back_on_itself(money_vault):
    """Learning from its own output would let one early mistake compound."""
    from lifeos import categorise
    history = [{
        "description_raw": "MYSTERY MERCHANT",
        "category": "wrong", "category_method": "rule",
    }]
    assert categorise.by_history("MYSTERY MERCHANT", history).category is None


# ── ledgers ──────────────────────────────────────────────────────────────────


def test_build_writes_accounts_and_transactions(money_vault):
    _, finance, *_ = money_vault
    r = finance.build()
    assert r["ledgers"]["transactions"]["written"] > 50
    assert r["ledgers"]["accounts"]["written"] >= 2


def test_rebuilding_writes_nothing_the_second_time(money_vault):
    _, finance, *_ = money_vault
    finance.build()
    again = finance.build()
    assert again["ledgers"]["transactions"]["written"] == 0
    assert again["ledgers"]["transactions"]["unchanged"] > 50


def test_business_statement_attaches_to_the_operating_company(money_vault):
    """Not the trust — a trust rarely runs the trading account, and attaching
    turnover to one would misstate both entities."""
    _, finance, _, _, _, ledger, _ = money_vault
    finance.build()
    biz = [t for t in ledger.read("transactions") if t.get("entity_id")]
    assert biz
    assert {t["entity_id"] for t in biz} == {"ent_co"}


def test_low_confidence_rows_are_parked_not_written(money_vault, vault_dir):
    _, finance, *_ = money_vault
    r = finance.build()
    assert r["ledgers"]["transactions"]["low_confidence"] > 0
    assert list((vault_dir / "proposed" / "low-confidence").glob("transactions-*.jsonl"))


def test_every_transaction_traces_to_a_document_and_locator(money_vault):
    _, finance, _, _, _, ledger, _ = money_vault
    finance.build()
    for t in ledger.read("transactions"):
        assert t["source"]["doc_hash"].startswith("sha256:")
        assert "=" in t["source"]["locator"]
        assert isinstance(t["amount"]["cents"], int)


# ── commitments ──────────────────────────────────────────────────────────────


def test_real_commitments_are_detected(money_vault):
    _, finance, recurring, *_ = money_vault
    finance.build()
    found = recurring.build()["found"]
    names = " ".join(f["counterparty"] for f in found).upper()
    for expected in ("BOND REPAYMENT", "NETFLIX", "DISCOVERY HEALTH", "SPOTIFY"):
        assert expected in names, f"missed {expected}"


def test_variable_spend_at_a_regular_merchant_is_not_a_commitment(money_vault):
    """A weekly grocery run is periodic and differently-priced every time."""
    _, finance, recurring, *_ = money_vault
    finance.build()
    names = " ".join(f["counterparty"] for f in recurring.build()["found"]).upper()
    for shop in ("WOOLWORTHS", "CHECKERS", "UBER", "TAKEALOT", "ENGEN"):
        assert shop not in names, f"{shop} is variable spend, not a commitment"


def test_escalation_is_detected(money_vault):
    _, finance, recurring, *_ = money_vault
    finance.build()
    esc = [f for f in recurring.build()["found"] if f["escalation"]]
    assert esc
    assert any(5 <= f["escalation"]["pct"] <= 7 for f in esc)


def test_cancellation_route_is_never_invented(money_vault):
    """A recurring cost nobody can work out how to stop is the finding."""
    _, finance, recurring, _, _, ledger, _ = money_vault
    finance.build()
    recurring.build()
    rows = list(ledger.read("recurring-payments"))
    assert rows
    assert all(r["cancellation_route"].startswith("UNKNOWN") for r in rows)


def test_detected_commitments_are_marked_inferred(money_vault):
    _, finance, recurring, _, _, ledger, _ = money_vault
    finance.build()
    recurring.build()
    assert all(r["source"]["method"] == "inferred" for r in ledger.read("recurring-payments"))


# ── analysis ─────────────────────────────────────────────────────────────────


def test_cashflow_separates_personal_from_business(money_vault):
    _, finance, _, analyse, *_ = money_vault
    finance.build()
    flow = analyse.cashflow()
    july = next(s for s in flow["series"] if s["month"] == "2026-07")
    assert july["business_net_cents"] != 0
    assert july["personal_net_cents"] != 0
    assert july["net_cents"] == july["personal_net_cents"] + july["business_net_cents"]


def test_savings_rate_uses_personal_flows_only(money_vault):
    """Business turnover would swamp it and make the number meaningless."""
    _, finance, _, analyse, *_ = money_vault
    finance.build()
    t = analyse.cashflow()["totals"]
    assert t["personal_in_cents"] < t["in_cents"]
    expected = round(100 * (t["personal_in_cents"] + t["personal_out_cents"]) / t["personal_in_cents"], 1)
    assert t["savings_rate_pct"] == expected


def test_transfers_are_excluded_from_both_sides(money_vault):
    _, _, _, analyse, *_ = money_vault
    assert "transfer" in analyse._EXCLUDED


def test_every_monthly_figure_names_its_records(money_vault):
    _, finance, _, analyse, *_ = money_vault
    finance.build()
    for s in analyse.cashflow()["series"]:
        assert len(s["record_ids"]) == s["transactions"]


def test_net_worth_is_labelled_partial_while_ledgers_are_empty(money_vault):
    """A net worth that quietly omits the house is worse than none."""
    _, finance, _, analyse, *_ = money_vault
    finance.build()
    nw = analyse.net_worth()
    assert nw["partial"] is True
    assert {"assets", "liabilities", "holdings"} <= set(nw["missing_ledgers"])
    # The caveat must NAME what is excluded in plain words, not merely say
    # "partial" — a reader who skips the flag must still see the omission.
    for phrase in ("property and movables", "debt", "investments"):
        assert phrase in nw["note"], nw["note"]


# ── findings ─────────────────────────────────────────────────────────────────


def test_cross_account_duplicate_is_found(money_vault):
    """Netflix billed personally AND through the business — invisible on either
    statement alone. This is the finding that justifies one consolidated ledger."""
    _, finance, recurring, _, optimise, *_ = money_vault
    finance.build()
    recurring.build()
    dups = [f for f in optimise.report()["findings"] if f["kind"] == "duplicate_subscription"]
    assert dups
    assert "NETFLIX" in dups[0]["title"].upper()


def test_escalation_finding_quantifies_five_year_cost(money_vault):
    _, finance, recurring, _, optimise, *_ = money_vault
    finance.build()
    recurring.build()
    esc = [f for f in optimise.report()["findings"] if f["kind"] == "escalation_creep"]
    assert esc
    assert esc[0]["annual_saving_cents"] > 0
    assert "five years" in esc[0]["detail"]


def test_tax_findings_never_claim_deductibility(money_vault):
    _, finance, _, _, optimise, *_ = money_vault
    finance.build()
    tax = [f for f in optimise.report()["findings"] if f["kind"] == "tax_review"]
    assert tax
    for f in tax:
        assert f["confidence"] == "review_required"
        assert f["annual_saving_cents"] == 0
        assert "practitioner" in f["detail"]


def test_every_finding_carries_evidence_or_is_a_summary(money_vault):
    _, finance, recurring, _, optimise, *_ = money_vault
    finance.build()
    recurring.build()
    for f in optimise.report()["findings"]:
        if f.get("annual_saving_cents", 0) > 0:
            assert f["evidence"], f"{f['kind']} claims a saving with no records behind it"


def test_findings_are_ranked_by_value_per_effort(money_vault):
    _, finance, recurring, _, optimise, *_ = money_vault
    finance.build()
    recurring.build()
    vals = [f["value_per_effort"] for f in optimise.report()["findings"]]
    assert vals == sorted(vals, reverse=True)
