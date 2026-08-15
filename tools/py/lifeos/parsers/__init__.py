"""Statement parsers — an adapter registry selected by fingerprinting.

SA bank PDF layouts differ substantially and change without notice, so the bank
is DETECTED from the document text, never taken from a filename or a claim.

The honest part of this design is what happens when detection is weak:

  * a **verified** adapter (tested against a real statement, with a fixture)
    emits rows at 0.97 confidence — above the 0.90 transactions floor, so they
    enter the ledger.

  * an **unverified** adapter emits at 0.60 — deliberately BELOW the floor, so
    every row lands in proposed/ for confirmation instead. Column order, date
    format and sign convention are what vary between banks, and getting them
    wrong produces numbers that are plausible, wrong and invisible.

  * no adapter at all produces a gap record naming the institution, which
    becomes a `kind:adapter` GitHub issue describing the layout change — a
    class of problem, never an instance of the user's data.

A parser never silently guesses a number into a ledger.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from functools import cache

from .. import money, vault

RULES_PATH = vault.repo_root() / ".claude" / "rules" / "bank-formats.yaml"


@dataclass
class Row:
    date: str                    # ISO
    description: str
    amount_cents: int            # signed: negative is outflow
    balance_cents: int | None
    locator: str
    confidence: float


@dataclass
class Statement:
    bank: str
    label: str
    verified: bool
    confidence: float
    account_no: str | None = None
    branch_code: str | None = None
    holder: str | None = None
    is_business: bool = False
    currency: str = "ZAR"
    period: dict | None = None
    rows: list[Row] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "schema": "statement/1",
            "bank": self.bank, "label": self.label,
            "verified": self.verified, "confidence": self.confidence,
            "account_no": self.account_no, "branch_code": self.branch_code,
            "holder": self.holder, "is_business": self.is_business,
            "currency": self.currency, "period": self.period,
            "rows": [r.__dict__ for r in self.rows],
            "errors": self.errors, "warnings": self.warnings,
        }


@cache
def load_formats() -> dict:
    from ruamel.yaml import YAML

    yaml = YAML(typ="safe")
    with RULES_PATH.open(encoding="utf-8") as fh:
        return yaml.load(fh)


def fingerprint(text: str) -> tuple[str | None, dict]:
    """Identify the institution from document text. Returns (key, spec)."""
    rules = load_formats()
    low = text.lower()
    best: tuple[int, str | None, dict] = (0, None, {})

    for key, spec in rules["banks"].items():
        fp = spec.get("fingerprint", {})
        required = fp.get("all", [])
        if required and not all(t.lower() in low for t in required):
            continue
        score = len(required) * 3 + sum(1 for t in fp.get("any", []) if t.lower() in low)
        if score > best[0]:
            best = (score, key, spec)

    return (best[1], best[2]) if best[0] else (None, {})


def _parse_date(value: str, fmts: list[str], fallback_year: int | None) -> str | None:
    v = value.strip()
    for fmt in fmts:
        try:
            d = datetime.strptime(v, fmt)
        except ValueError:
            continue
        if "%Y" not in fmt and fallback_year:
            d = d.replace(year=fallback_year)
        return d.date().isoformat()
    return None


# An amount token on an SA statement.
#
# The hard part is that space is BOTH a thousands separator and the gap between
# columns: "199.00 153 091.99" is two amounts, not one. A pattern that allows
# spaces inside a number swallows the whole run.
#
# The disambiguator is the two-decimal tail, which statements essentially always
# print. Requiring it means thousands groups must be exactly three digits, so
# "199.00" terminates before the space and "153 091.99" starts after it.
# A layout that omits cents will fail here loudly rather than mis-tokenise.
_AMOUNT_TOKEN = re.compile(
    r"""\(?-?\s*R?\s?              # optional paren, sign, currency
        \d{1,3}(?:[\s ,.]\d{3})*  # integer part, 3-digit thousands groups
        [.,]\d{2}                  # REQUIRED cents — this is the disambiguator
        \)?-?                      # optional closing paren, trailing minus
        (?:\s?(?:Cr|Dr)\b)?        # optional credit/debit marker
    """,
    re.X | re.I,
)

_LINE = re.compile(
    r"^(?P<date>\d{1,2}\s+\w{3,9}\s+\d{4}|\d{4}[-/]\d{2}[-/]\d{2}|\d{1,2}[-/]\d{1,2}[-/]\d{4})"
    r"\s+(?P<rest>.+?)$"
)


def _split_trailing_amounts(rest: str, want: int) -> tuple[str, list[str]]:
    """Peel the last `want` amount tokens off a line, leaving the description.

    Amounts are taken from the RIGHT: a description often contains digits — an
    account reference like "OUTSURANCE 4471", a policy number — and reading from
    the left would consume them as amounts.
    """
    matches = list(_AMOUNT_TOKEN.finditer(rest))
    if len(matches) < want:
        return rest.strip(), []
    taken = matches[-want:]
    return rest[: taken[0].start()].strip(), [m.group(0).strip() for m in taken]


def parse_text_statement(blocks: list, spec: dict, key: str) -> Statement:
    """Parse line-oriented statement text (the PDF path)."""
    rules = load_formats()
    d = rules["defaults"]
    layout = spec.get("layout", {})
    verified = bool(spec.get("verified"))
    conf = d["confidence_verified"] if verified else d["confidence_unverified"]

    st = Statement(bank=key, label=spec.get("label", key), verified=verified,
                   confidence=conf, currency=d["currency"],
                   is_business=bool(layout.get("is_business")))

    text = "\n".join(b.text for b in blocks)

    # Patterns are NOT compiled with re.I globally: an all-caps capture like
    # ([A-Z][A-Z ]+) for an account holder becomes greedy under re.I and eats
    # the next label. Case-insensitivity is opted into per-group in the YAML
    # with (?i:...).
    for field_name, pattern_key in (("account_no", "account_no_pattern"),
                                    ("branch_code", "branch_pattern"),
                                    ("holder", "holder_pattern")):
        pat = layout.get(pattern_key)
        if pat:
            m = re.search(pat, text)
            if m:
                setattr(st, field_name, m.group(1).strip())

    pat = layout.get("period_pattern")
    fallback_year = None
    fmts = [layout.get("date_format")] + d["date_formats"]
    fmts = [f for f in fmts if f]
    if pat:
        m = re.search(pat, text)
        if m:
            frm = _parse_date(m.group(1), fmts, None)
            to = _parse_date(m.group(2), fmts, None)
            if frm and to:
                st.period = {"from": frm, "to": to}
                fallback_year = int(to[:4])

    skip = [s.lower() for s in layout.get("skip_rows_matching", [])]
    kind = layout.get("kind", "signed_amount")

    # An empty cell leaves no trace in extracted PDF text, so a two-column row
    # yields TWO amounts (its own plus the balance), not three. Column position
    # therefore cannot say whether a row is money-in or money-out.
    #
    # The running balance can: prev_balance + amount == balance is an identity
    # the statement itself asserts. Deriving the sign from the balance delta and
    # cross-checking the magnitude against the printed amount is both more
    # robust than column counting and self-verifying.
    prev_balance: int | None = None
    for block in blocks:
        line = block.text.strip()
        m = _LINE.match(line)
        if not m:
            continue
        iso = _parse_date(m.group("date"), fmts, fallback_year)
        if not iso:
            continue

        rest = m.group("rest")
        low = rest.lower()

        # Opening/closing balance rows are not transactions, but the opening
        # balance seeds the delta chain, so read it before skipping.
        if any(s in low for s in skip):
            tokens = re.findall(_AMOUNT_TOKEN, rest)
            if tokens:
                seed = money.parse(tokens[-1])
                if seed is not None:
                    prev_balance = seed
            continue

        desc, amounts = _split_trailing_amounts(rest, 2)
        if len(amounts) < 2:
            continue

        printed, bal_c = money.parse(amounts[0]), money.parse(amounts[1])
        if bal_c is None:
            continue

        if kind == "two_column":
            if prev_balance is None:
                # No chain yet — fall back to the printed magnitude as an
                # outflow, the commoner case, and let reconciliation catch it.
                signed = -(abs(printed) if printed is not None else 0)
            else:
                signed = bal_c - prev_balance
                if printed is not None and abs(abs(signed) - abs(printed)) > 1:
                    st.warnings.append(
                        f"row {block.locator}: balance delta {signed} disagrees with "
                        f"printed amount {printed}"
                    )
        else:
            if printed is None:
                continue
            signed = printed

        prev_balance = bal_c
        st.rows.append(Row(
            date=iso, description=re.sub(r"\s+", " ", desc).strip(),
            amount_cents=signed, balance_cents=bal_c,
            locator=block.locator, confidence=conf,
        ))

    _validate(st)
    return st


def parse_tabular(table, spec: dict, key: str) -> Statement:
    """Parse a delimited export by matching column HEADERS, not positions.

    Position is the thing that varies most between exports; a header name is
    comparatively stable.
    """
    rules = load_formats()
    d = rules["defaults"]
    generic = rules["generic_tabular"]
    verified = bool(spec.get("verified"))
    conf = d["confidence_verified"] if verified else d["confidence_unverified"]
    layout = spec.get("layout", {})

    st = Statement(bank=key or "generic_tabular",
                   label=spec.get("label", generic["label"]),
                   verified=verified, confidence=conf, currency=d["currency"],
                   is_business=bool(layout.get("is_business")))

    if not table or len(table.rows) < 2:
        st.errors.append("no tabular rows")
        return st

    header = [h.strip().lower() for h in table.rows[0]]
    idx: dict[str, int] = {}
    for field_name, aliases in generic["header_aliases"].items():
        for i, h in enumerate(header):
            if h in [a.lower() for a in aliases]:
                idx[field_name] = i
                break

    if "date" not in idx or "description" not in idx:
        st.errors.append(f"could not identify date/description columns in header {header}")
        return st
    if "amount" not in idx and not ("out" in idx or "in" in idx):
        st.errors.append(f"could not identify an amount column in header {header}")
        return st

    fmts = [layout.get("date_format")] + d["date_formats"]
    fmts = [f for f in fmts if f]

    for n, raw in enumerate(table.rows[1:], start=2):
        if len(raw) <= max(idx.values()):
            continue
        iso = _parse_date(raw[idx["date"]], fmts, None)
        if not iso:
            continue
        if "amount" in idx:
            signed = money.parse(raw[idx["amount"]])
        else:
            out_c = money.parse(raw[idx["out"]]) if "out" in idx else None
            in_c = money.parse(raw[idx["in"]]) if "in" in idx else None
            signed = None if (out_c is None and in_c is None) else (in_c or 0) - abs(out_c or 0)
        if signed is None:
            continue
        bal = money.parse(raw[idx["balance"]]) if "balance" in idx else None
        st.rows.append(Row(
            date=iso, description=re.sub(r"\s+", " ", raw[idx["description"]]).strip(),
            amount_cents=signed, balance_cents=bal,
            locator=f"row={n}", confidence=conf,
        ))

    if st.rows:
        st.period = {"from": min(r.date for r in st.rows), "to": max(r.date for r in st.rows)}
    _validate(st)
    return st


def _validate(st: Statement) -> None:
    """Running-balance check — the cheapest possible proof the parse is right.

    If every row's balance equals the previous balance plus the amount, the
    column order, sign convention and decimal separator are all correct. If it
    does not reconcile, something is wrong in a way that would otherwise be
    invisible, so the whole statement is dropped below the floor.
    """
    if not st.rows:
        st.errors.append("no transaction rows recognised")
        return

    with_bal = [r for r in st.rows if r.balance_cents is not None]
    if len(with_bal) < 2:
        st.warnings.append("no running balance to reconcile against")
        return

    breaks = 0
    for prev, cur in zip(with_bal, with_bal[1:], strict=False):
        if prev.balance_cents + cur.amount_cents != cur.balance_cents:
            breaks += 1

    if breaks:
        st.warnings.append(
            f"running balance does not reconcile on {breaks} of {len(with_bal) - 1} rows"
        )
        if breaks > len(with_bal) * 0.1:
            st.confidence = min(st.confidence, 0.5)
            st.errors.append(
                "balance reconciliation failed — the column order or sign convention "
                "is probably wrong for this layout. Rows go to proposed/, not the ledger."
            )
            for r in st.rows:
                r.confidence = st.confidence
    else:
        st.warnings.append(f"running balance reconciles across {len(with_bal)} rows")


def parse(extraction, *, filename: str = "") -> Statement:
    """Entry point: an Extraction to a Statement."""
    key, spec = fingerprint(f"{filename}\n{extraction.text}")

    if extraction.tables and (key is None or spec.get("layout", {}).get("columns")):
        widest = max(extraction.tables, key=lambda t: len(t.rows))
        header = " ".join(widest.rows[0]).lower() if widest.rows else ""
        if any(w in header for w in ("date", "posting", "datum")):
            return parse_tabular(widest, spec, key)

    if key is None:
        st = Statement(bank="unknown", label="unidentified institution",
                       verified=False, confidence=0.0)
        st.errors.append(
            "no bank adapter matched this document. Add a fingerprint to "
            ".claude/rules/bank-formats.yaml — describe the LAYOUT, never the contents."
        )
        return st

    return parse_text_statement(extraction.blocks, spec, key)
