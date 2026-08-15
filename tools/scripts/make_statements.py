"""Generate FAKE multi-month, multi-bank, multi-entity statements.

Proves the consolidation claim: personal and business kept strictly separate
while still rolling up to one view. Every institution, number and person is
invented.
"""
from __future__ import annotations
import csv, random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INBOX = ROOT / "vault.example" / "inbox"
INBOX.mkdir(parents=True, exist_ok=True)
random.seed(20260815)  # deterministic fixtures: golden tests depend on it

MONTHS = [("05", "May"), ("06", "Jun"), ("07", "Jul")]
DAYS = {"05": 31, "06": 30, "07": 31}

# Recurring personal commitments. escalation applies from July.
RECUR = [
    ("DEBIT ORDER OUTSURANCE 4471", 184200, None),
    ("DEBIT ORDER DISCOVERY HEALTH", 731400, "07"),
    ("BOND REPAYMENT HOMELOAN 9921", 1875000, None),
    ("NETFLIX.COM", 19900, None),
    ("SPOTIFY AB", 11999, None),
    ("VIRGIN ACTIVE", 89900, "07"),
    ("ALLAN GRAY RA CONTRIB", 650000, None),
    ("MTN PREPAID DATA", 59900, None),
    ("DSTV PREMIUM", 94500, None),
]
VARIABLE = [
    ("WOOLWORTHS SANDTON", 80000, 180000),
    ("CHECKERS HYPER", 60000, 140000),
    ("ENGEN GARAGE", 90000, 130000),
    ("UBER TRIP", 8000, 25000),
    ("TAKEALOT.COM", 15000, 90000),
    ("CLICKS PHARMACY", 12000, 45000),
    ("PNP EXPRESS", 9000, 30000),
]
FEES = [("SERVICE FEE", 12100), ("CARD FEE", 3500)]


def r(c): return f"{c/100:,.2f}".replace(",", " ")


def personal_rows(mm, label):
    rows, bal = [], 4211855 if mm == "05" else None
    rows.append((f"01 {label} 2026", "OPENING BALANCE", "", "", None))
    tx = [("02", "SALARY NORTHWIND SOFTWARE", 6842000, "in")]
    for d, (desc, amt, esc) in zip(["03", "03", "05", "09", "09", "22", "25", "11", "14"], RECUR):
        a = int(amt * 1.06) if esc and mm >= esc else amt
        tx.append((d, desc, a, "out"))
    for i, (desc, lo, hi) in enumerate(VARIABLE):
        tx.append((f"{7+i*2:02d}", desc, random.randint(lo, hi), "out"))
    tx.append(("15", "RENT RECEIVED JHB PROPS CC", 950000, "in"))
    if mm in ("08", "02"):
        tx.append(("18", "SARS EFILING IRP6", 1240000, "out"))
    for d, (desc, amt) in zip(["28", "28"], FEES):
        tx.append((d, desc, amt, "out"))
    tx.sort(key=lambda t: t[0])
    return tx


def build_pdf(mm, label, tx, opening):
    bal = opening
    body = [(f"01 {label} 2026", "OPENING BALANCE", "", "", r(bal))]
    for d, desc, amt, direction in tx:
        bal += amt if direction == "in" else -amt
        body.append((f"{d} {label} 2026", desc,
                     "" if direction == "in" else r(amt),
                     r(amt) if direction == "in" else "", r(bal)))
    body.append((f"{DAYS[mm]} {label} 2026", "CLOSING BALANCE", "", "", r(bal)))
    rows = "".join(
        f"<tr><td>{a}</td><td>{b}</td><td class=n>{c}</td><td class=n>{d}</td><td class=n>{e}</td></tr>"
        for a, b, c, d, e in body)
    html = f"""<style>
@page {{ size: A4; margin: 18mm; }}
body {{ font-family: Helvetica, Arial, sans-serif; font-size: 9.5pt; }}
h1 {{ font-size: 15pt; margin: 0 0 2mm; }}
.hdr {{ border-bottom: 2px solid #333; padding-bottom: 3mm; margin-bottom: 5mm; }}
.meta td {{ padding: 0.6mm 6mm 0.6mm 0; font-size: 9pt; }}
table.tx {{ width: 100%; border-collapse: collapse; margin-top: 4mm; }}
table.tx th {{ text-align: left; border-bottom: 1px solid #333; padding: 1.5mm 1mm; font-size: 8.5pt; }}
table.tx td {{ padding: 1.2mm 1mm; border-bottom: 0.3px solid #ddd; }}
td.n, th.n {{ text-align: right; }}
.foot {{ margin-top: 6mm; font-size: 7.5pt; color: #666; }}
</style>
<div class=hdr><h1>NORTHBANK</h1><div>Cheque Account Statement</div></div>
<table class=meta>
 <tr><td><b>Account holder</b></td><td>A SAMPLE</td>
     <td><b>Statement period</b></td><td>01 {label} 2026 &ndash; {DAYS[mm]} {label} 2026</td></tr>
 <tr><td><b>Account number</b></td><td>1049 5560 118</td>
     <td><b>Branch code</b></td><td>250655</td></tr>
 <tr><td><b>Account type</b></td><td>Gold Cheque</td><td><b>Statement no.</b></td><td>08{mm}</td></tr>
</table>
<table class=tx>
 <tr><th>Date</th><th>Description</th><th class=n>Money out</th><th class=n>Money in</th><th class=n>Balance</th></tr>
 {rows}</table>
<div class=foot>FICTIONAL DOCUMENT — LifeOS test fixture.</div>"""
    from weasyprint import HTML
    out = INBOX / f"northbank-cheque-2026-{mm}.pdf"
    HTML(string=html).write_pdf(str(out))
    print("  ", out.name)
    return bal


bal = 4211855
for mm, label in MONTHS:
    bal = build_pdf(mm, label, personal_rows(mm, label), bal)

# ── Business account: different bank, different layout, own entity ───────────
print("business (semicolon CSV, dd/mm/yyyy, single signed amount column):")
biz = [
    ("02/07/2026", "CLIENT PAYMENT ACME HOLDINGS", 12500000),
    ("03/07/2026", "AWS EMEA CLOUD SERVICES", -1842300),
    ("05/07/2026", "SALARIES EMPLOYEE BATCH", -8400000),
    ("07/07/2026", "PAYE SARS EMP201", -1920000),
    ("10/07/2026", "GITHUB.COM SUBSCRIPTION", -84000),
    ("11/07/2026", "NETFLIX.COM", -19900),
    ("14/07/2026", "CLIENT PAYMENT BLUEBIRD LTD", 6800000),
    ("18/07/2026", "OFFICE RENT SANDTON", -2200000),
    ("22/07/2026", "MONTHLY ACCOUNT FEE", -46500),
    ("25/07/2026", "VAT PAYMENT SARS", -3100000),
]
bal = 0
with (INBOX / "meridian-business-2026-07.csv").open("w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh, delimiter=";")
    w.writerow(["Posting date", "Narrative", "Amount", "Balance"])
    for d, desc, amt in biz:
        bal += amt
        w.writerow([d, desc, f"{amt/100:.2f}", f"{bal/100:.2f}"])
print("   meridian-business-2026-07.csv")
print(f"\n{len(list(INBOX.iterdir()))} fixtures total")
