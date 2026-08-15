# LifeOS — Coverage Map

> Status: Phase 0 (design). This is the contract that guarantees **nothing in the domain taxonomy is silently dropped**.
>
> Every leaf of §6 of the brief appears below with an **owner agent**, a **ledger/schema** or a **checklist item**, and the **phase** that implements it. `/audit` parses this file, compares it against `.claude/agents/` and `templates/schemas/` on disk, and **fails** if any leaf is unowned, any owner does not exist, or any named schema is missing.
>
> Because the agent tree is deliberately lean ([ADR-0010](adr/0010-lean-agent-tree.md)), coverage is proven here rather than by counting agent files.

**Legend** — `L` ledger record · `F` field on an existing record · `C` checklist item in `readiness` · `A` analysis routine (no stored record) · `R` rulebook in `.claude/rules/za/`

Totals: **176 leaf rows · 11 domain owners · 0 unowned.**

The count is higher than the brief's bullet count because compound bullets are decomposed to the level at which something is actually owned. §6A's "Core records: ID numbers, passports, driver's licences, birth/marriage certificates…" is one bullet and six rows, because each of those is separately present, absent or expired, and a checklist that scored them as one item would be useless.

---

## A. Identity, People & Entities → `identity`

| # | Leaf | Kind | Ledger / schema | Readiness checklist | Phase |
|---|---|---|---|---|---|
| A1 | Self | L | `people.jsonl` | ID doc on file | 1 |
| A2 | Spouse | L | `people.jsonl` `relation=spouse` | ID + marriage cert | 1 |
| A3 | Children, incl. from prior marriages and deceased | L | `people.jsonl` `relation=child`, `deceased_at` | birth certs per child | 1 |
| A4 | Dependants | L | `people.jsonl` `is_dependant` | proof of dependency | 2 |
| A5 | Parents and their birth dates | L | `people.jsonl` `relation=parent`, `born_on` | — | 2 |
| A6 | ID numbers | F | `people.id_number` *(PII: high)* | present + verified | 1 |
| A7 | Passports | F | `people.documents[].passport` + expiry | present + not expired | 2 |
| A8 | Driver's licences | F | `people.documents[].licence` + expiry | present + not expired | 2 |
| A9 | Birth / marriage certificates | F | `people.documents[]` | original location known | 2 |
| A10 | Maiden names | F | `people.former_names[]` | — | 1 |
| A11 | Addresses — home and postal | F | `people.addresses[].kind` | proof of residence < 3 months | 1 |
| A12 | All contact channels | F | `people.contacts[]` | — | 1 |
| A13 | Marital regime — ANC / accrual / in community | F | `people.marital.regime` | ANC contract on file | 1 |
| A14 | Divorce orders | L | `people.marital.orders[]` | order on file | 2 |
| A15 | Settlement & maintenance orders | L | `people.marital.orders[]` `kind=maintenance` | order on file; obligation dated | 2 |
| A16 | Employment — employer, occupation, work contacts, employee number | F | `people.employment` | — | 1 |
| A17 | Business entities — name, reg no., tax no., addresses | L | `entities.jsonl` | CIPC docs on file | 1 |
| A18 | Key personnel & contacts | F | `entities.key_people[]` → `people` | — | 2 |
| A19 | Shareholding | L | `relationships.jsonl` `kind=shareholding` `pct` | share certificates | 2 |
| A20 | Directorships | L | `relationships.jsonl` `kind=directorship` | CoR39 current | 2 |
| A21 | Auditors / accountants | F | `entities.advisors[]` | engagement letter | 2 |
| A22 | Partnership / CC / company agreements | F | `entities.agreements[]` → doc hash | agreement on file | 2 |
| A23 | Financial statements, currency < 6 months | F | `entities.financials[].as_at` | **age-checked**, stale → gap | 2 |
| A24 | Relationship graph across all domains | L | `relationships.jsonl` | graph has no orphan nodes | 1 |

## B. Day-to-Day Living → `living` (B1–B2, B6–B9) · `finance` (B4–B5) · `identity` (B3)

| # | Leaf | Kind | Ledger / schema | Readiness checklist | Phase |
|---|---|---|---|---|---|
| B1a | Medical aid scheme, plan/option, member number | L | `medical-aid.jsonl` | membership certificate | 4 |
| B1b | Main member vs dependants, dependant roster | F | `medical-aid.members[]` → `people` | roster matches `people` | 4 |
| B1c | Gap cover provider & policy | L | `medical-aid.jsonl` `kind=gap` | policy schedule on file | 4 |
| B1d | Family doctor & contacts | F | `medical-aid.providers[]` | — | 4 |
| B1e | Organ donor status | F | `people.organ_donor` | recorded per person | 4 |
| B1f | Dentistry / optometry sub-limits | F | `medical-aid.sublimits[]` | — | 4 |
| B1g | PMB awareness | A | health-cover map | PMB list attached | 4 |
| B1h | Savings / threshold tracking | A | `medical-aid` + `transactions` | — | 4 |
| B1i | Annual option-change window | R | `za/medical-aid-calendar.yaml` | diarised, 30-day lead | 4 |
| B2a | Pension / provident fund & member number | L | `employee-benefits.jsonl` | benefit statement < 12 months | 4 |
| B2b | Group life | L | `employee-benefits.jsonl` `kind=group_life` | schedule on file | 4 |
| B2c | Income protection (employer) | L | `employee-benefits.jsonl` `kind=income_protection` | schedule on file | 4 |
| B2d | Funeral cover (employer) | L | `employee-benefits.jsonl` `kind=funeral` | schedule on file | 4 |
| B2e | Risk benefits cross-referenced vs personal cover | A | duplication/gap analysis | **flagship cross-domain** | 4 |
| B3 | Income tax reference numbers per person and entity | F | `people.tax_ref` / `entities.tax_ref` | present per taxpayer | 1 |
| B4 | Banking — all accounts per person and entity: bank, branch, account number, type | L | `accounts.jsonl` | statement < 3 months | 3 |
| B5 | Regular payments — type, amount, source account, escalation, contract end, cancellation route | L | `recurring-payments.jsonl` | **cancellation route recorded** | 3 |
| B6 | Subscriptions & contracts — streaming, phone & data, gym, software, memberships | L | `subscriptions.jsonl` | — | 3 |
| B7a | Digital accounts, usernames | L | `digital-estate.jsonl` | — | 4 |
| B7b | Credential **location** — pointer only, never a secret | F | `digital-estate.credential_pointer` | pointer resolves | 4 |
| B7c | Devices | L | `digital-estate.jsonl` `kind=device` | — | 4 |
| B7d | Digital executor | F | `digital-estate.executor` → `people` | nominated | 4 |
| B8a | Safe code location, alarm code custodian, spare keys | L | `household.jsonl` `kind=access` *(location only)* | custodian named | 4 |
| B8b | Firearm licences | L | `household.jsonl` `kind=firearm` (asset in `assets`) | licence not expired | 4 |
| B8c | Service providers — repairs, alarm, plumbing, electrical | L | `household.jsonl` `kind=provider` | — | 4 |
| B9 | Rental & lease contracts, either direction | L | `leases.jsonl` `direction=in\|out` | signed lease on file | 4 |

## C. Insurance & Risk → `insurance`

| # | Leaf | Kind | Ledger / schema | Readiness checklist | Phase |
|---|---|---|---|---|---|
| C1 | Life assurance | L | `policies.jsonl` `class=life` | schedule on file | 4 |
| C2 | Disability / capital disability | L | `policies.jsonl` `class=disability` | schedule on file | 4 |
| C3 | Income protection | L | `policies.jsonl` `class=income_protection` | schedule on file | 4 |
| C4 | Dread disease | L | `policies.jsonl` `class=dread_disease` | schedule on file | 4 |
| C5 | Funeral | L | `policies.jsonl` `class=funeral` | schedule on file | 4 |
| C6 | Short-term: contents, buildings, vehicle, all-risk, portable possessions, liability, cyber | L | `policies.jsonl` `class=short_term`, `subclass` | schedule + inventory | 4 |
| C7 | Business: key person, buy-and-sell, contingent liability, overheads, professional indemnity | L | `policies.jsonl` `class=business`, `subclass` | schedule + buy-sell agreement | 4 |
| C8 | Per policy: insurer, number, type, premium, escalation, beneficiaries, cession, waiting periods, exclusions, broker | F | `policies` record fields | all fields present or gap-logged | 4 |
| C9a | Needs analysis vs actual cover | A | needs-vs-cover report | — | 4 |
| C9b | Duplication detection | A | cross-read `policies` × `employee-benefits` | **flagship cross-domain** | 4 |
| C9c | Premium efficiency | A | premium per R of cover, by class | — | 4 |
| C9d | Estate liquidity contribution | A | feeds `estate` liquidity model | — | 5 |
| C9e | `s3(3)(a)(ii)` deemed property implications | A+R | `za/estate-duty.yaml` | flagged per policy | 5 |
| C9f | Quote-refresh cadence | A | 45-day lead before anniversary | diarised | 4 |

## D. Investments & Retirement → `investments`

| # | Leaf | Kind | Ledger / schema | Readiness checklist | Phase |
|---|---|---|---|---|---|
| D1 | Retirement annuities | L | `holdings.jsonl` `kind=ra` | statement < 12 months | 4 |
| D2 | Preservation funds | L | `holdings.jsonl` `kind=preservation` | statement < 12 months | 4 |
| D3 | Pension / provident funds | L | `holdings.jsonl` `kind=occupational` | benefit statement | 4 |
| D4 | Two-pot components | F | `holdings.two_pot{savings,retirement,vested}` | split recorded | 4 |
| D5 | Unit trusts | L | `holdings.jsonl` `kind=unit_trust` | statement | 4 |
| D6 | Share portfolios | L | `holdings.jsonl` `kind=equity` | statement | 4 |
| D7 | Offshore | L | `holdings.jsonl` `offshore=true` + `fx-rates` | statement + AIT record | 4 |
| D8 | Money market | L | `holdings.jsonl` `kind=money_market` | statement | 4 |
| D9 | Crypto | L | `holdings.jsonl` `kind=crypto` | wallet inventory, keys pointer | 4 |
| D10 | TFSA | L | `holdings.jsonl` `kind=tfsa` | statement | 4 |
| D11 | Per holding: platform, account number, type, mandate, fees (advice/platform/fund), beneficiaries, performance | F | `holdings` record fields | fee breakdown present | 4 |
| D12a | Asset allocation vs policy | A | drift report | policy target declared | 4 |
| D12b | Reg 28 compliance | A+R | `za/reg28.yaml` | per applicable fund | 4 |
| D12c | Total expense ratio drag | A | TER × horizon projection | — | 4 |
| D12d | Currency exposure | A | via `fx-rates` | — | 4 |
| D12e | Contribution optimisation vs deduction cap | A+R | `za/retirement-deduction.yaml` | 60-day lead pre year-end | 5 |
| D12f | TFSA annual & lifetime limits | A+R | `za/tfsa-limits.yaml` | checked each Feb | 5 |
| D12g | `s10C` | A+R | `za/s10c.yaml` | — | 5 |
| D12h | Drawdown modelling & retirement adequacy | A | projection in `/what-if` | — | 7 |

## E. Assets & Liabilities → `assets` (net worth jointly with `finance`)

| # | Leaf | Kind | Ledger / schema | Readiness checklist | Phase |
|---|---|---|---|---|---|
| E1 | Property: description, address, title deed location, valuation, bond, rates, levies, tenants, sectional-title deeds | L | `assets.jsonl` `class=property` + `valuations` | **title deed location recorded** | 4 |
| E2 | Vehicles & registrations | L | `assets.jsonl` `class=vehicle` | registration papers | 4 |
| E3 | Jewellery, art, collectibles | L | `assets.jsonl` `class=valuable` | valuation < 3 years | 4 |
| E4 | Firearms & licences | L | `assets.jsonl` `class=firearm` | licence not expired | 4 |
| E5 | Timeshare | L | `assets.jsonl` `class=timeshare` | contract + levy schedule | 4 |
| E6 | Offshore assets | L | `assets.jsonl` `offshore=true` | + FX basis recorded | 4 |
| E7 | Home loans | L | `liabilities.jsonl` `kind=home_loan` | statement | 3 |
| E8 | Vehicle finance | L | `liabilities.jsonl` `kind=vehicle_finance` | agreement + settlement quote | 3 |
| E9 | Overdrafts | L | `liabilities.jsonl` `kind=overdraft` | facility letter | 3 |
| E10 | Credit cards | L | `liabilities.jsonl` `kind=credit_card` | statement | 3 |
| E11 | Store & clothing accounts | L | `liabilities.jsonl` `kind=store_account` | statement | 3 |
| E12 | Personal loans | L | `liabilities.jsonl` `kind=personal_loan` | agreement | 3 |
| E13 | Cellphone contracts | L | `liabilities.jsonl` `kind=cellphone` | contract end date | 3 |
| E14 | **Surety and suretyship obligations** | L | `liabilities.jsonl` `kind=suretyship` | **required, not optional** | 4 |
| E15 | Assets pledged as security | F | `assets.pledged_to` → `liabilities` | encumbrance recorded | 4 |
| E16 | Insolvency history | F | `people.insolvency` / `entities.insolvency` | declared or explicitly none | 4 |
| E17 | Usufruct | L | `assets.jsonl` `class=right` `kind=usufruct` | deed on file | 5 |
| E18 | Fideicommissum | L | `assets.jsonl` `class=right` `kind=fideicommissum` | deed on file | 5 |
| E19 | Annuity & trust income entitlements | L | `assets.jsonl` `class=right` `kind=income_entitlement` | source doc | 5 |
| E20 | Rolling net worth statement & balance-sheet history | L | `networth-snapshots.jsonl` (`finance`) | monthly snapshot exists | 3 |

## F. Tax → `tax`

| # | Leaf | Kind | Ledger / schema | Readiness checklist | Phase |
|---|---|---|---|---|---|
| F1 | Personal annual return (ITR12) | L | `tax-events.jsonl` `kind=itr12` | filed / due | 5 |
| F2 | IRP5 / IT3(a) | L | `tax-events.jsonl` `kind=irp5` | received per employer | 5 |
| F3 | IT3(b) / IT3(c) | L | `tax-events.jsonl` `kind=it3` | received per platform | 5 |
| F4 | Medical tax credits | A+R | `za/medical-credits.yaml` × `medical-aid` | — | 5 |
| F5 | RA deduction | A+R | `za/retirement-deduction.yaml` × `contributions` | — | 5 |
| F6 | Travel allowance / logbook | L | `tax-events.jsonl` `kind=logbook` | **logbook maintained** | 5 |
| F7 | Home office | A+R | `za/home-office.yaml` | floor-area evidence | 5 |
| F8 | Rental income schedules | A | `leases` × `transactions` | per property | 5 |
| F9 | CGT events | L | `tax-events.jsonl` `kind=cgt` | base cost documented | 5 |
| F10 | Provisional tax — Aug & Feb (IRP6) | L | `tax-deadlines.jsonl` | 30-day lead each | 5 |
| F11 | Donations tax | L | `tax-events.jsonl` `kind=donation` | — | 5 |
| F12 | `s10(1)(o)(ii)` foreign employment | A+R | `za/s10-1-o-ii.yaml` | if applicable | 5 |
| F13 | Company / CC / trust returns | L | `tax-deadlines.jsonl` per entity | ITR14 / IT12TR diarised | 5 |
| F14 | Business provisional tax | L | `tax-deadlines.jsonl` per entity | — | 5 |
| F15 | VAT cycle (VAT201) | L | `tax-deadlines.jsonl` `kind=vat` | bi-monthly, 7-day lead | 5 |
| F16 | PAYE / UIF / SDL (EMP201) | L | `tax-deadlines.jsonl` `kind=emp201` | monthly, 5-day lead | 5 |
| F17 | Dividends tax | L | `tax-events.jsonl` `kind=dividends_tax` | — | 5 |
| F18 | Trust distributions | L | `distributions.jsonl` (`trusts`) → attribution | 6 |
| F19 | `s7C` loan interest | A+R | `za/s7c.yaml` × `loan-accounts` | annual check | 6 |
| F20 | Conduit principle | A | attribution model | — | 6 |
| F21 | Attribution rules | A+R | `za/attribution.yaml` | — | 6 |
| F22 | Deadline calendar | L | `tax-deadlines.jsonl` | drives `/deadlines` | 5 |
| F23 | Document readiness checklist | C | via `readiness` | tax pack completeness | 5 |
| F24 | Effective-rate tracking | A | year-on-year effective rate | — | 5 |
| F25 | Structuring reviews vs current SARS tables | A+R | `za/sars-tables.yaml` with `as_at` + refresh | **re-verify when stale** | 5 |

## G. Estate, Wills & Succession → `estate`

| # | Leaf | Kind | Ledger / schema | Readiness checklist | Phase |
|---|---|---|---|---|---|
| G1 | Will — signed? combined? date, executor, custodian & physical location, review triggers | L | `wills.jsonl` | **signed + location known** | 5 |
| G2 | Living will and its location | L | `wills.jsonl` `kind=living_will` | present + location | 5 |
| G3 | Further wishes and instructions supportive of the will | L | `wills.jsonl` `kind=wishes` | present | 5 |
| G4a | Estate duty calculation | A+R | `za/estate-duty.yaml` | modelled | 5 |
| G4b | CGT at death | A+R | `za/cgt-death.yaml` | modelled | 5 |
| G4c | `s4A` abatement | A+R | `za/estate-duty.yaml` | applied | 5 |
| G4d | Section 4(q) spousal roll-over | A+R | `za/estate-duty.yaml` | applied | 5 |
| G4e | Executor's fees | A+R | `za/executor-fees.yaml` | modelled | 5 |
| G4f | Master's fees | A+R | `za/master-fees.yaml` | modelled | 5 |
| G4g | **Liquidity shortfall analysis** | A | cash needed vs cash available at death | headline number | 5 |
| G5 | Beneficiary nominations across every policy and fund, checked for conflict with the will | L+A | `beneficiaries.jsonl` × `policies` × `holdings` × `wills` | **conflict = high-priority finding** | 5 |
| G6 | Estate details of deceased spouse, prior estate rights | L | `wills.jsonl` `kind=prior_estate` | L&D account on file | 5 |
| G7 | Family & friends to be notified — name, relationship, contact | L | `people.notify_on_death` | list exists | 5 |
| G8 | Ongoing court cases (courts must be notified on death) | L | `tax-events`-adjacent → `wills.jsonl` `kind=litigation` | case refs recorded | 5 |
| G9 | Maintenance obligations | L | see A15 `people.marital.orders[]` | obligation survives death? flagged | 5 |

## H. Trusts → `trusts` (also shipped as `packs/trusts/`)

| # | Leaf | Kind | Ledger / schema | Readiness checklist | Phase |
|---|---|---|---|---|---|
| H1 | Trust register: name, MT number, type (inter vivos discretionary / testamentary / bewind / special) | L | `trusts.jsonl` | letters of authority on file | 6 |
| H2 | Deed & amendments | F | `trusts.deed[]` → doc hashes | deed + all amendments | 6 |
| H3 | Letters of authority | F | `trusts.loa` | current, names match trustees | 6 |
| H4 | Trustees: identity, appointments & resignations | L | `trustees.jsonl` → `people` | matches LoA | 6 |
| H5 | Independent trustee presence | A | `trustees` check | **flagged if absent** | 6 |
| H6 | Resolutions register | L | `trustees.jsonl` `kind=resolution` | complete for the year | 6 |
| H7 | Meeting minutes and cadence | L | `trustees.jsonl` `kind=minutes` | cadence met | 6 |
| H8 | Beneficiaries: capital vs income, contingent vs vested, classes | L | `trusts.beneficiaries[]` | class definitions recorded | 6 |
| H9 | Trust assets | L | `assets.jsonl` `owner_entity=<trust>` | AFS-reconciled | 6 |
| H10 | Loan accounts | L | `loan-accounts.jsonl` | balance + terms | 6 |
| H11 | `s7C` interest exposure | A+R | `za/s7c.yaml` | annual computation | 6 |
| H12 | Distributions and tax attribution | L | `distributions.jsonl` | matches IT12TR | 6 |
| H13 | Annual financial statements | L | `tax-deadlines.jsonl` per trust | AFS < 12 months | 6 |
| H14 | IT12TR | L | `tax-deadlines.jsonl` | filed / due | 6 |
| H15 | Beneficial-ownership register (Master's filing) | L | `trusts.bo_register` | **filed, dated** | 6 |
| H16 | FICA obligations | C | `readiness` | accountable-institution status | 6 |
| H17 | Independent-trustee & proper-administration duties | C+A | `readiness` + compliance report | duties evidenced | 6 |
| H18 | Trustee liability | A | risk note per trustee | — | 6 |
| H19 | Testamentary trust for minors, guardianship interaction | A | `wills` × `trusts` × `people` | guardian nominated | 6 |
| H20 | Documented separation of trust from personal affairs | A | separation report; graph still links | **explicit statement** | 6 |

## I. Funeral & Final Wishes → `final-wishes`

| # | Leaf | Kind | Ledger / schema | Readiness checklist | Phase |
|---|---|---|---|---|---|
| I1 | Burial vs cremation, per person | F | `final-wishes.disposition` | recorded per adult | 5 |
| I2 | Grave purchased? plot details | F | `final-wishes.plot` | deed of grave | 5 |
| I3 | Ashes instructions | F | `final-wishes.ashes` | recorded | 5 |
| I4 | Funeral cover & provider contacts | F | → `policies` `class=funeral` + `final-wishes.provider` | contact reachable | 5 |
| I5 | Service preferences | F | `final-wishes.service` | recorded | 5 |
| I6 | Immediate-liquidity plan, first 30 days | A | cross-read `finance` × `insurance` | **a real number**; page 1 of the Life File | 5 |

## J. Document Readiness → `readiness`

| # | Leaf | Kind | Ledger / schema | Readiness checklist | Phase |
|---|---|---|---|---|---|
| J1 | Every required document per person and entity | L | `readiness.jsonl` one row per (subject, requirement) | — | 2 |
| J2 | Present / absent / expired | F | `readiness.status` | — | 2 |
| J3 | Where the original is kept | F | `readiness.original_location` | **asked for every original** | 2 |
| J4 | Who else needs a copy | F | `readiness.copies_needed[]` | — | 2 |
| J5 | Readiness Score | A | weighted by consequence-of-absence, not count | headline number | 2 |
| J6 | Shortest path to improve it | A | ranked by score-delta ÷ effort | top 5 actions | 2 |
| J7 | **The Life File document itself** — the tiered PDF handed to family | A | `/life-file` → `reports/life-file/` | 3 tiers; gaps are the headline | 2 |

---

## Cross-cutting coverage

Not taxonomy leaves, but required by the brief and owned here so they cannot fall through.

| Concern | Owner | Artefact |
|---|---|---|
| Inbox → filed original, never lost | `librarian` | `documents/index.jsonl` |
| Three-tier memory + consolidation ritual | `memory-keeper` | `memory/**`, `memory/audit.jsonl` |
| System growth, coverage audit, this file | `meta-architect` | `.claude/agents/`, this map |
| System backlog, phase tracking, self-maintenance | `meta-architect` | GitHub issues + milestones, mirrored to `state/system/issues.jsonl` ([github.md](github.md)) |
| Shared computation | `analyst` | `reports/analysis/*.json` |
| Rendering, no-CDN dashboards | `visualiser` | `reports/**` |
| Unknowns register | *all agents, append-only* | `state/gaps.jsonl` |
| Human gates | `orchestrator` | `proposed/` |
| PII redaction | hooks | `.claude/hooks/pii-guard.py` |
| POPIA erasure | `/forget` | [data-dictionary.md](data-dictionary.md) |

## Disabled domains

A domain switched off in `profile.yaml` is **not** removed from this map. Its rows are rendered as `not tracked — disabled <date>`, the relationship graph keeps the dangling edges as explicit unknowns, and `/readiness` excludes them from the score while listing them separately. Turning a domain back on must never require a repair step.
