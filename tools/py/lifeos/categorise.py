"""Transaction categorisation.

Three tiers, in order of trust:

  1. **rule**    a merchant pattern from .claude/rules/categories.yaml
  2. **history** an earlier transaction with a near-identical description that a
                 HUMAN categorised — the user's own past decisions outrank a
                 generic rule about their life
  3. **none**    uncategorised, with a question

There is deliberately no automatic LLM tier. A wrong category is worse than no
category: it silently distorts cashflow, budget variance, the savings rate and
which expenses look tax-deductible, and nothing about the output looks wrong.
Uncategorised is visible; miscategorised is not.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache

from . import vault

RULES_PATH = vault.repo_root() / ".claude" / "rules" / "categories.yaml"

# Below this a fuzzy history match is not trusted.
_HISTORY_MIN_RATIO = 88


@dataclass
class Category:
    category: str | None = None
    subcategory: str | None = None
    tax_relevance: list[str] | None = None
    confidence: float = 0.0
    method: str = "none"          # rule | history | human | none
    matched: str | None = None

    @property
    def ok(self) -> bool:
        return self.category is not None


@cache
def load_rules() -> dict:
    from ruamel.yaml import YAML

    yaml = YAML(typ="safe")
    with RULES_PATH.open(encoding="utf-8") as fh:
        return yaml.load(fh)


def _normalise(desc: str) -> str:
    """Strip the noise banks add so two visits to the same shop look the same.

    Card sequence numbers, dates, branch codes and reference digits all vary per
    transaction and would otherwise defeat history matching.
    """
    s = desc.lower()
    s = re.sub(r"\b\d{2}[/-]\d{2}([/-]\d{2,4})?\b", " ", s)   # dates
    s = re.sub(r"\*+\d+", " ", s)                              # masked card digits
    s = re.sub(r"\b\d{4,}\b", " ", s)                          # long refs
    s = re.sub(r"\b(pos|purch|purchase|payment|ref|card|seq|txn|trf)\b", " ", s)
    return re.sub(r"[^a-z0-9 ]+", " ", s).strip()


def by_rule(description: str, amount_cents: int) -> Category:
    rules = load_rules()
    low = description.lower()

    for rule in rules["rules"]:
        direction = rule.get("direction")
        if direction == "in" and amount_cents < 0:
            continue
        if direction == "out" and amount_cents > 0:
            continue
        for pattern in rule["match"]:
            if pattern.lower() in low:
                return Category(
                    category=rule["category"],
                    subcategory=rule.get("subcategory"),
                    tax_relevance=rule.get("tax_relevance"),
                    confidence=float(rule.get("confidence", 0.9)),
                    method="rule",
                    matched=pattern,
                )
    return Category()


def by_history(description: str, history: list[dict]) -> Category:
    """Match against transactions a HUMAN has already categorised.

    Only human-confirmed history counts. Learning from the categoriser's own
    output would let one early mistake propagate through every future month,
    growing more confident as it went.
    """
    if not history:
        return Category()

    from rapidfuzz import fuzz, process

    target = _normalise(description)
    if not target:
        return Category()

    confirmed = [h for h in history if h.get("category_method") == "human" and h.get("category")]
    if not confirmed:
        return Category()

    choices = {i: _normalise(h.get("description_raw", "")) for i, h in enumerate(confirmed)}
    best = process.extractOne(
        target, choices, scorer=fuzz.token_sort_ratio, score_cutoff=_HISTORY_MIN_RATIO
    )
    if not best:
        return Category()

    match = confirmed[best[2]]
    return Category(
        category=match.get("category"),
        subcategory=match.get("subcategory"),
        tax_relevance=match.get("tax_relevance"),
        # Scale confidence by similarity: an 88% match is not a 100% match.
        confidence=round(0.90 * (best[1] / 100.0) + 0.05, 3),
        method="history",
        matched=match.get("description_raw", "")[:60],
    )


def categorise(description: str, amount_cents: int, *, history: list[dict] | None = None) -> Category:
    """History first — the user's own decisions outrank a generic rule."""
    hist = by_history(description, history or [])
    if hist.ok and hist.confidence >= load_rules()["min_confidence"]:
        return hist

    rule = by_rule(description, amount_cents)
    if rule.ok:
        return rule

    return hist if hist.ok else Category()


def floor() -> float:
    return float(load_rules()["min_confidence"])
