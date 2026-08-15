"""Money parsing — the single place a printed amount becomes a number.

Getting a separator convention backwards turns R1,234.56 into R1.23: plausible,
wrong, and invisible. These cases are the ones that actually appear on SA
statements.
"""

from __future__ import annotations

import pytest

from lifeos import money


@pytest.mark.parametrize(
    "text,cents",
    [
        # SA convention: space thousands, comma decimal
        ("1 234,56", 123456),
        ("12 345,67", 1234567),
        ("1 234 567,89", 123456789),
        ("R 1 234,56", 123456),
        ("R1 234,56", 123456),
        # International convention: comma thousands, point decimal
        ("1,234.56", 123456),
        ("12,345.67", 1234567),
        ("1,234,567.89", 123456789),
        # Neither
        ("1234.56", 123456),
        ("1234,56", 123456),
        ("199.00", 19900),
        ("0.01", 1),
        ("0,01", 1),
        # Dot thousands with comma decimal (continental, seen on some exports)
        ("1.234,56", 123456),
        ("1.234.567,89", 123456789),
        # No decimals at all
        ("1 234", 123400),
        ("500", 50000),
    ],
)
def test_separator_conventions(text, cents):
    assert money.parse(text) == cents


@pytest.mark.parametrize(
    "text,cents",
    [
        ("-1 234,56", -123456),
        ("(1 234,56)", -123456),      # accounting parentheses
        ("1 234,56-", -123456),        # trailing minus, mainframe exports
        ("1 234,56 Dr", -123456),      # debit marker
        ("1 234,56 Cr", 123456),       # credit marker stays positive
        ("+1 234,56", 123456),
        ("R-500.00", -50000),
    ],
)
def test_sign_conventions(text, cents):
    assert money.parse(text) == cents


@pytest.mark.parametrize("text", ["", "   ", None, "abc", "R", "-", "n/a", "—", "1.2.3.4x"])
def test_unreadable_returns_none_never_zero(text):
    """None means 'I could not read this'. Zero would be a silent, plausible,
    wrong number that reconciles nothing and nobody would question."""
    assert money.parse(text) is None


def test_non_breaking_and_thin_spaces_are_handled():
    """PDF extraction routinely yields these instead of a plain space."""
    assert money.parse("1 234,56") == 123456
    assert money.parse("1 234,56") == 123456
    assert money.parse("1 234,56") == 123456


def test_rounding_is_half_up_at_the_cent():
    assert money.parse("0.005") == 1
    assert money.parse("0.004") == 0


def test_money_object_is_never_a_float():
    m = money.money(123456)
    assert isinstance(m["cents"], int)
    assert m == {"cents": 123456, "currency": "ZAR"}
    assert money.money(None) is None


def test_fmt_matches_the_javascript_renderer():
    """Both formatters must agree, or the same figure reads differently in a
    report and on a dashboard."""
    assert money.fmt(42676000) == "R426 760.00"
    assert money.fmt(-30196146) == "-R301 961.46"
    assert money.fmt(0) == "R0.00"
    assert money.fmt(-1) == "-R0.01"
    assert money.fmt(199) == "R1.99"
    assert money.fmt(None) == "—"


def test_fmt_signed_shows_a_plus():
    assert money.fmt(199, sign=True) == "+R1.99"


def test_add_refuses_to_mix_currencies():
    """Cross-currency arithmetic needs an explicit dated rate. Silently adding
    dollars to rands is the failure that makes a net worth meaningless."""
    with pytest.raises(ValueError, match="dated rate"):
        money.add({"cents": 100, "currency": "ZAR"}, {"cents": 100, "currency": "USD"})


def test_add_ignores_none_and_sums_cents():
    assert money.add({"cents": 100, "currency": "ZAR"}, None,
                     {"cents": 250, "currency": "ZAR"}) == {"cents": 350, "currency": "ZAR"}
