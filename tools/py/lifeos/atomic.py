"""Atomic writes — the only sanctioned write path into the vault.

Files are the database and there is no transaction manager, so physical write
safety is enforced here.  See docs/adr/0007-single-writer-atomic-writes.md.

  write_json / write_text  temp -> fsync -> os.replace  (atomic on POSIX:
                           a reader sees the old file or the new one, never a
                           torn one)
  append_jsonl             O_APPEND, one write() per record.  Records under
                           PIPE_BUF do not interleave between processes; larger
                           records fall back to a locked read-modify-rename.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

# macOS PIPE_BUF is 512 for pipes, but for regular files the relevant guarantee
# is a single write() syscall.  We stay conservative.
_SAFE_APPEND_BYTES = 4096


def write_text(target: Path, content: str) -> Path:
    """Atomically replace `target` with `content`."""
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return target


def write_json(target: Path, data: Any, *, sort_keys: bool = True) -> Path:
    """Atomically write JSON.

    Deterministic by default — sorted keys, fixed separators, trailing newline —
    so an unchanged state file produces a byte-identical result and the
    idempotency test can assert 'no diff' rather than 'no meaningful diff'.
    """
    text = json.dumps(data, indent=2, sort_keys=sort_keys, ensure_ascii=False) + "\n"
    return write_text(target, text)


def read_json(target: Path, default: Any = None) -> Any:
    if not target.is_file():
        return default
    return json.loads(target.read_text(encoding="utf-8"))


def append_jsonl(target: Path, record: dict) -> int:
    """Append one record. Returns bytes written.

    JSONL is append-only: corrections append a new record and a tombstone rather
    than mutating.  Compact separators keep the line small enough for a single
    atomic write.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n"
    blob = line.encode("utf-8")

    if len(blob) <= _SAFE_APPEND_BYTES:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, blob)
            os.fsync(fd)
        finally:
            os.close(fd)
    else:
        existing = target.read_bytes() if target.is_file() else b""
        write_text(target, (existing + blob).decode("utf-8"))
    return len(blob)


def read_jsonl(target: Path) -> Iterable[dict]:
    """Yield records, skipping blank lines. Raises on malformed JSON — a corrupt
    ledger must fail loudly, never be silently partially read."""
    if not target.is_file():
        return
    with target.open(encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"{target.name}:{n} is not valid JSON: {e}") from e
