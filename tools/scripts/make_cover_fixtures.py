"""FAKE medical aid, gap cover and employee benefit documents.

Deliberately arranged so the cross-domain analysis has something real to find:
income protection is held BOTH through the employer and personally, which in SA
cannot both pay out above roughly 75% of income — a duplication invisible from
inside either document.
"""
from __future__ import annotations
from pathlib import Path
from weasyprint import HTML

ROOT = Path(__file__).resolve().parents[2]
INBOX = ROOT / "vault.example" / "inbox"

CSS = """<style>
@page { size: A4; margin: 18mm; }
body { font-family: Helvetica, Arial, sans-serif; font-size: 10pt; }
h1 { font-size: 15pt; margin: 0 0 1mm; }
h2 { font-size: 11pt; margin: 6mm 0 2mm; border-bottom: 1px solid #999; padding-bottom: 1mm; }
.hdr { border-bottom: 2px solid #333; padding-bottom: 3mm; margin-bottom: 4mm; }
table { border-collapse: collapse; width: 100%; margin-top: 2mm; }
td { padding: 1.3mm 4mm 1.3mm 0; vertical-align: top; }
td.k { width: 46%; color: #444; }
th { text-align: left; border-bottom: 1px solid #333; padding: 1.5mm 4mm 1.5mm 0; font-size: 9pt; }
td.n { text-align: right; }
.foot { margin-top: 7mm; font-size: 7.5pt; color: #666; }
</style>"""

DOCS = {
"discovery-membership-certificate.pdf": CSS + """
<div class=hdr><h1>MERIDIAN HEALTH MEDICAL SCHEME</h1><div>Membership Certificate</div></div>
<h2>Membership</h2>
<table>
 <tr><td class=k>Medical scheme</td><td>Meridian Health Medical Scheme</td></tr>
 <tr><td class=k>Membership number</td><td>MH 8842011</td></tr>
 <tr><td class=k>Plan</td><td>Comprehensive Series</td></tr>
 <tr><td class=k>Option</td><td>Classic Comprehensive</td></tr>
 <tr><td class=k>Main member</td><td>A Sample</td></tr>
 <tr><td class=k>Monthly contribution</td><td>R 7 752.84</td></tr>
 <tr><td class=k>Period of cover</td><td>01 January 2026 to 31 December 2026</td></tr>
</table>
<h2>Dependants</h2>
<table>
 <tr><th>Name</th><th>Type</th><th>Date joined</th></tr>
 <tr><td>M Sample</td><td>Adult dependant</td><td>01 January 2020</td></tr>
 <tr><td>T Sample</td><td>Child dependant</td><td>14 March 2022</td></tr>
</table>
<h2>Benefits</h2>
<table>
 <tr><td class=k>Annual hospital cover</td><td>Unlimited at scheme rate</td></tr>
 <tr><td class=k>Medical savings account (annual)</td><td>R 24 600.00</td></tr>
 <tr><td class=k>Self-payment gap</td><td>R 11 400.00</td></tr>
 <tr><td class=k>Above threshold benefit</td><td>Applies after R 36 000.00</td></tr>
 <tr><td class=k>Dentistry sub-limit</td><td>R 9 800.00 per family per year</td></tr>
 <tr><td class=k>Optometry sub-limit</td><td>R 4 200.00 per beneficiary every 2 years</td></tr>
 <tr><td class=k>Prescribed Minimum Benefits</td><td>Covered in full at designated providers</td></tr>
 <tr><td class=k>Option change window</td><td>01 October 2026 to 30 November 2026</td></tr>
</table>
<div class=foot>FICTIONAL DOCUMENT — LifeOS test fixture.</div>""",

"gapcover-policy-schedule.pdf": CSS + """
<div class=hdr><h1>SENTINEL GAP COVER</h1><div>Policy Schedule</div></div>
<h2>Policy details</h2>
<table>
 <tr><td class=k>Policy number</td><td>SG-771204</td></tr>
 <tr><td class=k>Policy type</td><td>Medical gap cover</td></tr>
 <tr><td class=k>Principal insured</td><td>A Sample</td></tr>
 <tr><td class=k>Insurer</td><td>Sentinel Gap Cover (Pty) Ltd</td></tr>
 <tr><td class=k>Monthly premium</td><td>R 512.00</td></tr>
 <tr><td class=k>Inception date</td><td>01 March 2021</td></tr>
 <tr><td class=k>Anniversary date</td><td>01 March</td></tr>
 <tr><td class=k>Premium escalation</td><td>7% per annum</td></tr>
</table>
<h2>Cover</h2>
<table>
 <tr><td class=k>In-hospital shortfall</td><td>Up to 500% of scheme rate</td></tr>
 <tr><td class=k>Annual limit per beneficiary</td><td>R 187 000.00</td></tr>
 <tr><td class=k>Co-payment cover</td><td>Included</td></tr>
 <tr><td class=k>Sub-limit: oncology co-payments</td><td>R 40 000.00</td></tr>
 <tr><td class=k>Casualty benefit</td><td>R 8 500.00 per event</td></tr>
</table>
<h2>Exclusions and waiting periods</h2>
<table>
 <tr><td class=k>General waiting period</td><td>3 months from inception</td></tr>
 <tr><td class=k>Pre-existing conditions</td><td>12 months</td></tr>
 <tr><td class=k>Out-of-hospital day-to-day expenses</td><td>NOT COVERED</td></tr>
 <tr><td class=k>Chronic medication</td><td>NOT COVERED</td></tr>
</table>
<div class=foot>FICTIONAL DOCUMENT — LifeOS test fixture.</div>""",

"northwind-employee-benefit-statement.pdf": CSS + """
<div class=hdr><h1>NORTHWIND SOFTWARE (PTY) LTD</h1><div>Employee Benefit Statement</div></div>
<h2>Member</h2>
<table>
 <tr><td class=k>Member</td><td>A Sample</td></tr>
 <tr><td class=k>Employee number</td><td>NW-0442</td></tr>
 <tr><td class=k>Annual pensionable salary</td><td>R 1 025 000.00</td></tr>
 <tr><td class=k>Statement as at</td><td>30 June 2026</td></tr>
</table>
<h2>Retirement fund</h2>
<table>
 <tr><td class=k>Fund</td><td>Northwind Provident Fund</td></tr>
 <tr><td class=k>Member number</td><td>NWP 100442</td></tr>
 <tr><td class=k>Fund value</td><td>R 1 842 500.00</td></tr>
 <tr><td class=k>Member contribution</td><td>7.5% of pensionable salary</td></tr>
 <tr><td class=k>Employer contribution</td><td>10.0% of pensionable salary</td></tr>
</table>
<h2>Risk benefits</h2>
<table>
 <tr><th>Benefit</th><th>Cover</th><th>Notes</th></tr>
 <tr><td>Group life assurance</td><td>4 times annual salary</td><td>R 4 100 000.00</td></tr>
 <tr><td>Lump sum disability</td><td>3 times annual salary</td><td>R 3 075 000.00</td></tr>
 <tr><td>Income protection</td><td>75% of monthly salary</td><td>R 64 062.50 per month, after 3 months</td></tr>
 <tr><td>Funeral benefit</td><td>R 30 000.00</td><td>Member, spouse and children</td></tr>
</table>
<h2>Beneficiary nomination</h2>
<table>
 <tr><td class=k>M Sample (spouse)</td><td>100%</td></tr>
</table>
<div class=foot>FICTIONAL DOCUMENT — LifeOS test fixture.</div>""",

"aegis-income-protection-schedule.pdf": CSS + """
<div class=hdr><h1>AEGIS LIFE</h1><div>Policy Schedule</div></div>
<h2>Policy details</h2>
<table>
 <tr><td class=k>Policy number</td><td>AG-5590213</td></tr>
 <tr><td class=k>Policy type</td><td>Income protection (temporary and permanent disability)</td></tr>
 <tr><td class=k>Life assured</td><td>A Sample</td></tr>
 <tr><td class=k>Policy owner</td><td>A Sample</td></tr>
 <tr><td class=k>Insurer</td><td>Aegis Life Limited</td></tr>
 <tr><td class=k>Monthly benefit</td><td>R 55 000.00</td></tr>
 <tr><td class=k>Monthly premium</td><td>R 1 284.00</td></tr>
 <tr><td class=k>Waiting period</td><td>3 months</td></tr>
 <tr><td class=k>Inception date</td><td>01 June 2022</td></tr>
 <tr><td class=k>Anniversary date</td><td>01 June</td></tr>
 <tr><td class=k>Premium escalation</td><td>6% per annum</td></tr>
 <tr><td class=k>Benefit ceases</td><td>Age 65</td></tr>
</table>
<h2>Exclusions</h2>
<table>
 <tr><td class=k>Self-inflicted injury</td><td>Excluded</td></tr>
 <tr><td class=k>Professional sport</td><td>Excluded</td></tr>
</table>
<div class=foot>FICTIONAL DOCUMENT — LifeOS test fixture.</div>""",
}

for name, html in DOCS.items():
    HTML(string=html).write_pdf(str(INBOX / name))
    print("  ", name)
print(f"\n{len(list(INBOX.iterdir()))} fixtures total")
