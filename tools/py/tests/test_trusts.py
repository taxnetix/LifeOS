"""The pack mechanism, and trust administration.

Two things are being proven here. First, that a pack merges rather than forks —
installs cleanly, twice safely, refuses collisions, and uninstalls exactly.
Second, that the trusts domain finds what a trustee cannot see from any single
document: s7C, independence, unauthorised distributions, and separation.
"""

from __future__ import annotations

import importlib
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
FIXTURES = REPO / "vault.example" / "inbox"


@pytest.fixture
def pack_repo(tmp_path, monkeypatch, vault_dir, frozen_clock):
    """A throwaway copy of the repo, so installing a pack cannot touch the real one."""
    if not FIXTURES.is_dir():
        pytest.skip("fixtures not generated")

    root = tmp_path / "repo"
    for rel in (".claude/rules", ".claude/agents", ".claude/commands",
                "packs", "templates/schemas"):
        (root / rel).mkdir(parents=True, exist_ok=True)
    shutil.copytree(REPO / ".claude" / "rules", root / ".claude" / "rules",
                    dirs_exist_ok=True)
    shutil.copytree(REPO / "packs", root / "packs", dirs_exist_ok=True)
    shutil.copytree(REPO / "templates" / "schemas", root / "templates" / "schemas",
                    dirs_exist_ok=True)

    # Remove anything a previous real install left in the copied rules, so the
    # test starts from a genuinely uninstalled state.
    # Use the shipped fence remover rather than hand-rolling it here: a
    # hand-rolled strip that leaves the surrounding newlines wrong produces
    # YAML that will not parse, and the test would then be exercising the
    # fixture's bug instead of the installer's behaviour.
    from lifeos import packs as _p
    for fname in ("document-types.yaml", "readiness-requirements.yaml", "cover-fields.yaml"):
        _p._remove_fenced(root / ".claude" / "rules" / fname, "trusts")
    for rel in ("agents/trusts.md", "commands/trust-review.md",
                "rules/za/s7c.yaml", "rules/za/trust-compliance.yaml"):
        f = root / ".claude" / rel
        if f.is_file():
            f.unlink()

    from lifeos import packs
    from lifeos import vault as vault_mod
    monkeypatch.setattr(vault_mod, "repo_root", lambda: root)
    importlib.reload(packs)
    monkeypatch.setattr(packs, "PACKS_DIR", root / "packs")
    monkeypatch.setattr(packs, "CLAUDE_DIR", root / ".claude")
    return root, packs


# ── the pack mechanism ───────────────────────────────────────────────────────


def test_pack_is_listed_before_it_is_installed(pack_repo):
    _, packs = pack_repo
    names = {p["name"]: p for p in packs.available()}
    assert "trusts" in names
    assert names["trusts"]["installed"] is False


def test_install_copies_files_and_appends_fenced_rules(pack_repo):
    root, packs = pack_repo
    r = packs.install("trusts")
    assert (root / ".claude" / "agents" / "trusts.md").is_file()
    assert (root / ".claude" / "commands" / "trust-review.md").is_file()
    assert (root / ".claude" / "rules" / "za" / "s7c.yaml").is_file()
    for fname in ("document-types.yaml", "cover-fields.yaml", "readiness-requirements.yaml"):
        text = (root / ".claude" / "rules" / fname).read_text()
        assert packs.FENCE_START.format(name="trusts") in text
    assert r["actions"]


def test_installing_twice_is_a_no_op(pack_repo):
    """A half-installed pack fails at classification time, not install time."""
    _, packs = pack_repo
    packs.install("trusts")
    again = packs.install("trusts")
    assert again["already_installed"] is True


def test_rules_still_parse_after_install(pack_repo):
    """Appending a duplicate YAML key produces a document that will not parse,
    and the failure lands on the next command rather than on the install."""
    from ruamel.yaml import YAML
    root, packs = pack_repo
    packs.install("trusts")
    for fname in ("document-types.yaml", "cover-fields.yaml", "readiness-requirements.yaml"):
        YAML(typ="safe").load((root / ".claude" / "rules" / fname).read_text())


def test_collision_is_refused_rather_than_half_installed(pack_repo):
    root, packs = pack_repo
    manifest = root / "packs" / "trusts" / "pack.yaml"
    manifest.write_text(manifest.read_text().replace(
        "document_types:\n  letters_of_authority:",
        "document_types:\n  will:\n    domain: trusts\n    strong: [x]\n"
        "    routes_to: trusts\n  letters_of_authority:",
    ))
    with pytest.raises(packs.PackError, match="already exists"):
        packs.install("trusts")
    assert not (root / ".claude" / "agents" / "trusts.md").is_file(), "nothing was written"


def test_uninstall_removes_exactly_what_was_added(pack_repo):
    root, packs = pack_repo
    before = {f.name: f.read_text()
              for f in (root / ".claude" / "rules").glob("*.yaml")}
    packs.install("trusts")
    packs.uninstall("trusts")
    assert not (root / ".claude" / "agents" / "trusts.md").is_file()
    for name, text in before.items():
        assert (root / ".claude" / "rules" / name).read_text().strip() == text.strip()


def test_uninstall_says_it_left_the_data_alone(pack_repo):
    """Removing a capability is not a decision that the data no longer matters."""
    _, packs = pack_repo
    packs.install("trusts")
    r = packs.uninstall("trusts")
    assert "ledger data untouched" in r["note"]


def test_pack_declares_only_files_it_ships(pack_repo):
    root, packs = pack_repo
    spec = packs.load_manifest("trusts")
    for kind, rels in (spec.get("provides") or {}).items():
        for rel in rels:
            assert (root / "packs" / "trusts" / kind / rel).is_file(), f"{kind}/{rel}"


# ── trust administration ─────────────────────────────────────────────────────


@pytest.fixture
def trust_vault(vault_dir, frozen_clock):
    import shutil as _sh
    if not FIXTURES.is_dir():
        pytest.skip("fixtures not generated")
    for f in FIXTURES.iterdir():
        if f.is_file() and f.name != "README.md":
            _sh.copy2(f, vault_dir / "inbox" / f.name)
    (vault_dir / "profile" / "profile.yaml").write_text(
        "schema: profile/1\njurisdiction: za\ncurrency: ZAR\n"
        "people:\n"
        "  - {ref: per_a_sample, name: A Sample, relation: self}\n"
        "  - {ref: per_m_sample, name: M Sample, relation: spouse}\n"
        "  - {ref: per_t_sample, name: T Sample, relation: child}\n"
        "entities:\n  - {ref: ent_trust, name: The Sample Family Trust, form: trust}\n"
        "domains: {trusts: true, readiness: true}\n"
    )
    from lifeos import classify, cover, ingest, ledger, readiness, rules, trusts
    for m in (readiness, classify, rules, ledger, ingest, cover, trusts):
        importlib.reload(m)
    for fn in (readiness.load_profile, classify.load_rules, cover.load_rules, rules.load):
        fn.cache_clear()
    ingest.sweep()
    cover.build()
    return vault_dir, trusts, ledger


def test_one_trust_from_two_documents(trust_vault):
    """The deed and the letters of authority evidence ONE trust. Keying on the
    document would double every count, calendar and s7C figure."""
    _, _, ledger = trust_vault
    rows = list(ledger.read("trusts"))
    assert len(rows) == 1
    t = rows[0]
    assert t["mt_number"] == "IT 4471/2019"
    assert t["type"] == "inter_vivos_discretionary"
    assert t["deed"] and t["loa"], "fields from both documents merged"


def test_year_end_is_normalised_for_the_calendar(trust_vault):
    """'28 February' must become '02-28' or every deadline is a year out."""
    _, _, ledger = trust_vault
    assert next(iter(ledger.read("trusts")))["year_end"] == "02-28"


def test_trustees_come_from_the_letters_of_authority(trust_vault):
    """The ledger must never claim a trustee the Master has not authorised."""
    _, _, ledger = trust_vault
    appointments = [t for t in ledger.read("trustees") if t["kind"] == "appointment"]
    assert {t["name"] for t in appointments} == {"A Sample", "M Sample"}


def test_s7c_is_computed_on_an_interest_free_loan(trust_vault):
    """The cost is invisible on the loan account until it is computed."""
    _, trusts, _ = trust_vault
    exposure = trusts.s7c_exposure()
    assert len(exposure) == 1
    e = exposure[0]
    assert e["balance_cents"] == 420000000
    assert e["actual_rate_pct"] == 0.0
    expected = int(e["balance_cents"] * e["official_rate_pct"] / 100)
    assert e["deemed_donation_cents"] == expected
    assert e["donations_tax_cents"] > 0


def test_s7c_applies_the_exemption_and_says_it_is_shared(trust_vault):
    _, trusts, _ = trust_vault
    rep = trusts.report()
    md = trusts.to_markdown(rep)
    assert "Less annual exemption" in md
    assert "shared across all donations" in md
    assert "by the lender, not the trust" in md


def test_a_market_rate_loan_creates_no_s7c_exposure(trust_vault, vault_dir):
    from lifeos import atomic
    _, trusts, ledger = trust_vault
    path = vault_dir / "ledgers" / "loan-accounts.jsonl"
    rows = list(atomic.read_jsonl(path))
    rows[0]["interest_rate_pct"] = 12.0
    path.write_text("".join(__import__("json").dumps(r) + "\n" for r in rows))
    assert trusts.s7c_exposure() == []


def test_absent_independent_trustee_is_flagged_with_the_consequence(trust_vault):
    _, trusts, _ = trust_vault
    t = next(iter(trusts.report()["trusts"]))
    ind = t["independence"]
    assert ind["applies"] is True
    assert ind["compliant"] is False
    assert ind["trustee_count"] == 2
    assert any(c["why"] == "is the founder" for c in ind["conflicted"])
    assert "alter ego" in ind["why_it_matters"]


def test_distributions_are_linked_to_their_resolution(trust_vault):
    """Without a dated resolution the conduit principle fails and the income is
    taxed in the trust at the flat rate."""
    _, trusts, ledger = trust_vault
    dists = list(ledger.read("distributions"))
    assert len(dists) == 2
    assert all(d["resolution_ref"] for d in dists)
    assert all(d["conduit"] for d in dists)
    assert {d["nature"] for d in dists} == {"income_rental", "income_interest"}
    assert trusts.report()["trusts"][0]["distributions"]["unauthorised"] == []


def test_separation_findings_are_raised(trust_vault):
    _, trusts, _ = trust_vault
    sep = trusts.report()["trusts"][0]["separation"]
    kinds = {f["kind"] for f in sep["findings"]}
    assert "no_trust_bank_account" in kinds


def test_compliance_dates_run_off_the_year_that_has_ended(trust_vault):
    """Statements are due for the year that ENDED, not the one still running.
    Using the next year end pushes an overdue AFS a full year out."""
    _, trusts, _ = trust_vault
    cal = trusts.report()["trusts"][0]["compliance"]
    afs = next(c for c in cal if c["kind"] == "afs")
    assert afs["due_on"] == "2026-08-28"
    assert afs["in_lead_window"] is True
    assert {c["kind"] for c in cal} >= {"afs", "it12tr", "irp6_1", "bo_register"}


def test_report_carries_the_unverified_caveat(trust_vault):
    _, trusts, _ = trust_vault
    md = trusts.to_markdown(trusts.report())
    assert "not been verified" in md
    assert "personal liability" in md
    assert "Master's Office" in md


def test_report_is_useful_when_there_are_no_trusts(vault_dir, frozen_clock):
    from lifeos import trusts
    importlib.reload(trusts)
    rep = trusts.report()
    assert rep["trusts"] == []
    assert "trust deed" in trusts.to_markdown(rep)
