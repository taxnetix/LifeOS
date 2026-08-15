"""Packs — optional domain bundles, installed by MERGE rather than by fork.

A pack is a directory obeying the same conventions as the core. Installing it
copies its agents, commands, rules and schemas into their counterpart
directories, appends its document types and readiness requirements to the
rulebooks, and enables its domains in profile.yaml.

Three properties this design exists to guarantee:

  * **Nothing in the core is edited.** Appends are fenced between markers, so an
    uninstall is exact and a core upgrade does not fight the pack.
  * **Installing twice is a no-op.** Idempotence matters more here than
    anywhere: a half-installed pack is worse than an uninstalled one.
  * **A pack never touches vault data.** It installs capability. The colleague
    who wants trust administration gets the machinery and none of anyone
    else's records.

Usage:  python -m lifeos.packs [list|install <name>|uninstall <name>|status]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from . import atomic, clock, vault

PACKS_DIR = vault.repo_root() / "packs"
CLAUDE_DIR = vault.repo_root() / ".claude"

# Appended content is fenced so uninstall can remove exactly what was added.
FENCE_START = "# >>> LIFEOS PACK: {name} >>>"
FENCE_END = "# <<< LIFEOS PACK: {name} <<<"


class PackError(RuntimeError):
    pass


def _yaml():
    from ruamel.yaml import YAML

    y = YAML()
    y.preserve_quotes = True
    y.indent(mapping=2, sequence=4, offset=2)
    return y


def available() -> list[dict]:
    out = []
    if not PACKS_DIR.is_dir():
        return out
    for d in sorted(PACKS_DIR.iterdir()):
        manifest = d / "pack.yaml"
        if not manifest.is_file():
            continue
        from ruamel.yaml import YAML
        spec = YAML(typ="safe").load(manifest.read_text(encoding="utf-8"))
        out.append({
            "name": spec["name"], "title": spec.get("title", spec["name"]),
            "version": spec.get("version"), "jurisdiction": spec.get("jurisdiction"),
            "description": (spec.get("description") or "").strip(),
            "installed": is_installed(spec["name"]),
            "path": str(d.relative_to(vault.repo_root())),
        })
    return out


def load_manifest(name: str) -> dict:
    manifest = PACKS_DIR / name / "pack.yaml"
    if not manifest.is_file():
        raise PackError(f"no pack '{name}' (looked in {vault.rel(manifest)})")
    from ruamel.yaml import YAML
    return YAML(typ="safe").load(manifest.read_text(encoding="utf-8"))


def _installed_marker() -> Path:
    return CLAUDE_DIR / "installed-packs.json"


def installed() -> dict:
    return atomic.read_json(_installed_marker(), {}) or {}


def is_installed(name: str) -> bool:
    return name in installed()


def _append_fenced(path: Path, name: str, block: str) -> bool:
    """Append a fenced block. Returns False if it is already there."""
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    start = FENCE_START.format(name=name)
    if start in text:
        return False
    end = FENCE_END.format(name=name)
    atomic.write_text(path, f"{text.rstrip()}\n\n{start}\n{block.rstrip()}\n{end}\n")
    return True


def _remove_fenced(path: Path, name: str) -> bool:
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    start, end = FENCE_START.format(name=name), FENCE_END.format(name=name)
    if start not in text or end not in text:
        return False
    head = text[: text.index(start)]
    tail = text[text.index(end) + len(end):]
    atomic.write_text(path, (head.rstrip() + "\n" + tail.lstrip("\n")).rstrip() + "\n")
    return True


def _sequence_indent(path: Path, key: str, default: int = 2) -> int:
    """How far the existing items under `key:` are indented.

    YAML allows a sequence at the same indent as its key OR indented under it,
    but the two cannot be mixed in one sequence. Matching what is already in the
    file is the only safe append.
    """
    if not path.is_file():
        return default
    seen_key = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if not seen_key:
            if line.rstrip().startswith(f"{key}:"):
                seen_key = True
            continue
        stripped = line.lstrip()
        if stripped.startswith("- "):
            return len(line) - len(stripped)
        if stripped and not stripped.startswith("#"):
            break
    return default


def _block(mapping: dict, indent: int = 2) -> str:
    """Render a mapping as YAML at a given indent, for appending under a key."""
    import io

    from ruamel.yaml import YAML
    buf = io.StringIO()
    YAML().dump(mapping, buf)
    pad = " " * indent
    return "\n".join(pad + line if line.strip() else line
                     for line in buf.getvalue().rstrip().splitlines())


def _existing_keys(path: Path, top_key: str | None = None) -> set[str]:
    """Top-level keys already present in a rulebook, for collision detection."""
    if not path.is_file():
        return set()
    from ruamel.yaml import YAML
    try:
        doc = YAML(typ="safe").load(path.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001 — a broken rulebook is a separate problem
        return set()
    node = doc.get(top_key, {}) if top_key else doc
    return set(node) if isinstance(node, dict) else set()


def _check_collisions(spec: dict, name: str) -> list[str]:
    """Keys the pack would append that already exist.

    Appending a duplicate YAML key does not merge — it produces a document that
    will not parse, and the failure lands on the NEXT command to read it rather
    than on the install. So this is checked up front and the install refuses,
    because a half-installed pack that breaks classification is much worse than
    one that never installed.
    """
    problems = []
    for section, path, top in (
        ("document_types", CLAUDE_DIR / "rules" / "document-types.yaml", "types"),
        ("cover_fields", CLAUDE_DIR / "rules" / "cover-fields.yaml", "types"),
    ):
        declared = set(spec.get(section) or {})
        existing = _existing_keys(path, top) | _existing_keys(path)
        for key in sorted(declared & existing):
            problems.append(
                f"{section}: '{key}' already exists in {path.name} — a pack must not "
                "redefine a key the core or another pack already provides"
            )

    # Readiness requirements are a LIST keyed by `id`, so a duplicate does not
    # break YAML — it silently produces two identical rows, double-counting the
    # requirement in the score and listing it twice in the shortest path.
    # Quieter than a parse error, and worse.
    req_path = CLAUDE_DIR / "rules" / "readiness-requirements.yaml"
    if req_path.is_file() and spec.get("readiness_requirements"):
        from ruamel.yaml import YAML
        try:
            doc = YAML(typ="safe").load(req_path.read_text(encoding="utf-8")) or {}
        except Exception:  # noqa: BLE001
            doc = {}
        existing_ids = {r.get("id") for r in (doc.get("requirements") or [])}
        for req in spec["readiness_requirements"]:
            if req.get("id") in existing_ids:
                problems.append(
                    f"readiness_requirements: id '{req['id']}' already exists in "
                    f"{req_path.name} — it would be scored twice"
                )
    return problems


def install(name: str, *, dry_run: bool = False) -> dict:
    spec = load_manifest(name)
    src = PACKS_DIR / name
    actions: list[str] = []
    skipped: list[str] = []

    # Idempotence is checked FIRST. On a second install the pack's own keys are
    # already present, so collision detection would otherwise report the pack
    # colliding with itself.
    if is_installed(name):
        return {"pack": name, "already_installed": True,
                "note": "Nothing to do. Installing twice is a no-op by design."}

    collisions = _check_collisions(spec, name)
    if collisions:
        raise PackError(
            f"pack '{name}' cannot be installed:\n  - " + "\n  - ".join(collisions)
        )

    # 1. Copy files into their counterpart directories.
    for kind, targets in (("agents", CLAUDE_DIR / "agents"),
                          ("commands", CLAUDE_DIR / "commands"),
                          ("rules", CLAUDE_DIR / "rules"),
                          ("schemas", vault.repo_root() / "templates" / "schemas")):
        for rel in (spec.get("provides") or {}).get(kind, []):
            source = src / kind / rel
            dest = targets / rel
            if not source.is_file():
                raise PackError(f"pack '{name}' declares {kind}/{rel} but it is missing")
            if dest.exists():
                # Refuse rather than clobber: a pack must never silently replace
                # a core file or another pack's file.
                skipped.append(f"{kind}/{rel} (already exists — not overwritten)")
                continue
            if not dry_run:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, dest)
            actions.append(f"copied {kind}/{rel}")

    # 2. Append document types.
    if spec.get("document_types"):
        path = CLAUDE_DIR / "rules" / "document-types.yaml"
        if not dry_run and _append_fenced(path, name, _block(spec["document_types"], 2)):
            actions.append("added document types")
        elif dry_run:
            actions.append("would add document types")

    # 3. Append field-extraction rules. A pack reads its own documents; the
    #    core knows nothing about trust deeds or any other pack's formats.
    if spec.get("cover_fields"):
        path = CLAUDE_DIR / "rules" / "cover-fields.yaml"
        if not dry_run and _append_fenced(path, name, _block(spec["cover_fields"], 2)):
            actions.append("added field-extraction rules")
        elif dry_run:
            actions.append("would add field-extraction rules")

    # 4. Append readiness requirements.
    #
    # The shipped file indents its sequence items under `requirements:` by two
    # spaces. Appending them at zero indent is not merely untidy — YAML reads it
    # as a NEW top-level sequence inside a mapping, and the whole document stops
    # parsing. The indent must match what is already there.
    if spec.get("readiness_requirements"):
        path = CLAUDE_DIR / "rules" / "readiness-requirements.yaml"
        indent = _sequence_indent(path, "requirements")
        if not dry_run and _append_fenced(
            path, name, _block(spec["readiness_requirements"], indent)
        ):
            actions.append("added readiness requirements")
        elif dry_run:
            actions.append("would add readiness requirements")

    # 5. Enable domains in the profile.
    enabled = []
    profile_path = vault.path("profile", "profile.yaml")
    if spec.get("enables_domains") and profile_path.is_file():
        y = _yaml()
        prof = y.load(profile_path.read_text(encoding="utf-8"))
        prof.setdefault("domains", {})
        for domain in spec["enables_domains"]:
            if not prof["domains"].get(domain):
                prof["domains"][domain] = True
                enabled.append(domain)
        packs_list = prof.setdefault("packs", [])
        if name not in packs_list:
            packs_list.append(name)
        if not dry_run and (enabled or name not in packs_list):
            import io
            buf = io.StringIO()
            y.dump(prof, buf)
            atomic.write_text(profile_path, buf.getvalue())
        if enabled:
            actions.append(f"enabled domains: {', '.join(enabled)}")

    if not dry_run:
        marker = installed()
        marker[name] = {"version": spec.get("version"), "installed_at": clock.stamp(),
                        "provides": spec.get("provides", {})}
        atomic.write_json(_installed_marker(), marker)

    return {
        "pack": name, "title": spec.get("title"), "version": spec.get("version"),
        "dry_run": dry_run, "actions": actions, "skipped": skipped,
        "domains_enabled": enabled,
        "next_steps": spec.get("next_steps", []),
    }


def uninstall(name: str, *, dry_run: bool = False) -> dict:
    spec = load_manifest(name)
    actions: list[str] = []

    if not is_installed(name):
        return {"pack": name, "installed": False, "note": "Not installed."}

    for kind, targets in (("agents", CLAUDE_DIR / "agents"),
                          ("commands", CLAUDE_DIR / "commands"),
                          ("rules", CLAUDE_DIR / "rules"),
                          ("schemas", vault.repo_root() / "templates" / "schemas")):
        for rel in (spec.get("provides") or {}).get(kind, []):
            dest = targets / rel
            if dest.is_file():
                if not dry_run:
                    dest.unlink()
                actions.append(f"removed {kind}/{rel}")

    for fname in ("document-types.yaml", "readiness-requirements.yaml",
                  "cover-fields.yaml"):
        path = CLAUDE_DIR / "rules" / fname
        if dry_run:
            if path.is_file() and FENCE_START.format(name=name) in path.read_text():
                actions.append(f"would clean {fname}")
        elif _remove_fenced(path, name):
            actions.append(f"cleaned {fname}")

    # Domains are left ENABLED on purpose: the ledgers may still hold records,
    # and disabling would make them silently vanish from reports rather than
    # showing as "not tracked". Removing capability is not the same as deciding
    # the data no longer matters.
    note = (
        "Domains were left enabled and ledger data untouched. Disable the domain "
        "in profile.yaml if you also want it excluded from reports — it will then "
        "show as 'not tracked' rather than disappearing."
    )

    if not dry_run:
        marker = installed()
        marker.pop(name, None)
        atomic.write_json(_installed_marker(), marker)

    return {"pack": name, "dry_run": dry_run, "actions": actions, "note": note}


def status() -> dict:
    return {
        "schema": "packs/1",
        "at": clock.stamp(),
        "available": available(),
        "installed": installed(),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lifeos.packs")
    ap.add_argument("action", nargs="?", default="status",
                    choices=["status", "list", "install", "uninstall"])
    ap.add_argument("name", nargs="?")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    try:
        if args.action in ("status", "list"):
            print(json.dumps(status(), indent=2, ensure_ascii=False))
        elif args.action == "install":
            if not args.name:
                raise PackError("install needs a pack name")
            print(json.dumps(install(args.name, dry_run=args.dry_run), indent=2,
                             ensure_ascii=False))
        else:
            if not args.name:
                raise PackError("uninstall needs a pack name")
            print(json.dumps(uninstall(args.name, dry_run=args.dry_run), indent=2,
                             ensure_ascii=False))
    except PackError as e:
        print(json.dumps({"error": str(e)}))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
