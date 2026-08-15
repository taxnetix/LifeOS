"""Ingest idempotency, classification honesty, readiness weighting, Life File tiers."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from lifeos import atomic

FIXTURES = Path(__file__).resolve().parents[3] / "vault.example" / "inbox"


@pytest.fixture
def loaded(vault_dir, frozen_clock):
    """A temp vault with the fixture documents copied into its inbox."""
    if not FIXTURES.is_dir():
        pytest.skip("fixtures not generated")
    import shutil
    for f in FIXTURES.iterdir():
        if f.is_file() and f.name != "README.md":
            shutil.copy2(f, vault_dir / "inbox" / f.name)

    from lifeos import classify, ingest, life_file, readiness
    for m in (classify, readiness, ingest, life_file):
        importlib.reload(m)
    readiness.load_profile.cache_clear()

    # A profile with real subjects, or every person-scoped row is meaningless.
    (vault_dir / "profile" / "profile.yaml").write_text(
        "schema: profile/1\njurisdiction: za\ncurrency: ZAR\n"
        "people:\n"
        "  - {ref: per_a, name: A Sample, relation: self}\n"
        "  - {ref: per_m, name: M Sample, relation: spouse}\n"
        "  - {ref: per_t, name: T Sample, relation: child}\n"
        "entities:\n"
        "  - {ref: ent_trust, name: The Sample Family Trust, form: trust}\n"
        "domains: {identity: true, living: true, finance: true, insurance: true,\n"
        "  investments: true, assets: true, tax: true, estate: true, trusts: true,\n"
        "  final-wishes: true, readiness: true}\n"
    )
    readiness.load_profile.cache_clear()
    return vault_dir, ingest, readiness, life_file, classify


# ── classification ───────────────────────────────────────────────────────────


def test_classifier_refuses_to_guess_when_ambiguous(loaded):
    _, _, _, _, classify = loaded
    c = classify.classify("date amount balance policy premium insurer sum assured")
    assert c.type in {"unclassified", "policy_schedule", "transaction_export"}
    if c.type == "unclassified":
        assert "margin" in c.reason or "floor" in c.reason


def test_unknown_document_is_unclassified_not_forced(loaded):
    _, _, _, _, classify = loaded
    c = classify.classify("Just some notes I typed. Nothing structured here at all.")
    assert c.type == "unclassified"
    assert c.unseen is True


def test_period_detection_ignores_implausible_years(loaded):
    _, _, _, _, classify = loaded
    p = classify.detect_period("Statement 01 Jul 2026 to 31 Jul 2026, ref 99/99/1066")
    assert p == {"from": "2026-07-01", "to": "2026-07-31"}


# ── ingest ───────────────────────────────────────────────────────────────────


def test_sweep_files_and_routes_every_real_document(loaded):
    _, ingest, _, _, _ = loaded
    r = ingest.sweep()
    assert r["counts"].get("filed", 0) >= 5
    assert {"finance", "estate", "insurance", "investments"} <= set(r["routes"])


def test_second_sweep_files_nothing(loaded):
    """The identity check that makes /ingest idempotent."""
    _, ingest, _, _, _ = loaded
    first = ingest.sweep()
    second = ingest.sweep()
    assert second["counts"].get("filed", 0) == 0
    assert second["counts"].get("duplicate", 0) == first["counts"]["filed"]


def test_renamed_file_is_still_recognised_as_a_duplicate(loaded, vault_dir):
    """Identity is content, not filename."""
    _, ingest, _, _, _ = loaded
    ingest.sweep()
    src = next(f for f in (vault_dir / "inbox").glob("*.pdf"))
    copy = vault_dir / "inbox" / "totally-different-name.pdf"
    copy.write_bytes(src.read_bytes())
    r = ingest.sweep()
    assert r["counts"].get("filed", 0) == 0


def test_filed_originals_are_read_only(loaded, vault_dir):
    _, ingest, _, _, _ = loaded
    ingest.sweep()
    filed = [p for p in (vault_dir / "documents").rglob("*") if p.is_file()
             and p.suffix in {".pdf", ".docx", ".xlsx", ".csv", ".png"}]
    assert filed
    for p in filed:
        assert not (p.stat().st_mode & 0o222), f"{p.name} is writable; originals must be immutable"


def test_documents_are_filed_under_their_own_year_not_today(loaded, vault_dir):
    """A 2023 will ingested in 2026 belongs under 2023/."""
    _, ingest, _, _, _ = loaded
    ingest.sweep()
    paths = [str(p) for p in (vault_dir / "documents").rglob("*.docx")]
    assert any("/2023/" in p for p in paths), paths


def test_unclassifiable_file_stays_in_inbox_with_a_gap(loaded, vault_dir):
    _, ingest, _, _, _ = loaded
    (vault_dir / "inbox" / "mystery.txt").write_text("qqq zzz nothing recognisable")
    r = ingest.sweep()
    assert any(n["path"].endswith("mystery.txt") for n in r["needs_human"])
    assert (vault_dir / "inbox" / "mystery.txt").is_file(), "the system never deletes an inbox file"
    gaps = list(atomic.read_jsonl(vault_dir / "state" / "gaps.jsonl"))
    assert any("mystery.txt" in g.get("detail", "") for g in gaps)


def test_dry_run_files_nothing(loaded, vault_dir):
    _, ingest, _, _, _ = loaded
    r = ingest.sweep(dry_run=True)
    assert r["counts"].get("would_file", 0) > 0
    assert not list((vault_dir / "documents").rglob("*.pdf"))


def test_index_has_no_duplicate_hashes(loaded, vault_dir):
    _, ingest, _, _, _ = loaded
    ingest.sweep()
    ingest.sweep()
    rows = list(atomic.read_jsonl(vault_dir / "documents" / "index.jsonl"))
    hashes = [r["doc_hash"] for r in rows]
    assert len(hashes) == len(set(hashes))


# ── readiness ────────────────────────────────────────────────────────────────


def test_score_is_weighted_by_consequence_not_count(loaded):
    """Ten trivia must not outweigh one catastrophe."""
    _, _, readiness, _, _ = loaded
    score = readiness.evaluate()
    weights = {r.id: r.weight for r in score.rows}
    assert weights["G1b"] == readiness.CONSEQUENCE_WEIGHT["catastrophic"]
    assert weights["I2"] == readiness.CONSEQUENCE_WEIGHT["minor"]
    assert weights["G1b"] > weights["I2"] * 8


def test_a_minor_child_is_not_told_to_write_a_will(loaded):
    """Wrong advice costs trust faster than a missing feature does."""
    _, _, readiness, _, _ = loaded
    rows = readiness.evaluate().rows
    will_subjects = {r.subject_label for r in rows if r.id == "G1"}
    assert "T Sample" not in will_subjects
    assert {"A Sample", "M Sample"} <= will_subjects


def test_entity_requirements_respect_the_entity_form(loaded):
    _, _, readiness, _, _ = loaded
    rows = readiness.evaluate().rows
    trust_rows = [r for r in rows if r.id == "H1"]
    assert [r.subject_label for r in trust_rows] == ["The Sample Family Trust"]
    assert not [r for r in rows if r.id == "A23"], "no pty_ltd in this profile"


def test_filed_documents_lift_the_score(loaded):
    _, ingest, readiness, _, _ = loaded
    before = readiness.evaluate().percent
    ingest.sweep()
    importlib.reload(readiness)
    readiness.load_profile.cache_clear()
    after = readiness.evaluate().percent
    assert after > before


def test_person_scoped_document_is_unattributed_not_present(loaded):
    """A will exists, but LifeOS cannot yet prove whose it is."""
    _, ingest, readiness, _, _ = loaded
    ingest.sweep()
    importlib.reload(readiness)
    readiness.load_profile.cache_clear()
    rows = readiness.evaluate().rows
    g1 = [r for r in rows if r.id == "G1"]
    assert g1 and all(r.status == "unattributed" for r in g1)
    assert all(r.credit == r.weight * 0.5 for r in g1)


def test_disabled_domain_is_not_tracked_never_silently_dropped(loaded, vault_dir):
    _, _, readiness, _, _ = loaded
    p = vault_dir / "profile" / "profile.yaml"
    p.write_text(p.read_text().replace("trusts: true", "trusts: false"))
    readiness.load_profile.cache_clear()
    score = readiness.evaluate()
    assert any(n["id"] == "H1" for n in score.not_tracked)
    assert not any(r.id == "H1" for r in score.rows), "excluded from the score"


def test_shortest_path_groups_one_errand_into_one_action(loaded):
    """Three copies of the same action is a worse answer than one naming three people."""
    _, _, readiness, _, _ = loaded
    path = readiness.shortest_path(readiness.evaluate(), limit=5)
    assert len(path) == len({a["id"] for a in path})
    g1b = next((a for a in path if a["id"] == "G1b"), None)
    assert g1b and len(g1b["subjects"]) == 2


def test_shortest_path_prefers_cheap_catastrophic_over_expensive_severe(loaded):
    _, _, readiness, _, _ = loaded
    path = readiness.shortest_path(readiness.evaluate(), limit=10)
    assert path[0]["consequence"] == "catastrophic"
    assert path[0]["effort"] == "minutes"


def test_report_is_json_serialisable(loaded):
    _, _, readiness, _, _ = loaded
    json.dumps(readiness.report())


# ── Life File ────────────────────────────────────────────────────────────────


def _seed_policy(vault_dir):
    atomic.append_jsonl(vault_dir / "ledgers" / "policies.jsonl", {
        "id": "sha256:" + "c" * 64, "schema": "policies/1", "subject_id": "per_a",
        "source": {"doc_hash": "human", "locator": "l", "method": "human",
                   "confidence": 1.0, "extracted_at": "2026-08-15T09:00:00Z"},
        "valid_from": "2026-01-01", "valid_to": None, "superseded_by": None,
        "ref": "pol_life", "class": "life", "insurer": "Southern Mutual",
        "policy_no": "SM-4471902", "owner_ref": "per_a",
        "sum_assured": {"cents": 450000000, "currency": "ZAR"},
    })


@pytest.mark.parametrize("tier", [1, 2, 3])
def test_life_file_renders_at_every_tier(loaded, vault_dir, tier):
    _, ingest, _, life_file, _ = loaded
    ingest.sweep()
    r = life_file.generate(tier, html_only=True)
    assert r["tier"] == tier
    assert r["html"]
    assert (vault_dir / "reports" / "life-file").is_dir()


def test_tier1_shows_no_identifiers_and_withholds_the_executor_pack(loaded, vault_dir):
    _, _, _, life_file, _ = loaded
    _seed_policy(vault_dir)
    doc, _ = life_file.build_html(1)
    assert "SM-4471902" not in doc
    assert "Not in this copy" in doc


def test_tier2_masks_identifiers_to_the_last_four(loaded, vault_dir):
    _, _, _, life_file, _ = loaded
    _seed_policy(vault_dir)
    doc, _ = life_file.build_html(2)
    assert "SM-4471902" not in doc, "tier 2 must not print a full policy number"
    assert "1902" in doc, "tier 2 must show the last 4 so the executor can match it"


def test_tier3_shows_identifiers_in_full_and_is_sealed(loaded, vault_dir):
    _, _, _, life_file, _ = loaded
    _seed_policy(vault_dir)
    doc, _ = life_file.build_html(3)
    assert "SM-4471902" in doc
    assert "SEALED" in doc


def test_tier3_generation_is_audited(loaded, vault_dir):
    _, _, _, life_file, _ = loaded
    life_file.generate(3, html_only=True)
    audit = list(atomic.read_jsonl(vault_dir / "state" / "audit.jsonl"))
    assert any("TIER 3" in str(a.get("note", "")) for a in audit)


def test_secrets_are_never_printed_at_any_tier(loaded, vault_dir):
    """A document carrying both the map and the keys is a burglary aid."""
    atomic.append_jsonl(vault_dir / "ledgers" / "final-wishes.jsonl", {
        "id": "sha256:" + "d" * 64, "schema": "final-wishes/1", "subject_id": "per_a",
        "source": {"doc_hash": "human", "locator": "l", "method": "human",
                   "confidence": 1.0, "extracted_at": "2026-08-15T09:00:00Z"},
        "valid_from": "2026-01-01", "valid_to": None, "superseded_by": None,
        "person_ref": "per_a", "disposition": "burial",
        "ashes": "safe password is hunter2",
    })
    _, _, _, life_file, _ = loaded
    for tier in (1, 2, 3):
        doc, _ = life_file.build_html(tier)
        assert "hunter2" not in doc, f"tier {tier} leaked a secret"
        assert "REDACTED" in doc


def test_gaps_section_is_present_and_named_bluntly(loaded):
    _, _, _, life_file, _ = loaded
    doc, _ = life_file.build_html(1)
    assert "will <em>not</em> find" in doc
    assert "comfortable lie" in doc
    # It must sit near the front, not be buried in an appendix.
    assert doc.index("comfortable lie") < len(doc) // 2


def test_life_file_reports_the_score_it_was_built_from(loaded):
    _, _, readiness, life_file, _ = loaded
    r = life_file.generate(1, html_only=True)
    assert r["readiness_score"] == readiness.report()["score"]


def test_invalid_tier_is_refused(loaded):
    _, _, _, life_file, _ = loaded
    assert "error" in life_file.generate(4, html_only=True)
