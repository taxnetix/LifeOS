"""Vault resolution and the stable clock."""

from __future__ import annotations

import importlib


def test_env_var_overrides_default(monkeypatch, tmp_path):
    monkeypatch.setenv("LIFEOS_VAULT", str(tmp_path / "elsewhere"))
    from lifeos import vault
    importlib.reload(vault)
    assert vault.vault_root() == (tmp_path / "elsewhere").resolve()


def test_default_is_repo_vault_when_env_unset(monkeypatch):
    monkeypatch.delenv("LIFEOS_VAULT", raising=False)
    from lifeos import vault
    importlib.reload(vault)
    assert vault.vault_root() == vault.repo_root() / "vault"


def test_blank_env_var_falls_back(monkeypatch):
    """An exported-but-empty var is a common shell accident; it must not
    resolve the vault to the current directory."""
    monkeypatch.setenv("LIFEOS_VAULT", "   ")
    from lifeos import vault
    importlib.reload(vault)
    assert vault.vault_root() == vault.repo_root() / "vault"


def test_rel_renders_vault_relative_never_absolute(vault_dir):
    """An absolute path in a journal or audit line leaks the username and is
    meaningless on another machine."""
    from lifeos import vault
    assert vault.rel(vault_dir / "ledgers" / "people.jsonl") == "$VAULT/ledgers/people.jsonl"
    assert vault.rel(vault_dir) == "$VAULT"
    assert "/Users" not in vault.rel(vault_dir / "state" / "queue.json")


def test_is_initialised_tracks_the_profile(vault_dir):
    from lifeos import vault
    assert vault.is_initialised()
    (vault_dir / "profile" / "profile.yaml").unlink()
    assert not vault.is_initialised()


def test_clock_can_be_frozen_for_deterministic_tests(frozen_clock):
    assert frozen_clock.stamp() == "2026-08-15T09:00:00Z"
    assert frozen_clock.today() == "2026-08-15"   # 11:00 SAST, same date


def test_run_id_is_reused_within_one_heartbeat(frozen_clock):
    """Every tool invoked during one heartbeat must stamp the same run_id, or
    the audit trail cannot be reassembled."""
    assert frozen_clock.Run.current().id == "run_test_0001"


def test_new_runs_get_distinct_ids(monkeypatch):
    monkeypatch.delenv("LIFEOS_RUN_ID", raising=False)
    from lifeos import clock
    importlib.reload(clock)
    assert clock.Run.new().id != clock.Run.new().id
