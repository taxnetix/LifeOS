"""Vault path resolution — the ONLY code permitted to compute the vault root.

Resolution order:  $LIFEOS_VAULT  ->  <repo>/vault

Everything else in LifeOS addresses the vault through this module.  A grep for
absolute paths under /Users in the system repo must return nothing; /selftest
enforces that.  See docs/adr/0008-vault-location-and-separation.md.
"""

from __future__ import annotations

import os
from pathlib import Path

# The directory layout every vault has.  /lifeos-init creates exactly these.
SUBDIRS = (
    "profile",
    "inbox",
    "documents",
    "ledgers",
    "state",
    "state/agents",
    "state/system",
    "memory",
    "memory/short",
    "memory/medium",
    "memory/long",
    "reports",
    "proposed",
    "proposed/issues",
    "journal",
)


def repo_root() -> Path:
    """The system repo root — three levels up from tools/py/lifeos/."""
    return Path(__file__).resolve().parents[3]


def vault_root(*, must_exist: bool = False) -> Path:
    """Resolve the vault root.

    $LIFEOS_VAULT wins if set and non-empty, so relocating the vault out of the
    repo later costs one environment variable.
    """
    env = os.environ.get("LIFEOS_VAULT", "").strip()
    root = Path(env).expanduser().resolve() if env else repo_root() / "vault"
    if must_exist and not root.is_dir():
        raise VaultNotFound(root)
    return root


def path(*parts: str, must_exist: bool = False) -> Path:
    """Resolve a vault-relative path: path('ledgers', 'transactions.jsonl')."""
    p = vault_root().joinpath(*parts)
    if must_exist and not p.exists():
        raise FileNotFoundError(f"vault path does not exist: {rel(p)}")
    return p


def rel(p: Path | str) -> str:
    """Render a path vault-relative for display and logging.

    Absolute paths must never reach a journal entry, an audit line or an agent's
    output — they leak the username, and they are meaningless on another machine.
    """
    p = Path(p)
    try:
        inner = p.resolve().relative_to(vault_root())
        return "$VAULT" if str(inner) == "." else f"$VAULT/{inner}"
    except ValueError:
        try:
            return str(p.resolve().relative_to(repo_root()))
        except ValueError:
            return p.name


def is_initialised() -> bool:
    return (vault_root() / "profile" / "profile.yaml").is_file()


class VaultNotFound(RuntimeError):
    def __init__(self, root: Path) -> None:
        super().__init__(
            f"No vault at {root}.\n"
            "Run /lifeos-init to create one, or set $LIFEOS_VAULT to an existing vault."
        )
        self.root = root


if __name__ == "__main__":
    print(vault_root())
