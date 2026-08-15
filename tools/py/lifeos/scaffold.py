"""SCAFFOLD — grow a new domain from the charter template. Backs /add-domain.

This is definition-of-done #5, and the acceptance test is specific: the next
`/heartbeat` must pick the new domain up with **zero changes to the
orchestrator**. If the orchestrator needed editing, the scaffolding is wrong —
fix the scaffolding, not the orchestrator.

What that requires, and what this module therefore produces:

  * an agent charter obeying the same seven-part contract as every other agent,
    so the dispatcher can route to it without special-casing
  * a ledger JSON Schema composing the shared envelope, so its records carry
    provenance and validate like everything else
  * a row in the ownership table, so /audit's one-writer check sees it
  * rows in the coverage map, so /audit's coverage check sees it
  * a state file, so /status and SENSE see it
  * the domain enabled in profile.yaml

Nothing here is special-cased anywhere else in the system. That is the point.

Usage:  python -m lifeos.scaffold <name> [--label "..."] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import re
import sys

from . import atomic, clock, vault

CHARTER = vault.repo_root() / "templates" / "AGENT_CHARTER.md"
CATALOGUE = vault.repo_root() / "docs" / "agent-catalogue.md"
COVERAGE = vault.repo_root() / "docs" / "coverage-map.md"


class ScaffoldError(RuntimeError):
    pass


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")


def _schema_for(domain: str, label: str) -> dict:
    """A ledger schema composing the shared envelope.

    Composing rather than copying is what makes the new domain's records carry
    provenance, deterministic ids and confidence without any of that being
    written again.
    """
    env = "https://lifeos.local/schemas/envelope.schema.json#/$defs"
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://lifeos.local/schemas/ledgers/{domain}.schema.json",
        "title": f"{domain}/1",
        "description": (
            f"{label}. Owner: {domain}. Scaffolded from templates/AGENT_CHARTER.md — "
            "extend the properties as the domain earns them."
        ),
        "allOf": [{"$ref": f"{env}/base"}],
        "properties": {
            "ref": {"type": "string", "minLength": 1,
                    "description": "Stable identity within this ledger."},
            "label": {"type": "string", "minLength": 1},
            "kind": {"type": "string"},
            "amount": {"$ref": f"{env}/money"},
            "occurred_on": {"$ref": f"{env}/date"},
            "notes": {"type": "string"},
            "doc_hash": {"$ref": f"{env}/hash"},
        },
        "required": ["ref", "label"],
        "unevaluatedProperties": False,
    }


def _charter_for(domain: str, label: str, owns: str) -> str:
    template = CHARTER.read_text(encoding="utf-8")
    body = template.split("---", 2)[-1]

    front = (
        "---\n"
        f"name: {domain}\n"
        f"description: Owns {label.lower()}. Scaffolded by /add-domain; the seven-part "
        "charter below is filled in as the domain earns depth. Dispatch here for "
        f"anything concerning {label.lower()}.\n"
        "tools: Read, Grep, Glob, Bash, Write\n"
        "model: inherit\n"
        "---\n"
    )
    filled = (
        body
        .replace("<agent-name>", domain)
        .replace("<the slice of life this agent is accountable for>", owns)
        .replace("<the adjacent things someone might assume — name them, with the agent that does own them>",
                 "TO FILL IN — name the adjacent domains and who owns them.")
        .replace("<types this agent understands>", "TO FILL IN")
        .replace("<ledgers owned by others that I read>", "TO FILL IN")
        .replace("<agents whose output I consume>", "TO FILL IN")
        .replace("`$VAULT/ledgers/<name>.jsonl`", f"`$VAULT/ledgers/{domain}.jsonl`")
        .replace("`templates/schemas/ledgers/<name>.schema.json`",
                 f"`templates/schemas/ledgers/{domain}.schema.json`")
        .replace("<agent-name>.json", f"{domain}.json")
        .replace("<hourly | daily | weekly | monthly | quarterly | annual | on request>",
                 "weekly")
        .replace("<signal kinds from SENSE that should pull this agent forward>",
                 "`inbox.new` for a document routed to this domain")
        .replace("<checkable condition>", "TO FILL IN")
    )
    return front + filled + (
        "\n---\n\n"
        f"## Scaffolded {clock.today()}\n\n"
        "This charter was generated from `templates/AGENT_CHARTER.md` by `/add-domain`. "
        "The sections marked **TO FILL IN** are the ones only a human can answer: what "
        "this domain does *not* own, and what \"done\" means for it.\n\n"
        "The domain is already live regardless — the orchestrator dispatches to it, "
        "`/status` reports it, `/audit` checks it, and its ledger validates — because "
        "nothing about it is special-cased anywhere in the system. That is the property "
        "worth protecting: fill these in, but do not add plumbing.\n"
    )


def _append_catalogue_row(domain: str, label: str, dry_run: bool) -> bool:
    """Add the ledger to the ownership table, so /audit's one-writer check sees it."""
    if not CATALOGUE.is_file():
        return False
    text = CATALOGUE.read_text(encoding="utf-8")
    row = f"| `{domain}.jsonl` | `{domain}` | all |"
    if row in text:
        return False
    anchor = "| `documents/index.jsonl` | `librarian` | all |"
    if anchor not in text:
        return False
    if not dry_run:
        atomic.write_text(CATALOGUE, text.replace(anchor, f"{row}\n{anchor}"))
    return True


def _append_coverage_rows(domain: str, label: str, dry_run: bool) -> bool:
    """Add coverage rows, so /audit's coverage check sees the new leaves."""
    if not COVERAGE.is_file():
        return False
    text = COVERAGE.read_text(encoding="utf-8")
    marker = f"## Z — {label} (scaffolded)"
    if marker in text:
        return False
    block = (
        f"\n{marker} → `{domain}`\n\n"
        "| # | Leaf | Kind | Ledger / schema | Readiness checklist | Phase |\n"
        "|---|---|---|---|---|---|\n"
        f"| Z1 | {label} — records | L | `{domain}.jsonl` | — | scaffolded |\n"
        f"| Z2 | {label} — review cadence | A | `{domain}.jsonl` | — | scaffolded |\n"
    )
    anchor = "\n---\n\n## Cross-cutting coverage"
    if anchor not in text:
        return False
    if not dry_run:
        atomic.write_text(COVERAGE, text.replace(anchor, block + anchor))
    return True


def add_domain(name: str, *, label: str | None = None, dry_run: bool = False) -> dict:
    domain = _slug(name)
    if not domain:
        raise ScaffoldError("domain name must contain letters or digits")
    label = label or name.replace("-", " ").title()
    owns = f"{label.lower()} — records, review cadence and reporting"

    agent_path = vault.repo_root() / ".claude" / "agents" / f"{domain}.md"
    schema_path = (vault.repo_root() / "templates" / "schemas" / "ledgers"
                   / f"{domain}.schema.json")
    state_path = vault.path("state", "agents", f"{domain}.json")

    if agent_path.exists():
        raise ScaffoldError(
            f"domain '{domain}' already exists ({vault.rel(agent_path)}). "
            "Scaffolding never clobbers."
        )

    actions = []
    if not dry_run:
        atomic.write_text(agent_path, _charter_for(domain, label, owns))
        atomic.write_json(schema_path, _schema_for(domain, label))
        atomic.write_json(state_path, {
            "schema": "agent-state/1", "agent": domain, "health": "never_run",
            "open_loops": [], "known_gaps": [], "pending_questions": [],
            "metrics": {"runs_total": 0, "failures_recent": 0, "ledgers_owned": 1},
        })
    actions += [f"agent .claude/agents/{domain}.md",
                f"schema templates/schemas/ledgers/{domain}.schema.json",
                f"state $VAULT/state/agents/{domain}.json"]

    if _append_catalogue_row(domain, label, dry_run):
        actions.append("ownership row in docs/agent-catalogue.md")
    if _append_coverage_rows(domain, label, dry_run):
        actions.append("coverage rows in docs/coverage-map.md")

    enabled = False
    profile_path = vault.path("profile", "profile.yaml")
    if profile_path.is_file():
        from ruamel.yaml import YAML
        y = YAML()
        y.preserve_quotes = True
        y.indent(mapping=2, sequence=4, offset=2)
        prof = y.load(profile_path.read_text(encoding="utf-8"))
        prof.setdefault("domains", {})
        if not prof["domains"].get(domain):
            prof["domains"][domain] = True
            enabled = True
            if not dry_run:
                import io
                buf = io.StringIO()
                y.dump(prof, buf)
                atomic.write_text(profile_path, buf.getvalue())
    if enabled:
        actions.append(f"enabled domain '{domain}' in profile.yaml")

    return {
        "schema": "scaffold/1",
        "domain": domain, "label": label, "dry_run": dry_run,
        "created": actions,
        "next": [
            f"Fill in the TO FILL IN sections of .claude/agents/{domain}.md",
            "Run /audit — the new domain is already covered by every check",
            "Run /heartbeat — it participates with NO changes to the orchestrator",
        ],
        "acceptance": (
            "Definition of done #5: the next /heartbeat picks this domain up with zero "
            "changes to the orchestrator. If the orchestrator needed editing, the "
            "scaffolding is wrong — fix the scaffolding, not the orchestrator."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lifeos.scaffold")
    ap.add_argument("name")
    ap.add_argument("--label")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    try:
        print(json.dumps(add_domain(args.name, label=args.label, dry_run=args.dry_run),
                         indent=2, ensure_ascii=False))
    except ScaffoldError as e:
        print(json.dumps({"error": str(e)}))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
