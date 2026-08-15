# ADR-0011 — Python primary, thin Node

**Status** Accepted · Phase 0

## Context

The brief permits Python and shell scripts as leaf tools invoked by agents — never as a runtime that orchestrates. The user additionally asked for both `requirements.txt` and `package.json`, a `.venv`, and documented dependencies.

Two languages in one repo is a real cost: two toolchains, two test runners, two dependency graphs, and the standing temptation to solve the same problem twice. It is worth paying only if each language has work the other does badly.

## Decision

**Python owns the data plane.** Extraction, parsing, normalisation, enrichment, analysis, tax mathematics, the deterministic SENSE script, and the GitHub sync. This is where the libraries are — `pdfplumber`, `pypdf`, `pytesseract`, `openpyxl`, `python-docx`, `pandas` — and where exact integer and decimal arithmetic is comfortable.

**Node owns the presentation and validation plane.** Dashboard HTML generation, and `ajv` JSON-Schema validation where it is called from hooks and `pre-commit`, because those run on every tool call and every commit and interpreter startup time is felt directly there.

**No overlap.** A capability lives in exactly one language. If both could do it, Python does it, unless it runs in a hook.

Dashboards use hand-generated inline SVG and no charting library, so the brief's promise of a self-contained HTML file with no build step and no CDN dependency is literally true rather than approximately true.

## Consequences

- `.venv` at the repo root, `requirements.txt` pinned, `node_modules/` from a pinned `package.json` and committed `package-lock.json`. Both git-ignored except the manifests and the lockfile.
- `docs/dependencies.md` records, for every package: why it is here, which tool imports it, and what the fallback would be without it. A dependency nobody can justify gets removed.
- Two test runners — `pytest` and `vitest` — both wired into `/selftest`.
- The split is defensible in review: nothing in `tools/js/` touches a ledger, and nothing in `tools/py/` renders a dashboard.
- The honest caveat: Python could do all of it. Node earns its place on hook startup latency and on templating ergonomics for HTML, and if that stops being true the right move is to delete it rather than find work for it.
- Neither language orchestrates. Both are invoked by agents, exit, and return JSON — the constraint the brief cares about.

## Alternatives considered

**Python only** — one toolchain, simpler, and genuinely viable. Rejected because the user asked for `package.json`, and because hook-path validation latency is a real consideration on every tool call.

**Even split, Node also owning ledger I/O and CLI plumbing** — two idioms for the same job, guaranteed drift, and two schema-validation implementations that will eventually disagree. Rejected.

**Node only** — the PDF, OCR and spreadsheet library ecosystem is materially weaker for this work. Rejected.
