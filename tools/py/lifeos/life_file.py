"""THE LIFE FILE — the document handed to family on death.

Three audience tiers (ADR-0018). The default is the one meant to be findable
and it carries no identifiers at all; the one that discloses everything must be
asked for explicitly, every time.

    1  First 48 Hours   whoever finds it     no identifiers
    2  Executor Pack    executor, attorney   masked to last 4
    3  Sealed Annexure  the executor, on death   unmasked, audited

No secrets at any tier — passwords, PINs, safe codes, seed phrases and keys are
never printed. LifeOS stores a pointer, and the pointer is what gets printed.

HTML is the source and is always written; the PDF is derived. If weasyprint
cannot load its system libraries the HTML still lands with instructions to
print it. The deliverable degrades; it never fails.

Usage:  python -m lifeos.life_file [--tier 1|2|3] [--html-only]
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from dataclasses import dataclass

from . import atomic, clock, readiness, vault

TIER_NAMES = {1: "First 48 Hours", 2: "Executor Pack", 3: "Sealed Annexure"}

# Anything matching these is never printed, at any tier. A document carrying
# both the map and the keys is a burglary aid.
_SECRET = re.compile(
    r"([Pp][Aa][Ss][Ss][Ww]([Oo][Rr])?[Dd]|[Pp][Ii][Nn]|[Ss][Ee][Cc][Rr][Ee][Tt]|"
    r"[Aa][Pp][Ii][ _-]?[Kk][Ee][Yy]|[Ss][Ee][Ee][Dd][ _-][Pp][Hh][Rr][Aa][Ss][Ee]"
    r") *([:=]|[ ][Ii][Ss][ ]) *[^ ]|BEGIN [A-Z ]*PRIVATE KEY"
)

_IDENTIFIER_KEYS = (
    "id_number", "tax_ref", "vat_no", "registration_no", "account_no",
    "policy_no", "member_no", "mt_number", "branch_code",
)


@dataclass
class Ctx:
    tier: int
    today: str
    profile: dict
    docs: list[dict]
    report: dict

    @property
    def tier_name(self) -> str:
        return TIER_NAMES[self.tier]


# ── masking ──────────────────────────────────────────────────────────────────


def mask(value: str | None, tier: int) -> str:
    """Tier 1 shows nothing, tier 2 shows the last 4, tier 3 shows all."""
    if not value:
        return "—"
    s = str(value)
    if tier >= 3:
        return s
    if tier == 1:
        return "[not shown in this copy]"
    digits = re.sub(r"\D", "", s)
    return f"···· {digits[-4:]}" if len(digits) >= 4 else "····"


def scrub(text: str) -> str:
    """Last line of defence: never print anything shaped like a secret."""
    if not text:
        return ""
    return "[REDACTED — a secret must never appear in this document]" if _SECRET.search(text) else text


def e(v) -> str:
    return html.escape(str(v)) if v is not None else "—"


# ── data gathering ───────────────────────────────────────────────────────────


def _ledger(name: str) -> list[dict]:
    return [r for r in atomic.read_jsonl(vault.path("ledgers", f"{name}.jsonl"))
            if not r.get("superseded_by")]


def _people(ctx: Ctx) -> list[dict]:
    return ctx.profile.get("people") or []


def _rows(items: list[tuple[str, str]]) -> str:
    return "".join(f"<tr><th>{e(k)}</th><td>{v}</td></tr>" for k, v in items)


def _empty(what: str, who: str = "") -> str:
    return (
        f'<p class="missing"><strong>Not recorded.</strong> {e(what)}'
        + (f' {e(who)}' if who else "")
        + "</p>"
    )


# ── sections ─────────────────────────────────────────────────────────────────


def s_cover(ctx: Ctx) -> str:
    self_person = next((p for p in _people(ctx) if p.get("relation") == "self"), None)
    who = self_person.get("name") if self_person else "(no owner recorded in profile)"
    score = ctx.report.get("score", 0)
    band = "good" if score >= 75 else ("mid" if score >= 40 else "poor")
    seal = ('<div class="seal">SEALED — CONTAINS FULL IDENTIFIERS</div>'
            if ctx.tier == 3 else "")
    return f"""
<section class="cover">
  {seal}
  <div class="kicker">Life File · Tier {ctx.tier} · {e(ctx.tier_name)}</div>
  <h1>{e(who)}</h1>
  <p class="lede">Everything my family needs if I die.</p>
  <div class="scorebox {band}">
    <div class="num">{score}%</div>
    <div class="lbl">readiness</div>
  </div>
  <table class="meta">
    {_rows([
        ("Generated", ctx.today),
        ("Tier", f"{ctx.tier} — {e(ctx.tier_name)}"),
        ("Identifiers", {1: "none shown", 2: "masked to last 4 digits",
                         3: "shown in full"}[ctx.tier]),
        ("Secrets", "never — passwords, PINs and codes are not in this document"),
    ])}
  </table>
  <p class="supersede">This copy supersedes all earlier copies.
     Regenerate quarterly and after any major life event.</p>
</section>"""


def s_first_48(ctx: Ctx) -> str:
    """Who to call, in order. The page someone reads while in shock."""
    people = _people(ctx)
    spouse = [p for p in people if p.get("relation") == "spouse"]
    wills = _ledger("wills")
    executor = next((w.get("executor", {}).get("name") for w in wills
                     if w.get("executor")), None)

    calls: list[tuple[str, str]] = []
    for p in spouse:
        calls.append(("Spouse", e(p.get("name"))))
    if executor:
        calls.append(("Executor", e(executor)))
    else:
        calls.append(("Executor", '<span class="missing-inline">not recorded — '
                                  'see the gaps section</span>'))
    funeral = [p for p in _ledger("policies") if p.get("class") == "funeral"]
    calls.append(("Funeral cover", e(funeral[0].get("insurer")) if funeral
                  else '<span class="missing-inline">not recorded</span>'))

    return f"""
<section>
  <h2>1 · In the first 48 hours</h2>
  <p>Call these people, in this order.</p>
  <table class="kv">{_rows(calls)}</table>
  <div class="callout">
    <strong>Before anything else:</strong> do not cancel debit orders or close
    accounts. An estate is frozen at death, and the executor needs the account
    history intact. Get at least ten certified copies of the death certificate —
    every institution will want one.
  </div>
</section>"""


def s_gaps(ctx: Ctx) -> str:
    """The headline section. Deliberately early, deliberately blunt."""
    rep = ctx.report
    cat = rep.get("catastrophic_gaps", [])
    path = rep.get("shortest_path", [])

    if not cat and not path:
        body = "<p>Nothing outstanding. Every checked requirement is on file.</p>"
    else:
        items = "".join(
            f"<li><strong>{e(g['requirement'])}</strong>"
            f"{' — ' + e(g['subject_label']) if g['subject_label'] != 'Household' else ''}"
            f"<br><span class=\"det\">{e(g['detail'])}</span>"
            f"{'<br><span class=det>' + e(g['note']) + '</span>' if g.get('note') else ''}</li>"
            for g in cat
        )
        fix = "".join(
            f"<li><strong>{e(a['action'])}</strong> — {e(a['effort'])}, "
            f"recovers {a['score_gain']}% "
            f"<span class=\"det\">({e(', '.join(a['subjects']))})</span></li>"
            for a in path
        )
        body = (
            (f"<h3>Highest consequence, missing</h3><ul class=\"gaps\">{items}</ul>" if cat else "")
            + (f"<h3>Shortest path to fixing it</h3><ol class=\"fix\">{fix}</ol>" if fix else "")
        )

    return f"""
<section class="pagebreak">
  <h2>2 · What my family will <em>not</em> find</h2>
  <p class="lede-sm">This is the most important page in this document. A Life File
     that showed only what is known would be a comfortable lie.</p>
  {body}
</section>"""


def s_wishes(ctx: Ctx) -> str:
    wishes = _ledger("final-wishes")
    if not wishes:
        return f"""<section><h2>3 · Funeral and final wishes</h2>
        {_empty('No burial, cremation or service preferences have been recorded.',
                'The family will have to guess, usually within 48 hours.')}</section>"""
    blocks = []
    for w in wishes:
        plot = w.get("plot") or {}
        blocks.append(f"""<h3>{e(w.get('person_ref'))}</h3>
        <table class="kv">{_rows([
            ("Burial or cremation", e(w.get("disposition"))),
            ("Plot", e(f"{plot.get('cemetery','')} {plot.get('section','')} {plot.get('number','')}".strip()) or "—"),
            ("Ashes", e(scrub(w.get("ashes", "")))),
            ("Service", e(scrub(str((w.get("service") or {}).get("notes", ""))))),
        ])}</table>""")
    return f"<section><h2>3 · Funeral and final wishes</h2>{''.join(blocks)}</section>"


def s_will(ctx: Ctx) -> str:
    wills = _ledger("wills")
    if not wills:
        return f"""<section><h2>4 · The will</h2>
        {_empty('No will has been recorded in LifeOS.',
                'If one exists, its location is not written down anywhere the family can reach.')}
        </section>"""
    rows = []
    for w in wills:
        ex = w.get("executor") or {}
        cu = w.get("custodian") or {}
        rows.append(("Type", e(w.get("kind"))))
        rows.append(("Signed", "yes" if w.get("signed") else
                     '<span class="missing-inline">NOT SIGNED — this is critical</span>'))
        rows.append(("Signed on", e(w.get("signed_on"))))
        rows.append(("Executor", e(ex.get("name"))))
        rows.append(("Custodian", e(cu.get("name"))))
        rows.append(("Original kept at", e(w.get("original_location"))))
    return f'<section><h2>4 · The will</h2><table class="kv">{_rows(rows)}</table></section>'


def s_liquidity(ctx: Ctx) -> str:
    wishes = _ledger("final-wishes")
    plan = next((w.get("thirty_day_liquidity") for w in wishes
                 if w.get("thirty_day_liquidity")), None)
    if not plan:
        return f"""<section><h2>5 · Money in the first 30 days</h2>
        {_empty('No thirty-day liquidity plan exists.',
                'An estate is frozen at death. Without reachable cash the family cannot '
                'pay for the funeral, the bond or the groceries — however solvent the '
                'estate looks on paper.')}</section>"""
    amt = plan.get("amount", {})
    src = "".join(
        f"<tr><td>{e(s['description'])}</td><td class='n'>R {s['amount']['cents']/100:,.2f}</td>"
        f"<td class='n'>{e(s['days_to_access'])} days</td></tr>"
        for s in plan.get("sources", [])
    )
    return f"""<section><h2>5 · Money in the first 30 days</h2>
    <p class="big">R {amt.get('cents', 0)/100:,.2f} reachable</p>
    <table class="tbl"><tr><th>Source</th><th class="n">Amount</th><th class="n">Available in</th></tr>
    {src}</table></section>"""


def s_documents(ctx: Ctx) -> str:
    if not ctx.docs:
        return f"<section><h2>6 · Where the documents are</h2>{_empty('No documents have been filed yet.')}</section>"
    by_domain: dict[str, list[dict]] = {}
    for d in ctx.docs:
        by_domain.setdefault(d.get("domain", "other"), []).append(d)
    blocks = []
    for domain in sorted(by_domain):
        rows = "".join(
            f"<tr><td>{e(d.get('type','').replace('_',' '))}</td>"
            f"<td>{e((d.get('period') or {}).get('to') or d.get('ingested_at','')[:10])}</td>"
            f"<td class='mono'>{e(d.get('filed_path'))}</td></tr>"
            for d in sorted(by_domain[domain], key=lambda x: x.get("type", ""))
        )
        blocks.append(f"<h3>{e(domain)}</h3><table class='tbl'>"
                      f"<tr><th>Document</th><th>Dated</th><th>Filed as</th></tr>{rows}</table>")
    return f"""<section class="pagebreak"><h2>6 · Where the documents are</h2>
    <p>Digital copies live in the LifeOS vault at the paths below. Ask the executor
       for access. <strong>Physical originals are elsewhere</strong> — where they are
       kept is recorded per document, and any blanks appear in the gaps section.</p>
    {''.join(blocks)}</section>"""


def s_tier2(ctx: Ctx) -> str:
    """Everything an executor needs to actually administer the estate."""
    if ctx.tier < 2:
        return """
<section class="pagebreak">
  <h2>7 · Policies, accounts and assets</h2>
  <div class="callout">
    <strong>Not in this copy.</strong> Policy numbers, bank accounts, investments,
    assets, liabilities and the trust register are in the <strong>Executor Pack
    (tier 2)</strong>. Ask the executor for it.
  </div>
</section>"""

    def table(title: str, ledger: str, cols: list[tuple[str, str]], empty: str) -> str:
        rows = _ledger(ledger)
        if not rows:
            return f"<h3>{e(title)}</h3>{_empty(empty)}"
        head = "".join(f"<th>{e(c[0])}</th>" for c in cols)
        body = ""
        for r in rows:
            cells = ""
            for _, key in cols:
                val = r.get(key)
                if isinstance(val, dict) and "cents" in val:
                    val = f"R {val['cents']/100:,.2f}"
                elif key in _IDENTIFIER_KEYS:
                    val = mask(val, ctx.tier)
                cells += f"<td>{e(scrub(str(val)) if val is not None else '—')}</td>"
            body += f"<tr>{cells}</tr>"
        return f"<h3>{e(title)}</h3><table class='tbl'><tr>{head}</tr>{body}</table>"

    return f"""
<section class="pagebreak">
  <h2>7 · Policies, accounts and assets</h2>
  {table("Insurance policies to claim", "policies",
         [("Insurer", "insurer"), ("Type", "class"), ("Policy no.", "policy_no"),
          ("Sum assured", "sum_assured")],
         "No insurance policies are recorded.")}
  {table("Bank accounts", "accounts",
         [("Bank", "bank"), ("Type", "kind"), ("Account no.", "account_no")],
         "No bank accounts are recorded.")}
  {table("Investments", "holdings",
         [("Platform", "platform"), ("Type", "kind"), ("Account no.", "account_no"),
          ("Value", "value")],
         "No investments are recorded.")}
  {table("Assets", "assets",
         [("Description", "description"), ("Class", "class"),
          ("Title deed kept at", "title_deed_location")],
         "No assets are recorded.")}
  {table("Debts and suretyships", "liabilities",
         [("Creditor", "creditor"), ("Type", "kind"), ("Account no.", "account_no"),
          ("Balance", "balance")],
         "No debts are recorded — including suretyships, which are the most "
         "commonly forgotten and most damaging item at death.")}
  {table("Trusts", "trusts",
         [("Name", "name"), ("Type", "type"), ("Master's ref", "mt_number")],
         "No trusts are recorded.")}
  {table("Digital estate", "digital-estate",
         [("Service", "service"), ("Username", "username"),
          ("Credentials kept at", "credential_pointer")],
         "No digital accounts are recorded. Email, banking and photo archives "
         "may be unreachable.")}
</section>"""


def s_notify(ctx: Ctx) -> str:
    people = [p for p in _people(ctx)]
    if not people:
        return ""
    rows = "".join(
        f"<tr><td>{e(p.get('name'))}</td><td>{e(p.get('relation'))}</td></tr>"
        for p in people
    )
    return f"""<section><h2>8 · People in the profile</h2>
    <table class="tbl"><tr><th>Name</th><th>Relationship</th></tr>{rows}</table>
    <p class="det">A full notification list with contact details is a separate
       readiness item; if it is missing it appears in the gaps section.</p></section>"""


def s_footer(ctx: Ctx) -> str:
    return f"""<section class="footer">
  <h2>About this document</h2>
  <p>Produced by LifeOS on {ctx.today} from filed source documents. Every figure
     traces to a document in the vault; anything LifeOS could not verify is listed
     as a gap rather than guessed.</p>
  <p><strong>This is not professional advice.</strong> It is preparation for a
     sharper conversation with a registered financial advisor, tax practitioner,
     attorney or the Master's Office.</p>
  <p><strong>Keep this copy where it belongs.</strong>
     Tier 1 with the will and with the executor · Tier 2 with the executor and the
     attorney · Tier 3 sealed, one copy, executor only.</p>
</section>"""


CSS = """
@page { size: A4; margin: 18mm 16mm 20mm; @bottom-center {
  content: "Life File — page " counter(page) " of " counter(pages);
  font: 8pt Helvetica, sans-serif; color: #888; } }
* { box-sizing: border-box; }
body { font: 10.5pt/1.5 Helvetica, Arial, sans-serif; color: #1a1a1a; margin: 0; }
h1 { font-size: 26pt; margin: 2mm 0 1mm; letter-spacing: -0.4pt; }
h2 { font-size: 14pt; margin: 8mm 0 3mm; padding-bottom: 1.5mm;
     border-bottom: 2px solid #1a1a1a; }
h3 { font-size: 11pt; margin: 5mm 0 2mm; color: #333; }
p { margin: 0 0 2.5mm; }
section.pagebreak { break-before: page; }
.cover { border-bottom: 3px solid #1a1a1a; padding-bottom: 6mm; margin-bottom: 4mm; }
.kicker { font-size: 8.5pt; letter-spacing: 1.4pt; text-transform: uppercase; color: #777; }
.lede { font-size: 12pt; color: #444; margin-bottom: 4mm; }
.lede-sm { font-size: 10pt; color: #555; font-style: italic; }
.scorebox { display: inline-block; padding: 3mm 6mm; border-radius: 2mm;
            margin: 2mm 0 4mm; border: 1.5px solid; }
.scorebox .num { font-size: 22pt; font-weight: bold; line-height: 1; }
.scorebox .lbl { font-size: 8pt; letter-spacing: 1pt; text-transform: uppercase; }
.scorebox.good { border-color: #1a7f37; color: #1a7f37; background: #f0f9f2; }
.scorebox.mid  { border-color: #9a6700; color: #9a6700; background: #fdf8ee; }
.scorebox.poor { border-color: #a40e26; color: #a40e26; background: #fdf0f2; }
.seal { background: #a40e26; color: #fff; padding: 2mm 4mm; font-weight: bold;
        letter-spacing: 1.5pt; font-size: 9pt; margin-bottom: 4mm; }
table { border-collapse: collapse; width: 100%; margin: 2mm 0 3mm; }
table.meta th, table.kv th { text-align: left; width: 42%; color: #666;
        font-weight: normal; padding: 1.2mm 4mm 1.2mm 0; vertical-align: top; }
table.meta td, table.kv td { padding: 1.2mm 0; vertical-align: top; }
table.tbl th { text-align: left; font-size: 8.5pt; text-transform: uppercase;
        letter-spacing: 0.5pt; color: #666; border-bottom: 1px solid #999;
        padding: 1.5mm 3mm 1.5mm 0; }
table.tbl td { padding: 1.5mm 3mm 1.5mm 0; border-bottom: 0.4px solid #e0e0e0;
        vertical-align: top; }
td.n, th.n { text-align: right; }
.mono { font-family: "SF Mono", Menlo, monospace; font-size: 8pt; color: #555;
        word-break: break-all; }
.missing { background: #fdf0f2; border-left: 3px solid #a40e26;
           padding: 2.5mm 4mm; margin: 2mm 0 3mm; }
.missing-inline { color: #a40e26; font-weight: bold; }
.callout { background: #f4f6f8; border-left: 3px solid #555; padding: 3mm 4mm;
           margin: 3mm 0; font-size: 10pt; }
ul.gaps { padding-left: 5mm; } ul.gaps li { margin-bottom: 2.5mm; }
ol.fix { padding-left: 5mm; } ol.fix li { margin-bottom: 1.5mm; }
.det { color: #666; font-size: 9pt; }
.big { font-size: 20pt; font-weight: bold; color: #1a7f37; margin: 2mm 0; }
.supersede { font-size: 9pt; color: #777; font-style: italic; }
.footer { break-before: page; }
.footer p { font-size: 9.5pt; color: #444; }
"""


def build_html(tier: int) -> tuple[str, dict]:
    profile = readiness.load_profile()
    rep = readiness.report()
    ctx = Ctx(
        tier=tier,
        today=clock.today(),
        profile=profile,
        docs=list(atomic.read_jsonl(vault.path("documents", "index.jsonl"))),
        report=rep,
    )
    sections = [
        s_cover(ctx), s_first_48(ctx), s_gaps(ctx), s_wishes(ctx), s_will(ctx),
        s_liquidity(ctx), s_documents(ctx), s_tier2(ctx), s_notify(ctx), s_footer(ctx),
    ]
    doc = (
        "<!doctype html><html lang=\"en-ZA\"><head><meta charset=\"utf-8\">"
        f"<title>Life File — tier {tier} — {ctx.today}</title>"
        f"<style>{CSS}</style></head><body>{''.join(sections)}</body></html>"
    )
    return doc, rep


def generate(tier: int = 1, *, html_only: bool = False) -> dict:
    if not vault.is_initialised():
        return {"schema": "life-file/1", "error": "no vault — run /lifeos-init"}
    if tier not in TIER_NAMES:
        return {"schema": "life-file/1", "error": f"tier must be 1, 2 or 3 (got {tier})"}

    doc, rep = build_html(tier)
    today = clock.today()
    out_dir = vault.path("reports", "life-file")
    html_path = out_dir / f"{today}-tier{tier}.html"
    atomic.write_text(html_path, doc)

    result = {
        "schema": "life-file/1",
        "at": clock.stamp(),
        "tier": tier,
        "tier_name": TIER_NAMES[tier],
        "readiness_score": rep.get("score"),
        "catastrophic_gaps": len(rep.get("catastrophic_gaps", [])),
        "html": vault.rel(html_path),
        "pdf": None,
    }

    if tier == 3:
        # Generating an unmasked copy is auditable: it must always be answerable
        # who produced one, and when.
        atomic.append_jsonl(vault.path("state", "audit.jsonl"), {
            "at": clock.stamp(), "event": "vault.write", "tool": "life_file",
            "path": str(html_path.relative_to(vault.vault_root())),
            "run_id": clock.Run.current().id,
            "note": "TIER 3 SEALED — full identifiers rendered",
        })

    if html_only:
        result["note"] = "HTML only, as requested."
        return result

    pdf_path = out_dir / f"{today}-tier{tier}.pdf"
    try:
        from weasyprint import HTML

        HTML(string=doc).write_pdf(str(pdf_path))
        result["pdf"] = vault.rel(pdf_path)
    except Exception as e:  # noqa: BLE001 — degrade, never fail
        result["pdf_error"] = f"{type(e).__name__}: {str(e).splitlines()[0][:160]}"
        result["note"] = (
            "PDF rendering unavailable, so only the HTML was written — open it in a "
            "browser and print to PDF. On macOS weasyprint needs pango and cairo: "
            "`brew install pango` and run with DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib."
        )
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lifeos.life_file")
    ap.add_argument("--tier", type=int, default=1, choices=[1, 2, 3])
    ap.add_argument("--html-only", action="store_true")
    args = ap.parse_args(argv)
    print(json.dumps(generate(args.tier, html_only=args.html_only), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
