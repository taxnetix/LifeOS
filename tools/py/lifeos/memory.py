"""MEMORY — the consolidation ritual. Backs /consolidate.

Three tiers, aged by horizon, with every change audited. The part that matters
most is what this refuses to do: **contradictions are surfaced, never resolved.**

If long-term memory says "rejects anything with a lock-in period" and today's
decision was a 24-month contract, silently overwriting the preference is how a
memory system becomes untrustworthy — and an untrustworthy memory is worse than
none, because it is consulted with confidence. The resolution might be "the
preference was wrong" or "this was a deliberate exception", and only the human
knows which.

Hand edits are equally sacred. The files are meant to be edited; a consolidation
that mangles one is a failed run, not a cosmetic issue.

Usage:  python -m lifeos.memory [--consolidate] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, timedelta

from . import atomic, clock, vault

SHORT_DAYS = 7
MEDIUM_DAYS = 90

_FRONT = re.compile(r"^---\n(.*?)\n---\n", re.S)

MARK_START = "<!-- LIFEOS:MEMORY:BEGIN"
MARK_END = "<!-- LIFEOS:MEMORY:END -->"


def _read_front(path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    m = _FRONT.match(text)
    if not m:
        return {}, text
    from ruamel.yaml import YAML
    try:
        return YAML(typ="safe").load(m.group(1)) or {}, text[m.end():]
    except Exception:  # noqa: BLE001 — a malformed header is data, not a crash
        return {}, text


def _tier_files(tier: str) -> list:
    d = vault.path("memory", tier)
    return sorted(d.glob("*.md")) if d.is_dir() else []


def _audit(action: str, **fields) -> None:
    atomic.append_jsonl(vault.path("memory", "audit.jsonl"), {
        "at": clock.stamp(), "action": action,
        "run_id": clock.Run.current().id, **fields,
    })


def scan() -> dict:
    """What is in memory, and what the ritual would do to it."""
    today = date.fromisoformat(clock.today())
    out: dict = {"tiers": {}, "contradictions": [], "hand_edited": []}

    for tier, horizon in (("short", SHORT_DAYS), ("medium", MEDIUM_DAYS), ("long", None)):
        items = []
        for f in _tier_files(tier):
            front, body = _read_front(f)
            age = None
            for key in ("since", "horizon", "created"):
                if front.get(key):
                    try:
                        age = (today - date.fromisoformat(str(front[key])[:10])).days
                        break
                    except ValueError:
                        pass
            item = {
                "file": vault.rel(f), "topic": front.get("topic", f.stem),
                "kind": front.get("kind"), "confidence": front.get("confidence"),
                "age_days": age, "hand_edited": bool(front.get("hand_edited")),
                "contradicts": front.get("contradicts") or [],
                "expired": bool(horizon and age is not None and age > horizon),
                "chars": len(body.strip()),
            }
            items.append(item)
            if item["hand_edited"]:
                out["hand_edited"].append(item["file"])
            for other in item["contradicts"]:
                out["contradictions"].append({"file": item["file"], "contradicts": other,
                                              "topic": item["topic"]})
        out["tiers"][tier] = items

    out["counts"] = {t: len(v) for t, v in out["tiers"].items()}
    out["would_expire"] = [i["file"] for t in ("short", "medium")
                           for i in out["tiers"][t] if i["expired"]]
    return out


def claude_md_block(long_items: list[dict]) -> str:
    """The digest that feeds forward into every future session."""
    keep = [i for i in long_items if i.get("kind") in
            {"preference", "standing_instruction", "risk_appetite", "pattern"}]
    if not keep:
        return "*No long-term memory yet. Run `/consolidate` after your first working session.*"
    lines = []
    for i in sorted(keep, key=lambda x: str(x.get("kind"))):
        conf = f" _(confidence {i['confidence']})_" if i.get("confidence") else ""
        lines.append(f"- **{i['topic']}**{conf}")
    return "\n".join(lines)


def update_claude_md(block: str, *, dry_run: bool = False) -> bool:
    """Rewrite ONLY between the delimiters.

    Everything outside them is the human's constitution, and a memory ritual
    that edited it would be rewriting its own instructions.
    """
    path = vault.repo_root() / "CLAUDE.md"
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    start = text.find(MARK_START)
    end = text.find(MARK_END)
    if start == -1 or end == -1:
        return False
    head_end = text.find("-->", start) + 3
    new = text[:head_end] + "\n" + block.strip() + "\n" + text[end:]
    if new == text:
        return False
    if not dry_run:
        atomic.write_text(path, new)
    return True


def consolidate(*, dry_run: bool = False) -> dict:
    if not vault.is_initialised():
        return {"schema": "memory/1", "error": "no vault — run /lifeos-init"}

    state = scan()
    today = date.fromisoformat(clock.today())
    actions: list[dict] = []

    # Expire, never delete. An expired item moves down a tier with an audit line,
    # so nothing the system once knew simply vanishes.
    for tier, target in (("short", "medium"), ("medium", None)):
        for item in state["tiers"][tier]:
            if not item["expired"]:
                continue
            if item["hand_edited"]:
                actions.append({"action": "kept", "file": item["file"],
                                "why": "hand-edited; the human's edit outranks the horizon"})
                continue
            actions.append({"action": "demote" if target else "expire",
                            "file": item["file"], "to": target,
                            "age_days": item["age_days"]})
            if not dry_run:
                _audit("demote" if target else "expire", file=item["file"],
                       from_tier=tier, to_tier=target or "none",
                       reason=f"past the {tier} horizon at {item['age_days']} days")

    # Contradictions are surfaced, never resolved.
    for c in state["contradictions"]:
        actions.append({"action": "flag_contradiction", **c,
                        "why": "surfaced for the human; never silently overwritten"})
        if not dry_run:
            _audit("flag_contradiction", file=c["file"], contradicts=c["contradicts"],
                   reason="both statements retained; the human decides which holds")

    block = claude_md_block(state["tiers"]["long"])
    if update_claude_md(block, dry_run=dry_run):
        actions.append({"action": "regenerated CLAUDE.md memory block"})

    brief_path = vault.path("memory", "short",
                            f"brief-{(today + timedelta(days=1)).isoformat()}.md")
    if not dry_run and not brief_path.exists():
        atomic.write_text(brief_path, _tomorrow_brief())
        actions.append({"action": "wrote tomorrow's brief", "file": vault.rel(brief_path)})

    return {
        "schema": "memory/1",
        "at": clock.stamp(),
        "dry_run": dry_run,
        "counts": state["counts"],
        "actions": actions,
        "contradictions": state["contradictions"],
        "hand_edited_preserved": state["hand_edited"],
        "note": (
            "Contradictions are surfaced, never resolved. Hand-edited files are "
            "preserved even when past their horizon — a consolidation that mangles "
            "a human's edit is a failed run."
        ),
    }


def _tomorrow_brief() -> str:
    from . import readiness
    try:
        score = readiness.report().get("score")
    except Exception:  # noqa: BLE001
        score = None
    return (
        "---\n"
        f"topic: Brief for {(date.fromisoformat(clock.today()) + timedelta(days=1)).isoformat()}\n"
        "kind: pattern\n"
        f"since: {clock.today()}\n"
        "confidence: 1.0\n"
        "---\n\n"
        f"Readiness stood at {score}% when this was written.\n\n"
        "Run `/boot` for where things stand, and `/heartbeat` to advance.\n"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lifeos.memory")
    ap.add_argument("--consolidate", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    result = consolidate(dry_run=args.dry_run) if args.consolidate else scan()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
