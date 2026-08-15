"""Shared fixtures. Every test runs against a throwaway vault — never the real one."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def vault_dir(tmp_path, monkeypatch):
    """A scaffolded vault at a temp path, with $LIFEOS_VAULT pointed at it.

    Proves the resolver is honoured: if anything hardcoded a path, these tests
    would touch the real vault and this fixture would not isolate them.
    """
    root = tmp_path / "vault"
    monkeypatch.setenv("LIFEOS_VAULT", str(root))

    from lifeos import vault as vault_mod
    importlib.reload(vault_mod)

    from lifeos import init_vault
    importlib.reload(init_vault)
    init_vault.scaffold(root)

    yield root


@pytest.fixture
def frozen_clock(monkeypatch):
    """Deterministic time, so golden-file comparisons are meaningful."""
    monkeypatch.setenv("LIFEOS_NOW", "2026-08-15T09:00:00Z")
    monkeypatch.setenv("LIFEOS_RUN_ID", "run_test_0001")
    from lifeos import clock
    importlib.reload(clock)
    return clock
