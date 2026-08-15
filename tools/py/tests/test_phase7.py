"""Audit, self-extension, memory ritual and POPIA erasure."""

from __future__ import annotations

import importlib
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
FIXTURES = REPO / "vault.example" / "inbox"


@pytest.fixture
def full_vault(vault_dir, frozen_clock):
    if not FIXTURES.is_dir():
        pytest.skip("fixtures not generated")
    for f in FIXTURES.iterdir():
        if f.is_file() and f.name != "README.md":
            shutil.copy2(f, vault_dir / "inbox" / f.name)
    (vault_dir / "profile" / "profile.yaml").write_text(
        "schema: profile/1\njurisdiction: za\ncurrency: ZAR\n"
        "people:\n"
        "  - {ref: per_a_sample, name: A Sample, relation: self}\n"
        "  - {ref: per_m_sample, name: M Sample, relation: spouse}\n"
        "entities:\n  - {ref: ent_trust, name: The Sample Family Trust, form: trust}\n"
        "domains: {finance: true, estate: true, trusts: true, readiness: true}\n"
    )
    from lifeos import audit, classify, cover, finance, forget, ingest, ledger, memory, readiness, rules
    for m in (readiness, classify, rules, ledger, ingest, cover, finance, audit,
              memory, forget):
        importlib.reload(m)
    for fn in (readiness.load_profile, classify.load_rules, cover.load_rules, rules.load):
        fn.cache_clear()
    ingest.sweep()
    cover.build()
    finance.build()
    return vault_dir, audit, memory, forget, ledger


# ── audit ────────────────────────────────────────────────────────────────────


def test_every_record_carries_provenance(full_vault):
    _, audit, *_ = full_vault
    assert audit.check_provenance()["ok"]


def test_no_record_cites_a_document_that_does_not_exist(full_vault):
    _, audit, *_ = full_vault
    assert audit.check_orphans()["ok"]


def test_filed_originals_still_match_their_hash(full_vault):
    _, audit, *_ = full_vault
    r = audit.check_integrity()
    assert r["ok"] and r["checked"] > 0


def test_tampering_with_an_original_is_detected(full_vault, vault_dir):
    """An edit that slipped past the immutability hook must not go unnoticed."""
    _, audit, *_ = full_vault
    filed = next(p for p in (vault_dir / "documents").rglob("*.csv") if p.is_file())
    filed.chmod(0o644)
    filed.write_text(filed.read_text() + "\n2026-07-31;TAMPERED;-1.00;0.00\n")
    r = audit.check_integrity()
    assert not r["ok"]
    assert "no longer matches" in r["problems"][0]["problem"]


def test_an_orphaned_record_is_caught(full_vault, vault_dir):
    from lifeos import atomic
    _, audit, _, _, ledger = full_vault
    rec = next(iter(ledger.read("transactions")))
    rec = dict(rec)
    rec["id"] = "sha256:" + "f" * 64
    rec["source"] = {**rec["source"], "doc_hash": "sha256:" + "e" * 64}
    atomic.append_jsonl(vault_dir / "ledgers" / "transactions.jsonl", rec)
    assert not audit.check_orphans()["ok"]


def test_audit_exits_non_zero_on_failure(full_vault, vault_dir, capsys):
    from lifeos import atomic
    _, audit, _, _, ledger = full_vault
    rec = dict(next(iter(ledger.read("transactions"))))
    rec["id"] = "sha256:" + "d" * 64
    rec["source"] = {**rec["source"], "doc_hash": "sha256:" + "c" * 64}
    atomic.append_jsonl(vault_dir / "ledgers" / "transactions.jsonl", rec)
    assert audit.main([]) == 1


def test_trace_walks_a_figure_back_to_its_document(full_vault):
    _, audit, _, _, ledger = full_vault
    rec = next(iter(ledger.read("transactions")))
    t = audit.trace(rec["id"][:24])
    assert t["found"] and t["document"]["filed_path"]
    assert "=" in t["source"]["locator"]


def test_coverage_and_one_writer_hold(full_vault):
    _, audit, *_ = full_vault
    assert audit.check_coverage()["ok"]
    assert audit.check_one_writer()["ok"]


def test_the_system_repo_hardcodes_no_absolute_path(full_vault):
    _, audit, *_ = full_vault
    r = audit.check_no_absolute_paths()
    assert r["ok"], r["problems"][:3]


# ── self-extension ───────────────────────────────────────────────────────────


def test_scaffolding_produces_a_domain_the_system_already_understands(tmp_path,
                                                                     monkeypatch,
                                                                     vault_dir,
                                                                     frozen_clock):
    """Definition of done #5. The loop must need no changes."""
    root = tmp_path / "repo"
    for rel in (".claude/agents", "templates/schemas/ledgers", "docs", "templates"):
        (root / rel).mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO / "templates" / "AGENT_CHARTER.md", root / "templates")
    for name in ("agent-catalogue.md", "coverage-map.md"):
        shutil.copy2(REPO / "docs" / name, root / "docs")
    shutil.copytree(REPO / "templates" / "schemas", root / "templates" / "schemas",
                    dirs_exist_ok=True)

    from lifeos import scaffold
    from lifeos import vault as vm
    monkeypatch.setattr(vm, "repo_root", lambda: root)
    importlib.reload(scaffold)
    monkeypatch.setattr(scaffold, "CHARTER", root / "templates" / "AGENT_CHARTER.md")
    monkeypatch.setattr(scaffold, "CATALOGUE", root / "docs" / "agent-catalogue.md")
    monkeypatch.setattr(scaffold, "COVERAGE", root / "docs" / "coverage-map.md")

    r = scaffold.add_domain("beekeeping", label="Beekeeping and hives")
    agent = (root / ".claude" / "agents" / "beekeeping.md").read_text()
    assert "name: beekeeping" in agent
    assert "seven-part" in agent or "## 7." in agent

    import json as _j
    schema = _j.loads((root / "templates" / "schemas" / "ledgers"
                       / "beekeeping.schema.json").read_text())
    # Composing the envelope is what gives it provenance for free.
    assert schema["allOf"][0]["$ref"].endswith("envelope.schema.json#/$defs/base")
    assert "| `beekeeping.jsonl` | `beekeeping` |" in \
        (root / "docs" / "agent-catalogue.md").read_text()
    assert "zero changes to the orchestrator" in r["acceptance"]


def test_scaffolding_never_clobbers(tmp_path, monkeypatch, vault_dir, frozen_clock):
    root = tmp_path / "repo"
    (root / ".claude" / "agents").mkdir(parents=True)
    (root / ".claude" / "agents" / "taken.md").write_text("existing")
    from lifeos import scaffold
    from lifeos import vault as vm
    monkeypatch.setattr(vm, "repo_root", lambda: root)
    importlib.reload(scaffold)
    with pytest.raises(scaffold.ScaffoldError, match="already exists"):
        scaffold.add_domain("taken")


# ── memory ───────────────────────────────────────────────────────────────────


def test_contradictions_are_surfaced_never_resolved(full_vault, vault_dir):
    """An untrustworthy memory is worse than none: it is consulted confidently."""
    _, _, memory, _, _ = full_vault
    (vault_dir / "memory" / "long" / "lock-in.md").write_text(
        "---\ntopic: Rejects lock-in contracts\nkind: preference\n"
        "since: 2025-01-01\nconfidence: 0.9\ncontradicts: [fibre-contract]\n---\n\n"
        "Refuses anything with a lock-in period.\n"
    )
    r = memory.consolidate(dry_run=True)
    flags = [a for a in r["actions"] if a["action"] == "flag_contradiction"]
    assert flags
    assert "never silently overwritten" in flags[0]["why"]


def test_hand_edited_memory_outranks_the_horizon(full_vault, vault_dir):
    _, _, memory, _, _ = full_vault
    (vault_dir / "memory" / "short" / "note.md").write_text(
        "---\ntopic: Old note\nkind: pattern\nsince: 2020-01-01\n"
        "confidence: 1.0\nhand_edited: true\n---\n\nKeep me.\n"
    )
    r = memory.consolidate(dry_run=True)
    kept = [a for a in r["actions"] if a["action"] == "kept"]
    assert kept and "hand-edited" in kept[0]["why"]


def test_claude_md_is_rewritten_only_between_the_delimiters(full_vault):
    from lifeos import vault as vm
    _, _, memory, _, _ = full_vault
    path = vm.repo_root() / "CLAUDE.md"
    before = path.read_text()
    memory.update_claude_md("- **Test fact**", dry_run=True)
    assert path.read_text() == before, "dry run must not write"
    head = before[: before.index(memory.MARK_START)]
    assert "Non-negotiable rules" in head, "the constitution sits outside the markers"


# ── forget ───────────────────────────────────────────────────────────────────


def test_manifest_touches_nothing(full_vault, vault_dir):
    _, _, _, forget, _ = full_vault
    before = sorted(p.name for p in (vault_dir / "ledgers").glob("*.jsonl"))
    plan = forget.manifest("per_m_sample")
    assert plan["ledger_record_count"] > 0
    assert sorted(p.name for p in (vault_dir / "ledgers").glob("*.jsonl")) == before
    assert "Nothing has been touched" in plan["note"]


def test_manifest_includes_derived_artefacts(full_vault, vault_dir):
    """Removing a document while its numbers survive in a report is not erasure."""
    _, _, _, forget, _ = full_vault
    (vault_dir / "reports").mkdir(exist_ok=True)
    (vault_dir / "reports" / "demo.md").write_text("M Sample receives 60%.")
    plan = forget.manifest("per_m_sample")
    assert any("demo.md" in d for d in plan["derived_artefacts"])


def test_apply_quarantines_rather_than_shreds(full_vault, vault_dir):
    _, _, _, forget, _ = full_vault
    r = forget.apply("per_m_sample")
    assert r["removed"]["tombstoned"] > 0
    assert r["removed"]["quarantined"]
    assert not r["removed"]["shredded"]
    assert (vault_dir / "proposed" / "erasure" / "per_m_sample").is_dir()


def test_erasure_reports_what_it_cannot_remove(full_vault):
    """Honesty about the limits of erasure is part of the erasure."""
    _, _, _, forget, _ = full_vault
    r = forget.apply("per_m_sample")
    joined = " ".join(r["unremovable"]).lower()
    assert "github" in joined and "bank" in joined
    assert r["retained"]


def test_tombstones_keep_the_audit_trail(full_vault, vault_dir):
    from lifeos import atomic
    _, _, _, forget, _ = full_vault
    forget.apply("per_m_sample")
    rows = list(atomic.read_jsonl(vault_dir / "ledgers" / "policies.jsonl"))
    assert any(r.get("schema", "").endswith("/tombstone") for r in rows)
    audit_rows = list(atomic.read_jsonl(vault_dir / "state" / "audit.jsonl"))
    assert any(a.get("tool") == "forget" for a in audit_rows)
