# LifeOS — Dependencies

> Status: Phase 0 (design). Manifests are written; `.venv` and `node_modules/` are created in Phase 1.
> Split rationale: [ADR-0011](adr/0011-python-primary-thin-node.md). Why tools rather than skills: [ADR-0004](adr/0004-tools-compute-skills-judge.md).

Every dependency below is justified, attributed to the tool that imports it, and paired with what we would do without it. **A package nobody can justify gets removed** — that is the standard this file exists to enforce.

Neither language orchestrates. Both are invoked by agents as leaf tools, exit, and return JSON.

## 1. Detected environment

| | Found | Notes |
|---|---|---|
| Python | 3.13.12 (miniforge) | `.venv` at repo root |
| Node | 24.18.0, npm 11.16.0 | `engines` requires ≥ 20 |
| git | 2.50.1 | repo not yet initialised — Phase 1 |
| `gh` | 2.92.0, authed as `arneschreuder` | scopes: `gist, read:org, read:project, repo` |

## 2. Bootstrap (Phase 1)

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt && npm install
```

`.venv/`, `node_modules/` and `requirements.lock.txt` are git-ignored except the manifests and `package-lock.json`. Phase 1 freezes the resolved Python set into `requirements.lock.txt`; CI and `/selftest` install from the lockfiles, never from the floors.

## 3. Python — the data plane

Floors are minimum-compatible majors with an upper bound at the next major, so a breaking release cannot arrive silently.

### Runtime — `requirements.txt`

| Package | Why it is here | Imported by | Without it |
|---|---|---|---|
| `pdfplumber` | PDF text **and table** extraction with per-word bounding boxes — the bboxes are what let `source.locator` say `page=3;row=17` instead of just `page=3` | `tools/py/extract/pdf.py`, `tools/py/parsers/*` | `pdftotext -layout` (present on this machine) plus column heuristics — workable, materially worse on tables, and loses the locator precision [ADR-0014](adr/0014-provenance-and-confidence.md) depends on |
| `pypdf` | page splitting, metadata, and decryption of password-protected PDFs — banks routinely email these | `tools/py/ingest.py` | `qpdf` — **not installed on this machine**, so `pypdf` is what closes that gap |
| `pytesseract` | OCR for scanned documents: older policy schedules, title deeds, trust deeds | `tools/py/extract/ocr.py` | shelling out to `tesseract` directly; the wrapper adds confidence-per-word, which gates the write |
| `pillow` | image loading, deskew and threshold before OCR | `tools/py/extract/ocr.py` | none realistic; `pytesseract` needs it |
| `openpyxl` | `.xlsx`/`.xlsm` — broker and platform statements arrive as spreadsheets | `tools/py/extract/xlsx.py` | CSV export by hand, which breaks unattended ingestion |
| `python-docx` | `.docx` — wills, trust deeds, agreements | `tools/py/extract/docx.py` | unzip + XML parsing by hand |
| `pandas` | grouping, resampling, variance and trend over JSONL ledgers; the reason no SQLite read-model is needed [ADR-0009](adr/0009-no-sqlite-read-model.md) | `tools/py/analyse/*` | hand-rolled aggregation — slower to write, easier to get subtly wrong |
| `python-dateutil` | fiscal-calendar arithmetic (`relativedelta`), fuzzy date parsing from statement text | `tools/py/calendar_za.py`, parsers | `datetime` plus careful month-end handling; `relativedelta` is worth the dependency for "last day of February" alone |
| `rapidfuzz` | merchant and counterparty matching for dedupe and recurring-payment detection | `tools/py/enrich/categorise.py` | `difflib` — correct but far slower over a decade of transactions |
| `jsonschema` | validates every record against `templates/schemas/` **at write time**; a failing record never reaches a ledger | `tools/py/ledger.py` | hand-written validators that drift from the schemas |
| `pydantic` | typed record models, so parsers fail at the boundary rather than deep in analysis | `tools/py/models.py` | dataclasses plus manual coercion |
| `ruamel.yaml` | **round-trip** YAML — preserves your comments and ordering in `profile.yaml` | `tools/py/config.py` | `PyYAML` silently strips comments from a file the user hand-edits. Non-negotiable for a file the human owns |

### Development — `requirements-dev.txt`

| Package | Why | Without it |
|---|---|---|
| `pytest` | golden-file fixtures against `vault.example/`; every phase must leave it green | `unittest` — more ceremony, weaker fixtures |
| `pytest-cov` | coverage on the parsers, where an untested branch means a wrong number in a ledger | eyeballing |
| `ruff` | lint **and** format in one fast tool | `black` + `isort` + `flake8` — three tools, three configs |

## 4. Node — presentation and validation

| Package | Why | Used by | Without it |
|---|---|---|---|
| `ajv` | JSON Schema 2020-12 validation where **startup latency is felt** — the `PreToolUse` hook and `pre-commit`, which run constantly | `tools/js/validate-schema.mjs`, `.claude/hooks/` | Python `jsonschema`, paying interpreter startup on every tool call |
| `ajv-formats` | `date`, `date-time`, `uri`, `email` format assertions the schemas rely on | same | hand-written regex per format |
| `prettier` *(dev)* | deterministic formatting of generated HTML and JSON, so dashboards diff cleanly | `npm run format` | noisy diffs on every regeneration |
| `vitest` *(dev)* | tests for the renderer and validator | `npm test` | `node:test` — viable, weaker snapshot support for HTML output |

**No charting library, deliberately.** Dashboards are hand-generated inline SVG. That is what makes the brief's promise literally true: a self-contained HTML file with no build step, no CDN, and no network needed to read it — years from now, by someone who is not you.

## 5. External binaries

| Binary | Status | Needed for | If missing |
|---|---|---|---|
| `tesseract` | ✅ present | OCR of scanned documents | scanned docs land in `proposed/` with a gap record — degraded, not broken |
| `pdftotext` (poppler) | ✅ present | fallback text extraction | `pdfplumber` covers it |
| `git` | ✅ 2.50.1 | version control, pre-commit guard | the leak guard cannot run — blocking for Phase 1 |
| `gh` | ✅ 2.92.0 | system backlog, self-maintenance ([github.md](github.md)) | `/issues` degrades to local-only drafts; the loop is unaffected |
| `sqlite3` | ✅ present | unused by design | — |
| `qpdf` | ❌ **missing** | encrypted PDF repair | `pypdf` handles decryption; only exotic repair cases would need it. **Not a blocker.** Install with `brew install qpdf` if a bank statement ever defeats `pypdf` |

## 6. Two live findings

**1. `gh` token lacks project write scope.** Current scopes are `gist, read:org, read:project, repo`. `repo` covers issues, labels, milestones and pull requests — everything the design in [github.md](github.md) uses. `read:project` is read-only, so a GitHub Projects v2 board would fail to write. Phase tracking uses **milestones**, which work today. Only needed if you want a kanban board:

```bash
gh auth refresh -s project
```

**2. Python is miniforge, not a plain CPython.** `.venv` created from it works normally, but if conda environments are activated in this shell the venv must be activated *after* them or `pip` resolves against the wrong prefix. Phase 1's bootstrap uses explicit `.venv/bin/` paths throughout to sidestep this entirely.

## 7. Policy

- **Pin floors and ceilings.** No unbounded `>=`; a new major cannot arrive unannounced.
- **Lockfiles are authoritative.** `requirements.lock.txt` and `package-lock.json` are committed and are what CI installs.
- **Justify or remove.** A package without a row in this file fails review.
- **No runtime service.** Nothing here is a server, a daemon or an orchestrator — the brief's constraint §1, and the reason there is no web framework, no ORM and no task queue in either manifest.
- **Prefer the standard library.** Each row above had to beat "just write it" on correctness or on maintenance, not on convenience.
