# inbox/

**Drop documents here. This is the only thing you do manually.**

Bank statements, policy schedules, medical aid certificates, tax certificates,
wills, trust deeds, payslips, invoices — any format.

`/heartbeat` or `/ingest` classifies each one, files an immutable original
under `documents/`, and routes it to the domain that owns it.

Nothing here is ever deleted by the system. A file that cannot be classified
stays put with a gap record explaining why.
