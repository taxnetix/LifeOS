"""Money parsing — text on a statement to integer minor units.

Money is NEVER a float in LifeOS (ADR-0005). This module is the single place
where a printed amount becomes a number, and it refuses rather than guesses:
`parse` returns None for anything it cannot read exactly, and the caller turns
that into a gap record.

South African statements are inconsistent in ways that matter:

    1 234,56      space thousands, comma decimal   (SARS, most banks)
    1,234.56      comma thousands, point decimal   (card exports, platforms)
    1234.56       neither
    R 1 234,56    currency prefix
    (1 234,56)    parentheses mean negative        (accounting convention)
    1 234,56-     trailing minus                   (some mainframe exports)
    1 234,56 Cr   credit marker

Getting the separator convention backwards turns R1,234.56 into R1.23, which is
plausible, wrong, and invisible. So the convention is DECIDED, never assumed —
see `_decide_separators`.
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

# Strip currency marks, whitespace variants and credit/debit suffixes.
#
# Order matters and the case-sensitivity is deliberate: a case-insensitive
# [R$€£] matches the 'r' inside "Cr", turning a credit marker into "C" and
# losing the sign. Cr/Dr are therefore stripped FIRST, and the currency class
# is anchored so it can only take a leading symbol or a standalone code.
_CR = re.compile(r"\s*\b(cr|credit)\b\.?$", re.I)
_DR = re.compile(r"\s*\b(dr|debit)\b\.?$", re.I)
_CURRENCY = re.compile(r"^\s*(?:[R$€£]|(?:ZAR|USD|EUR|GBP)\b)\s*|\s*\b(?:ZAR|USD|EUR|GBP)\s*$", re.I)
_NBSP = "   "

_VALID = re.compile(r"^-?\d+(?:[.,]\d+)?$")


def _decide_separators(s: str) -> str:
    """Normalise thousands/decimal separators to a bare '123456.78'.

    The rule: whichever separator appears LAST and is followed by exactly 2 (or
    1) digits is the decimal separator; every other separator is thousands.
    That works for both SA conventions without having to know which bank wrote
    the file — and it is why this is decided rather than assumed.
    """
    last_comma, last_dot = s.rfind(","), s.rfind(".")

    if last_comma == -1 and last_dot == -1:
        return s

    if last_comma > last_dot:
        dec_pos, dec_char, other = last_comma, ",", "."
    else:
        dec_pos, dec_char, other = last_dot, ".", ","

    tail = s[dec_pos + 1:]
    if not tail.isdigit():
        return s

    if len(tail) <= 2:
        return s[:dec_pos].replace(other, "").replace(dec_char, "") + "." + tail

    if len(tail) == 3:
        # Ambiguous: "1.234" is continental thousands, but "0.005" cannot be —
        # nothing has a thousands group after a bare zero. Reading it as
        # thousands would turn five-tenths of a cent into five rands, a
        # thousandfold error that reconciles against nothing.
        head = s[:dec_pos].replace(other, "").replace(dec_char, "")
        if head.lstrip("-+") == "0":
            return head + "." + tail
        return s.replace(",", "").replace(".", "")

    # More than three decimals is not a money format. Refuse rather than guess.
    return ""


def parse(text: str | None) -> int | None:
    """Parse an amount to integer cents. Returns None if it cannot be read.

    None is a real answer: the caller writes a gap record rather than a zero.
    A zero here would be a silent, plausible, wrong number.
    """
    if text is None:
        return None
    s = str(text).strip()
    if not s:
        return None

    for ch in _NBSP:
        s = s.replace(ch, " ")
    s = _CURRENCY.sub("", s).strip()

    negative = False
    if _CR.search(s):
        s = _CR.sub("", s).strip()
    elif _DR.search(s):
        s = _DR.sub("", s).strip()
        negative = True

    if s.startswith("(") and s.endswith(")"):
        negative = True
        s = s[1:-1].strip()

    if s.endswith("-"):
        negative = True
        s = s[:-1].strip()
    elif s.startswith("-"):
        negative = True
        s = s[1:].strip()
    elif s.startswith("+"):
        s = s[1:].strip()

    s = s.replace(" ", "")
    if not s:
        return None

    s = _decide_separators(s)
    if not _VALID.match(s):
        return None

    try:
        cents = int(
            (Decimal(s) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
    except (InvalidOperation, ValueError):
        return None

    return -cents if negative else cents


def money(cents: int | None, currency: str = "ZAR") -> dict | None:
    """Build the ledger money object. Never a float."""
    return None if cents is None else {"cents": int(cents), "currency": currency}


def fmt(cents: int | None, currency: str = "ZAR", *, sign: bool = False) -> str:
    """Render for humans. Presentation lives here, never in a ledger."""
    if cents is None:
        return "—"
    symbol = {"ZAR": "R", "USD": "$", "EUR": "€", "GBP": "£"}.get(currency, currency + " ")
    body = f"{abs(cents) / 100:,.2f}".replace(",", " ")
    if cents < 0:
        return f"-{symbol}{body}"
    return f"+{symbol}{body}" if sign else f"{symbol}{body}"


def add(*amounts: dict | None, currency: str = "ZAR") -> dict:
    """Sum money objects of one currency.

    Raises on a currency mix rather than silently adding dollars to rands —
    cross-currency arithmetic requires an explicit dated rate (ADR-0005).
    """
    total = 0
    for a in amounts:
        if not a:
            continue
        if a["currency"] != currency:
            raise ValueError(
                f"cannot add {a['currency']} to {currency} without an explicit dated rate"
            )
        total += a["cents"]
    return {"cents": total, "currency": currency}
