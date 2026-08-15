"""Document type detection.

Scores extracted text against .claude/rules/document-types.yaml. Rules are data;
adding a type is an edit to that file plus a fixture, never a code change.

The important behaviour is what happens when the answer is unclear. A winner
must beat both an absolute floor and the runner-up by a margin; otherwise the
document is UNCLASSIFIED. A confident wrong classification files a will under
`finance` and routes it to the wrong agent — far worse than an honest "I don't
know" that becomes a gap record and a question.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from functools import cache

from . import vault

RULES_PATH = vault.repo_root() / ".claude" / "rules" / "document-types.yaml"

_STRONG_WEIGHT = 3
_ANY_WEIGHT = 1

# Enough text to judge by. Beyond this the signal is already decided, and
# scanning a 200-page deed adds nothing.
_SCAN_CHARS = 20_000


@dataclass
class Classification:
    type: str = "unclassified"
    domain: str = "unclassified"
    routes_to: str | None = None
    score: int = 0
    runner_up: str | None = None
    runner_up_score: int = 0
    matched: list[str] = field(default_factory=list)
    period: dict | None = None
    unseen: bool = False
    reason: str = ""

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


@cache
def load_rules() -> dict:
    from ruamel.yaml import YAML

    yaml = YAML(typ="safe")
    with RULES_PATH.open(encoding="utf-8") as fh:
        return yaml.load(fh)


def _score(text: str, rule: dict) -> tuple[int, list[str]]:
    matched: list[str] = []

    for term in rule.get("require", []):
        if term.lower() not in text:
            return 0, []

    total = 0
    for term in rule.get("strong", []):
        if term.lower() in text:
            total += _STRONG_WEIGHT
            matched.append(term)
    for term in rule.get("any", []):
        if term.lower() in text:
            total += _ANY_WEIGHT
            matched.append(term)
    return total, matched


# ── period detection ─────────────────────────────────────────────────────────

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}

_DATE_PATTERNS = [
    re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"),                                    # 2026-07-31
    re.compile(r"\b(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})\b"),                      # 01 Jul 2026
    re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b"),                                # 31/07/2026
]


def _dates(text: str) -> list[date]:
    found: list[date] = []
    for rx in _DATE_PATTERNS:
        for m in rx.finditer(text):
            try:
                a, b, c = m.groups()
                if rx is _DATE_PATTERNS[0]:
                    found.append(date(int(a), int(b), int(c)))
                elif rx is _DATE_PATTERNS[1]:
                    mon = _MONTHS.get(b[:3].lower())
                    if mon:
                        found.append(date(int(c), mon, int(a)))
                else:
                    found.append(date(int(c), int(b), int(a)))
            except ValueError:
                continue  # 31 February and friends
    return found


def detect_period(text: str) -> dict | None:
    """Earliest and latest plausible date in the document.

    Used only to pick the filing year, so a wide guess is harmless; a WRONG year
    would file a July 2026 statement under 2019, so implausible years are
    discarded rather than trusted.
    """
    plausible = [d for d in _dates(text) if 1950 <= d.year <= date.today().year + 2]
    if not plausible:
        return None
    return {"from": min(plausible).isoformat(), "to": max(plausible).isoformat()}


def classify(text: str, *, filename: str = "") -> Classification:
    rules = load_rules()
    haystack = f"{filename}\n{text}"[:_SCAN_CHARS].lower()

    scored = []
    for name, rule in rules["types"].items():
        total, matched = _score(haystack, rule)
        if total:
            scored.append((total, name, rule, matched))
    scored.sort(key=lambda x: (-x[0], x[1]))

    if not scored:
        return Classification(
            unseen=True,
            reason="no rule matched — this may be a document type LifeOS has never seen",
        )

    top_score, top_name, top_rule, matched = scored[0]
    runner_up, runner_score = (scored[1][1], scored[1][0]) if len(scored) > 1 else (None, 0)

    if top_score < rules["min_score"]:
        return Classification(
            score=top_score, runner_up=top_name, runner_up_score=top_score, matched=matched,
            reason=f"best candidate '{top_name}' scored {top_score}, below the floor of {rules['min_score']}",
        )

    if top_score - runner_score < rules["min_margin"] and runner_up:
        return Classification(
            score=top_score, runner_up=runner_up, runner_up_score=runner_score, matched=matched,
            reason=(f"ambiguous: '{top_name}' ({top_score}) vs '{runner_up}' ({runner_score}) — "
                    f"margin below {rules['min_margin']}. Refusing to guess."),
        )

    return Classification(
        type=top_name,
        domain=top_rule.get("domain", "unclassified"),
        routes_to=top_rule.get("routes_to"),
        score=top_score,
        runner_up=runner_up,
        runner_up_score=runner_score,
        matched=matched[:12],
        period=detect_period(text) if top_rule.get("period") or True else None,
        reason="",
    )
