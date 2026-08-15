"""The South African fiscal calendar.

Cadence triggers compare cursors against the clock AND against these anchors.
Each carries a lead time so work starts before the date, not on it.

Rates, thresholds and limits are deliberately NOT here — those live in
.claude/rules/za/*.yaml with an "as at" date and a refresh interval, because
they change annually and a hard-coded number cannot carry its own provenance.
This module holds only the shape of the year, which does not change.
See docs/adr/0016-jurisdiction-as-config-axis.md.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

CADENCES = ("hourly", "daily", "weekly", "monthly", "quarterly", "annual")

CADENCE_SECONDS = {
    "hourly": 3600,
    "daily": 86_400,
    "weekly": 604_800,
    "monthly": 2_592_000,      # 30d — the trigger is "at least this stale"
    "quarterly": 7_776_000,    # 90d
    "annual": 31_536_000,      # 365d
}


@dataclass(frozen=True)
class Anchor:
    key: str
    label: str
    lead_days: int
    applies_to: str  # "individual" | "entity" | "trust" | "employer" | "any"


ANCHORS: tuple[Anchor, ...] = (
    Anchor("tax_year_end", "Personal tax year end — RA top-up, TFSA limit, CGT harvesting", 60, "individual"),
    Anchor("irp6_1", "Provisional tax IRP6 period 1", 30, "any"),
    Anchor("irp6_2", "Provisional tax IRP6 period 2", 30, "any"),
    Anchor("filing_season", "Personal income tax filing season opens", 30, "individual"),
    Anchor("itr14", "Company ITR14 (12 months after year end)", 60, "entity"),
    Anchor("it12tr", "Trust IT12TR, annual financial statements, beneficial-ownership filing", 90, "trust"),
    Anchor("emp201", "PAYE/UIF/SDL monthly return", 5, "employer"),
    Anchor("vat201", "VAT return", 7, "entity"),
    Anchor("medical_option_change", "Medical aid option-change window", 30, "individual"),
)


def is_leap(year: int) -> bool:
    return calendar.isleap(year)


def tax_year_end(year: int) -> date:
    """Last day of February — 29th in a leap year."""
    return date(year, 2, 29 if is_leap(year) else 28)


def tax_year_of(d: date) -> int:
    """SA year of assessment, identified by the year in which it ends.

    1 March 2026 – 28 February 2027 is the 2027 tax year.
    """
    return d.year + 1 if d.month >= 3 else d.year


def tax_year_bounds(tax_year: int) -> tuple[date, date]:
    return date(tax_year - 1, 3, 1), tax_year_end(tax_year)


def _next_on_or_after(d: date, month: int, day: int) -> date:
    for year in (d.year, d.year + 1):
        last = calendar.monthrange(year, month)[1]
        candidate = date(year, month, min(day, last))
        if candidate >= d:
            return candidate
    raise AssertionError("unreachable")


def next_occurrence(key: str, today: date) -> date | None:
    """Next occurrence of a fixed-date anchor. Returns None for anchors whose
    date depends on entity-specific data (year ends, VAT cycles)."""
    if key == "tax_year_end":
        end = tax_year_end(today.year)
        return end if end >= today else tax_year_end(today.year + 1)
    if key == "irp6_1":
        return _next_on_or_after(today, 8, 31)
    if key == "irp6_2":
        end = tax_year_end(today.year)
        return end if end >= today else tax_year_end(today.year + 1)
    if key == "filing_season":
        return _next_on_or_after(today, 7, 1)
    if key == "emp201":
        return _next_on_or_after(today, today.month if today.day <= 7 else (today.month % 12) + 1, 7)
    if key == "medical_option_change":
        return _next_on_or_after(today, 10, 1)
    return None  # itr14, it12tr, vat201 — derived from the entity's own year end


def due_anchors(today: date) -> list[dict]:
    """Anchors whose lead window is open today.

    An anchor inside its lead window is a signal even when nothing in the vault
    has changed — this is the half of SENSE that prevents 'doing nothing because
    nothing obviously changed'.
    """
    out: list[dict] = []
    for a in ANCHORS:
        when = next_occurrence(a.key, today)
        if when is None:
            continue
        days = (when - today).days
        if 0 <= days <= a.lead_days:
            out.append(
                {
                    "anchor": a.key,
                    "label": a.label,
                    "due_on": when.isoformat(),
                    "days_until": days,
                    "lead_days": a.lead_days,
                    "applies_to": a.applies_to,
                }
            )
    return sorted(out, key=lambda x: x["days_until"])


def company_itr14_due(year_end: date) -> date:
    return year_end + timedelta(days=365)
