"""Rulebook loading, with staleness and verification enforced rather than trusted.

Every claim about tax law carries an "as at" date and a source. This module is
what makes that structural instead of aspirational: a value cannot be read
without also reading how old it is and whether anyone has checked it.

Two flags travel with every rule and with every figure computed from it:

    stale                its refresh interval has elapsed, or its tax year is
                         not the current one
    requires_verification  `verified: false` — the value was written from memory
                         and has not been confirmed against the source

`Computation` carries both forward, so a report cannot print a bare number that
came from an unverified rule. A confident wrong estate-duty figure is worse than
no figure: it gets planned around, and the error surfaces at the moment the
family can least absorb it.

Usage:  python -m lifeos.rules [--check]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from functools import cache

from . import calendar_za, clock, vault

RULES_DIR = vault.repo_root() / ".claude" / "rules"


class RuleNotFound(KeyError):
    pass


@dataclass
class Rule:
    name: str
    jurisdiction: str
    data: dict
    as_at: str
    source: str
    verified: bool
    tax_year: int | None
    refresh_interval: str

    def __getitem__(self, key):
        return self.data[key]

    def get(self, key, default=None):
        return self.data.get(key, default)

    @property
    def age_days(self) -> int:
        try:
            return (date.fromisoformat(clock.today()) - date.fromisoformat(self.as_at)).days
        except ValueError:
            return 10**6

    @property
    def interval_days(self) -> int:
        m = re.fullmatch(r"P(?:(\d+)Y)?(?:(\d+)M)?(?:(\d+)D)?", self.refresh_interval or "P1Y")
        if not m:
            return 365
        y, mo, d = (int(g or 0) for g in m.groups())
        return y * 365 + mo * 30 + d

    @property
    def current_tax_year(self) -> int:
        return calendar_za.tax_year_of(date.fromisoformat(clock.today()))

    @property
    def stale(self) -> bool:
        if self.tax_year is not None and self.tax_year < self.current_tax_year:
            return True
        return self.age_days > self.interval_days

    @property
    def status(self) -> dict:
        why = []
        if self.tax_year is not None and self.tax_year < self.current_tax_year:
            why.append(
                f"carries {self.tax_year} tax-year figures; the current year is "
                f"{self.current_tax_year}"
            )
        if self.age_days > self.interval_days:
            why.append(f"last dated {self.as_at}, {self.age_days} days ago")
        if not self.verified:
            why.append("never verified against the source")
        return {
            "rule": self.name, "as_at": self.as_at, "source": self.source,
            "verified": self.verified, "tax_year": self.tax_year,
            "stale": self.stale, "why": why,
        }


@dataclass
class Computation:
    """A figure, and everything a reader needs to judge how far to trust it."""

    value: int | float | None
    label: str
    formula: str = ""
    rules_used: list[Rule] = field(default_factory=list)
    inputs: dict = field(default_factory=dict)
    record_ids: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def requires_verification(self) -> bool:
        return any(not r.verified for r in self.rules_used)

    @property
    def stale(self) -> bool:
        return any(r.stale for r in self.rules_used)

    def to_dict(self) -> dict:
        return {
            "value": self.value,
            "label": self.label,
            "formula": self.formula,
            "inputs": self.inputs,
            "record_ids": self.record_ids,
            "notes": self.notes,
            "requires_verification": self.requires_verification,
            "stale": self.stale,
            "rules": [{"rule": r.name, "as_at": r.as_at, "tax_year": r.tax_year,
                       "verified": r.verified, "source": r.source} for r in self.rules_used],
        }


@cache
def load(name: str, jurisdiction: str = "za") -> Rule:
    from ruamel.yaml import YAML

    path = RULES_DIR / jurisdiction / f"{name}.yaml"
    if not path.is_file():
        raise RuleNotFound(
            f"no rulebook '{name}' for jurisdiction '{jurisdiction}' "
            f"(expected {vault.rel(path)})"
        )
    yaml = YAML(typ="safe")
    with path.open(encoding="utf-8") as fh:
        data = yaml.load(fh)
    return Rule(
        name=f"{jurisdiction}/{name}",
        jurisdiction=jurisdiction,
        data=data,
        as_at=str(data.get("as_at", "1970-01-01")),
        source=str(data.get("source", "")),
        verified=bool(data.get("verified", False)),
        tax_year=data.get("tax_year"),
        refresh_interval=str(data.get("refresh_interval", "P1Y")),
    )


def all_rules(jurisdiction: str = "za") -> list[Rule]:
    d = RULES_DIR / jurisdiction
    if not d.is_dir():
        return []
    return [load(p.stem, jurisdiction) for p in sorted(d.glob("*.yaml"))]


def caveat(items: list[Computation] | Computation) -> str:
    """The sentence that must accompany any figure built on unverified rules."""
    comps = [items] if isinstance(items, Computation) else items
    rules = {r.name: r for c in comps for r in c.rules_used}
    unverified = [r for r in rules.values() if not r.verified]
    stale = [r for r in rules.values() if r.stale]
    if not unverified and not stale:
        return ""

    parts = []
    if unverified:
        parts.append(
            "These figures use tax rules that have **not been verified against "
            "SARS**: " + ", ".join(sorted(r.name for r in unverified)) + "."
        )
    if stale:
        oldest = min(stale, key=lambda r: r.as_at)
        parts.append(
            f"The oldest is dated {oldest.as_at}"
            + (f" and carries {oldest.tax_year} tax-year figures"
               if oldest.tax_year else "")
            + f"; the current tax year is {oldest.current_tax_year}."
        )
    parts.append(
        "Treat every number here as an order-of-magnitude estimate for a "
        "conversation with a registered tax practitioner, not as a calculation "
        "to plan around."
    )
    return " ".join(parts)


def check() -> dict:
    """Backs /status and the rule.expired signal."""
    rules = all_rules()
    return {
        "schema": "rules-check/1",
        "at": clock.stamp(),
        "current_tax_year": calendar_za.tax_year_of(date.fromisoformat(clock.today())),
        "total": len(rules),
        "stale": [r.status for r in rules if r.stale],
        "unverified": [r.name for r in rules if not r.verified],
        "ok": [r.name for r in rules if not r.stale and r.verified],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lifeos.rules")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--show", help="print one rulebook")
    args = ap.parse_args(argv)
    if args.show:
        print(json.dumps(load(args.show).data, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(check(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
