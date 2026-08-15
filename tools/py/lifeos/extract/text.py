"""Plain text and markdown extraction.

Trivial, and still worth its own module: notes the user types by hand are a
legitimate document source, and they must carry provenance like everything
else. A hand-written note gets a locator and a confidence, so a figure taken
from it is visibly distinguishable from one read off a bank statement.
"""

from __future__ import annotations

from pathlib import Path

from . import Block, Extraction

_CONF = 1.0  # the file says exactly what it says; nothing is being inferred
_ENCODINGS = ("utf-8-sig", "utf-8", "cp1252", "latin-1")


def extract_text(path: Path, doc_hash: str) -> Extraction:
    text = None
    encoding = None
    for enc in _ENCODINGS:
        try:
            text = path.read_text(encoding=enc)
            encoding = enc
            break
        except UnicodeDecodeError:
            continue

    out = Extraction(
        doc_hash=doc_hash,
        method="text/markdown" if path.suffix.lower() == ".md" else "text",
        pages=1,
        meta={"encoding": encoding} if encoding else {},
    )
    if text is None:
        out.errors.append("could not decode file in any known encoding")
        return out

    n = 0
    current: list[str] = []
    for line in text.splitlines():
        if line.strip():
            current.append(line.rstrip())
        elif current:
            n += 1
            out.blocks.append(Block(locator=f"para={n}", text="\n".join(current), confidence=_CONF))
            current = []
    if current:
        n += 1
        out.blocks.append(Block(locator=f"para={n}", text="\n".join(current), confidence=_CONF))

    if not out.blocks:
        out.errors.append("file is empty")
    return out
