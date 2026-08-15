"""READINESS — the Life File checklist as a live, scored artefact.

Backs /readiness and supplies the gaps section of /life-file.

Two decisions drive everything here:

  * **The score is weighted by consequence, not by count.** Ten missing gym
    contracts must not outweigh one missing signed will. A percentage that
    treats them equally is decoration.

  * **The shortest path is score-delta divided by effort.** "What should I do
    next" has a real answer, and it is usually not the biggest gap — it is the
    catastrophic one that takes ten minutes.

A fourth status exists beside present/absent/expired: `unattributed`. A document
of the right type is in the vault, but LifeOS cannot yet prove whose it is, so
it counts as half and says so. Subject attribution deepens as the identity
domain lands; pretending to certainty now would be the wrong kind of quiet.

Usage:  python -m lifeos.readiness [--json|--markdown]
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import date
from functools import cache

from . import atomic, clock, vault

RULES_PATH = vault.repo_root() / ".claude" / "rules" / "readiness-requirements.yaml"

CONSEQUENCE_WEIGHT = {"catastrophic": 16, "severe": 8, "moderate": 3, "minor": 1}
EFFORT_COST = {"minutes": 1, "hours": 3, "days": 8, "weeks": 20}

# An unattributed document is real evidence, just not proof of ownership.
_UNATTRIBUTED_CREDIT = 0.5


@cache
def load_rules() -> dict:
    from ruamel.yaml import YAML

    yaml = YAML(typ="safe")
    with RULES_PATH.open(encoding="utf-8") as fh:
        return yaml.load(fh)


@cache
def load_profile() -> dict:
    from ruamel.yaml import YAML

    p = vault.path("profile", "profile.yaml")
    if not p.is_file():
        return {}
    yaml = YAML(typ="safe")
    with p.open(encoding="utf-8") as fh:
        return yaml.load(fh) or {}


@dataclass
class Row:
    id: str
    subject_ref: str
    subject_label: str
    requirement: str
    category: str
    domain: str
    status: str                     # present | absent | expired | unattributed | not_tracked
    consequence: str
    effort: str
    weight: int = 0
    credit: float = 0.0
    doc_hash: str | None = None
    filed_path: str | None = None
    age_days: int | None = None
    note: str = ""
    detail: str = ""

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class Score:
    percent: float = 0.0
    earned: float = 0.0
    possible: int = 0
    rows: list[Row] = field(default_factory=list)
    by_category: dict = field(default_factory=dict)
    not_tracked: list[dict] = field(default_factory=list)


def _subjects() -> tuple[list[dict], list[dict]]:
    """People and entities from profile.yaml, each with its relation/form.

    The relation matters: telling someone their eight-year-old needs a signed
    will is wrong, and wrong advice in a readiness score costs trust faster
    than a missing feature does.
    """
    prof = load_profile()

    def parse(items, prefix, kind_key):
        out = []
        for item in items or []:
            if isinstance(item, dict):
                name = str(item.get("name") or item.get("legal_name") or "?")
                out.append({
                    "ref": item.get("ref") or f"{prefix}_{name.lower().replace(' ', '_')}",
                    "label": name,
                    "kind": item.get(kind_key),
                })
            elif isinstance(item, str):
                out.append({"ref": f"{prefix}_{item.lower().replace(' ', '_')}",
                            "label": item, "kind": None})
        return out

    return parse(prof.get("people"), "per", "relation"), parse(prof.get("entities"), "ent", "form")


def _applicable(req: dict, subject: dict, scope: str) -> bool:
    """Does this requirement apply to this subject?"""
    if scope == "person":
        allowed = req.get("applies_to_relations")
        if allowed and subject.get("kind") not in allowed:
            return False
    elif scope == "entity":
        allowed = req.get("applies_to_forms")
        if allowed and subject.get("kind") not in allowed:
            return False
    return True


def _enabled_domains() -> dict[str, bool]:
    return load_profile().get("domains", {}) or {}


def _documents() -> list[dict]:
    return list(atomic.read_jsonl(vault.path("documents", "index.jsonl")))


def _age_days(iso: str | None, today: date) -> int | None:
    if not iso:
        return None
    try:
        return (today - date.fromisoformat(iso[:10])).days
    except ValueError:
        return None


def _match(req: dict, docs: list[dict]) -> dict | None:
    """Newest filed document satisfying this requirement, by type."""
    types = set(req.get("satisfied_by") or [])
    if not types:
        return None
    candidates = [d for d in docs if d.get("type") in types and not d.get("redacted")]
    if not candidates:
        return None
    return max(candidates, key=lambda d: (d.get("period") or {}).get("to") or d.get("ingested_at", ""))


def evaluate() -> Score:
    rules = load_rules()
    docs = _documents()
    people, entities = _subjects()
    enabled = _enabled_domains()
    today = date.fromisoformat(clock.today())

    score = Score()

    for req in rules["requirements"]:
        scope = req.get("scope", "household")
        domain = req.get("domain", "unclassified")

        if scope == "person":
            targets = [s for s in people if _applicable(req, s, scope)]
        elif scope == "entity":
            targets = [s for s in entities if _applicable(req, s, scope)]
        else:
            targets = [{"ref": "household", "label": "Household", "kind": None}]

        # A disabled domain degrades to "not tracked" and is excluded from the
        # score — never silently dropped from the map.
        if enabled and not enabled.get(domain, False):
            for s in targets or [{"ref": "household", "label": "Household"}]:
                score.not_tracked.append({
                    "id": req["id"], "requirement": req["label"], "domain": domain,
                    "subject_ref": s["ref"], "subject_label": s["label"],
                    "reason": f"domain '{domain}' is disabled in profile.yaml",
                })
            continue

        if not targets:
            continue

        weight = CONSEQUENCE_WEIGHT[req["consequence"]]
        doc = _match(req, docs)

        for subject in targets:
            ref, label = subject["ref"], subject["label"]
            row = Row(
                id=req["id"], subject_ref=ref, subject_label=label,
                requirement=req["label"], category=req["category"], domain=domain,
                status="absent", consequence=req["consequence"], effort=req["effort"],
                weight=weight, note=(req.get("note") or "").strip(),
            )

            if doc is None:
                row.detail = (
                    "no document of the required type has been filed"
                    if req.get("satisfied_by")
                    else "not recorded anywhere in the vault"
                )
            else:
                row.doc_hash = doc.get("doc_hash")
                row.filed_path = doc.get("filed_path")
                row.age_days = _age_days(
                    (doc.get("period") or {}).get("to") or doc.get("ingested_at"), today
                )
                expires = req.get("expires_days")
                if expires and row.age_days is not None and row.age_days > expires:
                    row.status = "expired"
                    row.detail = f"newest is {row.age_days} days old; must be under {expires}"
                elif scope in {"person", "entity"}:
                    # Evidence exists, ownership is unproven. Half credit, and say why.
                    row.status = "unattributed"
                    row.credit = weight * _UNATTRIBUTED_CREDIT
                    row.detail = (
                        f"a {doc.get('type')} is filed, but LifeOS cannot yet prove it "
                        f"belongs to {label}"
                    )
                else:
                    row.status = "present"
                    row.credit = weight
                    row.detail = f"{doc.get('type')} filed"

            score.rows.append(row)
            score.possible += weight
            score.earned += row.credit

    score.percent = round(100 * score.earned / score.possible, 1) if score.possible else 0.0

    for row in score.rows:
        b = score.by_category.setdefault(row.category, {"earned": 0.0, "possible": 0, "gaps": 0})
        b["earned"] += row.credit
        b["possible"] += row.weight
        if row.status in {"absent", "expired"}:
            b["gaps"] += 1
    for b in score.by_category.values():
        b["percent"] = round(100 * b["earned"] / b["possible"], 1) if b["possible"] else 0.0

    return score


def shortest_path(score: Score, limit: int = 5) -> list[dict]:
    """Rank open items by score gained per unit of effort.

    This is why the answer is usually not the biggest gap: a catastrophic item
    that takes ten minutes beats a severe one that takes weeks, every time.
    """
    if not score.possible:
        return []

    # Group by requirement, not by row. "Record where the will is" for three
    # people is ONE errand, and a top-five list padded with three copies of it
    # is a worse answer than one line naming all three.
    grouped: dict[str, dict] = {}
    for row in score.rows:
        remaining = row.weight - row.credit
        if remaining <= 0:
            continue
        g = grouped.setdefault(row.id, {
            "id": row.id,
            "action": row.requirement,
            "subjects": [],
            "statuses": set(),
            "consequence": row.consequence,
            "effort": row.effort,
            "remaining": 0.0,
            "why": row.note or row.detail,
        })
        g["remaining"] += remaining
        g["statuses"].add(row.status)
        if row.subject_ref != "household":
            g["subjects"].append(row.subject_label)

    out = []
    for g in grouped.values():
        delta = 100 * g["remaining"] / score.possible
        # Effort is per errand, not per subject: recording three locations while
        # you are already standing at the safe does not cost three times as much.
        cost = EFFORT_COST[g["effort"]]
        out.append({
            "id": g["id"],
            "action": g["action"],
            "subjects": g["subjects"] or ["Household"],
            "status": sorted(g["statuses"])[0],
            "consequence": g["consequence"],
            "effort": g["effort"],
            "score_gain": round(delta, 1),
            "value_per_effort": round(delta / cost, 2),
            "why": g["why"],
        })
    out.sort(key=lambda c: (-c["value_per_effort"], -c["score_gain"]))
    return out[:limit]


def report() -> dict:
    if not vault.is_initialised():
        return {"schema": "readiness/1", "error": "no vault — run /lifeos-init"}

    score = evaluate()
    open_rows = [r for r in score.rows if r.status in {"absent", "expired", "unattributed"}]
    return {
        "schema": "readiness/1",
        "at": clock.stamp(),
        "score": score.percent,
        "earned": round(score.earned, 1),
        "possible": score.possible,
        "by_category": score.by_category,
        "counts": {
            s: sum(1 for r in score.rows if r.status == s)
            for s in ("present", "unattributed", "expired", "absent")
        },
        "catastrophic_gaps": [
            r.to_dict() for r in score.rows
            if r.consequence == "catastrophic" and r.status in {"absent", "expired"}
        ],
        "shortest_path": shortest_path(score),
        "rows": [r.to_dict() for r in score.rows],
        "open": [r.to_dict() for r in open_rows],
        "not_tracked": score.not_tracked,
    }


def to_markdown(rep: dict) -> str:
    if rep.get("error"):
        return f"**{rep['error']}**"
    lines = [
        f"# Readiness: {rep['score']}%",
        "",
        f"{rep['counts']['present']} present · {rep['counts']['unattributed']} unattributed · "
        f"{rep['counts']['expired']} expired · {rep['counts']['absent']} absent",
        "",
    ]
    if rep["catastrophic_gaps"]:
        lines += ["## Catastrophic gaps", ""]
        for g in rep["catastrophic_gaps"]:
            lines.append(f"- **{g['requirement']}** ({g['subject_label']}) — {g['detail']}")
        lines.append("")
    lines += ["## Shortest path", ""]
    for i, s in enumerate(rep["shortest_path"], 1):
        lines.append(
            f"{i}. **{s['action']}** — {s['effort']}, +{s['score_gain']}% "
            f"({s['consequence']})"
        )
    lines += ["", "## By category", "", "| Category | Score | Gaps |", "|---|---|---|"]
    for cat, b in sorted(rep["by_category"].items()):
        lines.append(f"| {cat} | {b['percent']}% | {b['gaps']} |")
    if rep["not_tracked"]:
        lines += ["", f"_{len(rep['not_tracked'])} requirement(s) not tracked — domain disabled._"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lifeos.readiness")
    ap.add_argument("--markdown", action="store_true")
    args = ap.parse_args(argv)
    rep = report()
    print(to_markdown(rep) if args.markdown else json.dumps(rep, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
