# LifeOS — Data Dictionary

> Status: Phase 0 (design). Executable JSON Schemas live in `templates/schemas/`; this document is the human-readable specification they implement.
>
> Covers: the shared record envelope, every ledger, state files, memory files, and the **POPIA classification and erasure path** for each category.

## 1. Conventions

| Rule | Detail |
|---|---|
| **Money** | `{ "cents": <int>, "currency": "ZAR" }` — integer minor units, ISO-4217. Never a float ([ADR-0005](adr/0005-money-as-integer-cents.md)). |
| **Dates** | `YYYY-MM-DD` for calendar dates; RFC 3339 UTC for instants. Local time is Africa/Johannesburg and appears only in human-facing output. |
| **IDs** | `id` = `sha256(doc_hash + locator + natural_key)`, rendered `sha256:<64 hex>`. Stable across re-ingestion ([ADR-0006](adr/0006-deterministic-record-ids.md)). |
| **Refs** | `per_<slug>` people · `ent_<slug>` entities · `acc_<slug>` accounts · `pol_<slug>` policies · `tr_<slug>` trusts. Human-legible on purpose. |
| **Schema** | `"<ledger>/<major>"`. Bumps require an ADR and a migration ([ADR-0012](adr/0012-schema-versioning.md)). |
| **Unknown** | Omit the field and write a record to `state/gaps.jsonl`. **Never** `null` meaning "we didn't look", never `0` meaning "unknown", never a placeholder. |
| **Append-only** | Ledgers are JSONL, appended. Corrections append a new record and a tombstone setting `superseded_by`. |
| **Secrets** | Pointers only. `credential_pointer: "1Password/Personal/FNB Online"` is permitted; a password is a schema violation and a hook block. |

## 2. The record envelope

Every record in every ledger. `templates/schemas/envelope.schema.json`.

| Field | Type | Req | Meaning |
|---|---|---|---|
| `id` | `sha256:<hex>` | ✓ | deterministic identity |
| `schema` | `"<ledger>/<n>"` | ✓ | schema name + major version |
| `subject_id` | `per_*` \| `ent_*` | ✓ | whose record this is |
| `entity_id` | `ent_*` | | owning entity when different from subject (business vs personal) |
| `source.doc_hash` | `sha256:<hex>` | ✓ | the filed original this came from |
| `source.locator` | string | ✓ | `page=3;row=17`, `sheet=Summary;cell=B14`, `para=12` |
| `source.method` | string | ✓ | `parser:absa-cheque/2`, `pdfplumber`, `ocr:tesseract`, `llm-extract`, `human`, `inferred` |
| `source.confidence` | 0.0–1.0 | ✓ | below the ledger's floor → `proposed/`, not the ledger |
| `source.extracted_at` | instant | ✓ | when extraction ran |
| `valid_from` | date | ✓ | when the fact became true |
| `valid_to` | date \| `null` | ✓ | `null` = still true |
| `superseded_by` | `sha256:*` \| `null` | ✓ | set by a later correction |
| `_meta.run_id` | string | ✓ | the heartbeat run that wrote it |
| `_meta.agent` | string | ✓ | the sole-writer agent |
| `_meta.written_at` | instant | ✓ | wall clock at write |

**Bitemporality.** `valid_from`/`valid_to` describe the world; `_meta.written_at` describes our knowledge of it. That separation is what lets the system answer *"what did we believe the net worth was in March?"* as well as *"what was it in March?"* — different questions, both needed for an audit.

## 3. Ledgers

Owners are authoritative in [agent-catalogue.md](agent-catalogue.md). `†` = contains high-sensitivity PII.

### `people.jsonl` † — `identity`
`ref` · `full_name` · `former_names[]` · `relation` (self/spouse/child/parent/dependant/other) · `born_on` · `deceased_at` · `id_number` † · `tax_ref` † · `organ_donor` · `insolvency` · `addresses[]{kind,line1..,postal_code}` · `contacts[]{kind,value}` † · `documents[]{kind,number,issued,expires,doc_hash,original_location}` · `marital{regime,married_on,orders[]{kind,court,case_no,doc_hash}}` · `employment{employer,occupation,employee_no,contacts[]}` · `notify_on_death{include,relationship,contact}` · `is_dependant`

### `entities.jsonl` † — `identity`
`ref` · `legal_name` · `trading_name` · `form` (pty/cc/trust/partnership/sole_prop) · `registration_no` † · `tax_ref` † · `vat_no` † · `addresses[]` · `key_people[]{person_ref,role}` · `advisors[]{kind,name,contact}` · `agreements[]{kind,doc_hash,signed_on}` · `financials[]{as_at,doc_hash,audited}` · `insolvency`

> `financials[].as_at` drives the brief's "< 6 months" currency rule. Stale → gap record, surfaced in `/readiness`.

### `relationships.jsonl` — `identity`
`from_ref` · `to_ref` · `kind` (shareholding/directorship/trustee/beneficiary/dependant/guardian/spouse/employment/suretyship/pledge) · `pct` · `since` · `until` · `doc_hash`

> The edge table for the whole graph. Every cross-domain question resolves through it.

### `accounts.jsonl` † — `finance`
`ref` · `owner_ref` · `bank` · `branch_code` · `account_no` † · `kind` (cheque/savings/credit_card/loan/money_market/business) · `currency` · `opened_on` · `closed_on` · `is_business` · `statement_cadence`

### `transactions.jsonl` — `finance`
`account_ref` · `posted_on` · `value_on` · `description_raw` · `description_clean` · `amount{cents,currency}` · `balance_after{cents,currency}` · `category` · `subcategory` · `counterparty` · `is_recurring` · `recurring_ref` · `tax_relevance[]` · `category_confidence` · `category_method` (rule/history/llm/human)

> The largest ledger. Confidence below `profile.finance.category_floor` means the transaction lands **uncategorised with a question**, not guessed into a bucket.

### `recurring-payments.jsonl` — `finance`
`ref` · `payer_ref` · `account_ref` · `counterparty` · `kind` (debit_order/eft/card_recurring/cash) · `amount{cents,currency}` · `frequency` · `escalation{pct,month}` · `started_on` · `contract_ends_on` · `cancellation_route` · `last_seen_txn` · `status` (active/lapsed/cancelled)

> `cancellation_route` is required — a recurring cost you cannot work out how to stop is a finding, and the field exists to force the question.

### `budgets.yaml` — `finance`
Per entity, per category: `target{cents,currency}` · `period` · `tolerance_pct` · `notes`. Human-authored, machine-read.

### `networth-snapshots.jsonl` — `finance`
`as_at` · `entity_ref` · `assets{cents}` · `liabilities{cents}` · `net{cents}` · `components[]{ledger,record_id,cents}` · `fx_basis[]{pair,rate,rate_date}`

> `components[]` makes every snapshot fully attributable; `/audit` walks it.

### `medical-aid.jsonl` † — `living`
`ref` · `kind` (scheme/gap) · `provider` · `plan` · `option` · `member_no` † · `main_member_ref` · `members[]{person_ref,role}` · `premium{cents,currency}` · `savings{annual,used}` · `threshold{annual,reached_on}` · `sublimits[]{kind,limit}` · `providers[]{kind,name,contact}` · `option_change_window{opens,closes}` · `doc_hash`

### `employee-benefits.jsonl` † — `living`
`ref` · `person_ref` · `employer` · `kind` (pension/provident/group_life/income_protection/funeral/other_risk) · `member_no` † · `benefit{cents,currency}` or `multiple_of_salary` · `contribution{employee,employer}` · `beneficiaries[]` · `statement_as_at` · `doc_hash`

### `subscriptions.jsonl` — `living`
`ref` · `subject_ref` · `service` · `category` · `amount{cents,currency}` · `frequency` · `started_on` · `renews_on` · `lock_in_until` · `cancellation_route` · `linked_recurring_ref`

### `digital-estate.jsonl` † — `living`
`ref` · `subject_ref` · `kind` (account/device/domain/wallet) · `service` · `username` † · `credential_pointer` · `recovery_pointer` · `two_factor{method,pointer}` · `executor_ref` · `on_death` (transfer/close/memorialise)

> **`credential_pointer` holds a location, never a secret.** Schema `pattern` rejects anything resembling a password, key or seed phrase; the PII hook blocks it too.

### `household.jsonl` † — `living`
`ref` · `kind` (access/firearm/provider) · `description` · `custodian_ref` · `location_hint` · `licence{no,expires,doc_hash}` · `provider{name,contact,service}`

> Access records store *who holds it* and *where it is documented* — never the code itself.

### `leases.jsonl` — `living`
`ref` · `direction` (in/out) · `property_ref` · `counterparty` · `rent{cents,currency}` · `escalation_pct` · `starts_on` · `ends_on` · `deposit{cents}` · `doc_hash`

### `policies.jsonl` † — `insurance`
`ref` · `class` (life/disability/income_protection/dread_disease/funeral/short_term/business) · `subclass` · `insurer` · `policy_no` † · `life_assured_ref` · `owner_ref` · `premium{cents,currency}` · `premium_frequency` · `escalation_pct` · `sum_assured{cents,currency}` · `beneficiaries[]{person_ref,pct}` · `cession{to,kind,doc_hash}` · `waiting_periods[]` · `exclusions[]` · `broker{name,contact}` · `inception_on` · `anniversary_on` · `deemed_property_s3_3_a_ii` · `doc_hash`

### `holdings.jsonl` † — `investments`
`ref` · `owner_ref` · `kind` (ra/preservation/occupational/unit_trust/equity/money_market/crypto/tfsa) · `platform` · `account_no` † · `mandate` · `offshore` · `currency` · `value{cents,currency}` · `value_as_at` · `fees{advice_pct,platform_pct,fund_ter_pct}` · `beneficiaries[]{person_ref,pct}` · `two_pot{savings,retirement,vested}` · `reg28_applicable` · `allocation[]{asset_class,pct}` · `doc_hash`

### `contributions.jsonl` — `investments`
`holding_ref` · `person_ref` · `tax_year` · `amount{cents,currency}` · `kind` (member/employer/lump_sum) · `deductible` · `doc_hash`

### `assets.jsonl` — `assets`
`ref` · `owner_ref` · `owner_entity` · `class` (property/vehicle/valuable/firearm/timeshare/right/other) · `kind` · `description` · `acquired_on` · `base_cost{cents,currency}` · `offshore` · `pledged_to` · `title_deed_location` · `registration_no` · `doc_hash`

### `liabilities.jsonl` † — `assets`
`ref` · `debtor_ref` · `kind` (home_loan/vehicle_finance/overdraft/credit_card/store_account/personal_loan/cellphone/suretyship) · `creditor` · `account_no` † · `balance{cents,currency}` · `balance_as_at` · `rate{kind,pct}` · `instalment{cents,currency}` · `ends_on` · `secured_by` · `surety_for` · `doc_hash`

### `valuations.jsonl` — `assets`
`asset_ref` · `as_at` · `value{cents,currency}` · `basis` (municipal/market/insured/professional/estimate) · `valuer` · `doc_hash`

### `fx-rates.jsonl` — `assets`
`pair` (`USDZAR`) · `rate` · `rate_date` · `source` · `fetched_at`

> Every cross-currency figure in every report names the rate and its date. No silent conversion.

### `tax-events.jsonl` † — `tax`
`ref` · `taxpayer_ref` · `tax_year` · `kind` (itr12/itr14/it12tr/irp5/it3/cgt/donation/dividends_tax/logbook) · `amount{cents,currency}` · `status` (expected/received/filed/assessed/paid/disputed) · `filed_on` · `assessed_on` · `doc_hash`

### `tax-deadlines.jsonl` — `tax`
`ref` · `taxpayer_ref` · `kind` (irp6_1/irp6_2/itr12/itr14/it12tr/vat201/emp201/afs/bo_register) · `period` · `due_on` · `lead_days` · `status` · `rule_ref`

### `wills.jsonl` † — `estate`
`ref` · `testator_ref` · `kind` (will/living_will/wishes/prior_estate/litigation) · `signed` · `signed_on` · `is_joint` · `executor{name,contact}` · `custodian{name,contact}` · `original_location` · `review_triggers[]` · `doc_hash`

### `beneficiaries.jsonl` † — `estate`
`instrument_ref` (→ `policies` \| `holdings` \| `employee-benefits`) · `person_ref` · `pct` · `kind` (nominated/estate/trust) · `nominated_on` · `conflicts_with_will` · `doc_hash`

> `conflicts_with_will` is computed, not entered. When true it becomes a high-priority work item — this is one of the highest-value findings the system produces.

### `trusts.jsonl` † — `trusts`
`ref` · `name` · `mt_number` † · `type` (inter_vivos_discretionary/testamentary/bewind/special) · `founder_ref` · `deed[]{kind,signed_on,doc_hash}` · `loa{issued_on,doc_hash,trustees[]}` · `beneficiaries[]{person_ref,class,capital,income,vested}` · `bo_register{filed_on,doc_hash}` · `year_end` · `fica_accountable`

### `trustees.jsonl` † — `trusts`
`trust_ref` · `person_ref` · `role` · `independent` · `appointed_on` · `resigned_on` · `kind` (appointment/resolution/minutes) · `doc_hash`

### `distributions.jsonl` — `trusts`
`trust_ref` · `beneficiary_ref` · `tax_year` · `amount{cents,currency}` · `nature` (income/capital) · `conduit` · `attributed_to_ref` · `resolution_ref` · `doc_hash`

### `loan-accounts.jsonl` — `trusts`
`trust_ref` · `counterparty_ref` · `direction` · `balance{cents,currency}` · `balance_as_at` · `interest_rate_pct` · `s7c_applicable` · `s7c_deemed_donation{cents,currency}` · `doc_hash`

### `final-wishes.jsonl` † — `final-wishes`
`person_ref` · `disposition` (burial/cremation) · `plot{cemetery,section,number,deed_doc_hash}` · `ashes` · `service{venue,officiant,music,readings,notes}` · `provider{name,contact}` · `thirty_day_liquidity{cents,currency,sources[]}`

### `readiness.jsonl` — `readiness`
`subject_ref` · `requirement` · `category` · `status` (present/absent/expired/not_applicable) · `expires_on` · `doc_hash` · `original_location` · `copies_needed[]{holder,has_copy}` · `weight` · `consequence_if_absent`

> Score is weighted by `consequence_if_absent`, not by count. A missing will outweighs a missing gym contract, and the score has to say so or it is decoration.

### `documents/index.jsonl` — `librarian`
`doc_hash` · `original_path` · `filed_path` · `type` · `domain` · `subject_ref` · `period{from,to}` · `pages` · `ocr` · `ingested_at` · `run_id` · `checksum_verified_at`

## 4. State files

| File | Writer | Contents |
|---|---|---|
| `state/cursors.json` | `orchestrator` | per-stream cursors: inbox, cadence, ledgers, rules |
| `state/queue.json` | `orchestrator` | work items — see [loop.md §3.2](loop.md#32-triage) |
| `state/run-log.jsonl` | `orchestrator` | one line per heartbeat: run_id, started, ended, waves, items, outcome |
| `state/gaps.jsonl` | *all, append-only* | `kind` · `subject_ref` · `domain` · `detail` · `blocking` · `opened_run` · `closed_run` |
| `state/agents/<name>.json` | that agent | last_run · cursor · health · open_loops · known_gaps · confidence · pending_questions |
| `state/system/issues.jsonl` | `orchestrator` (sync) | GitHub mirror — `number` · `title` · `state` · `labels[]` · `milestone` · `assignees[]` · `url` · `created_at` · `updated_at` · `synced_at` · `local_only`. **System work only; contains no personal data by construction** ([github.md](github.md)) |
| `state/audit.jsonl` | `vault-audit` hook | every vault mutation: tool, path, bytes, run_id, timestamp — plus every **blocked** egress attempt (web or `gh`), recording the matched pattern *class*, never the value |

## 5. Memory files

| Path | Horizon | Format |
|---|---|---|
| `memory/short/*.md` | session + 7 days | free-form markdown, dated filenames |
| `memory/medium/*.md` | ~90 days | markdown with a `horizon:` front-matter date |
| `memory/long/*.md` | durable | markdown, one topic per file, `confidence:` and `since:` front matter |
| `memory/audit.jsonl` | permanent | `action` (promote/demote/expire/merge/flag) · `from` · `to` · `reason` · `run_id` |

All four are **human-readable and hand-editable**. `/consolidate` must preserve hand edits; a consolidation that mangles them is a failed run.

## 6. POPIA — classification, retention, erasure

Purpose limitation and minimality are design constraints, not aspirations. Every category below has a documented erasure path that includes **derived artefacts**, because deleting a source document while its numbers survive in a dashboard is not erasure.

| Category | Sensitivity | Purpose | Retention | Erasure path (`/forget`) |
|---|---|---|---|---|
| Names, relations, DOB | medium | graph identity | while relevant | tombstone in `people`; rewrite refs to `per_redacted_<n>`; rebuild graph, reports |
| ID / passport numbers | **high** | tax, estate, FICA | while legally required | field-level redaction in place; `documents/` original quarantined then shredded on confirmation |
| Contact details | medium | notification lists | while relevant | field-level redaction; regenerate notify lists |
| Bank account numbers | **high** | statement matching | 5 years (tax) | mask to last 4; re-key `transactions` by `account_ref` only |
| Transactions | medium | analysis | 5 years (tax) | delete by `account_ref` + period; rebuild dashboards and net worth |
| Medical scheme, member no. | **high (special)** | cover analysis | while a member + 5 years | full record delete; regenerate health-cover map |
| Health condition inferences | **high (special)** | never inferred | n/a | *the system does not derive health conditions from claims data* |
| Policy / holding numbers | **high** | reconciliation | policy life + 5 years | mask; keep `ref` only |
| Credential pointers | medium | digital estate | while account exists | delete row; pointer never contained a secret |
| Trust records | high | administration | statutory | delete by `trust_ref`; regenerate compliance calendar |
| Wills, final wishes | **high** | succession | until superseded | supersede, then delete on confirmation |
| Journal, memory | medium | continuity | rolling per tier | `/forget` scans and redacts across all three tiers plus `CLAUDE.md` |
| GitHub issues | **none by construction** | system backlog | indefinite | n/a — personal data may never reach GitHub; if it ever does, `/forget` reports it as **unremovable** and tells you to treat it as disclosed |
| Source documents | **high** | provenance | as per category | quarantine → confirm → shred; index row keeps hash and a `redacted` tombstone |

**`/forget <subject>` reports three things:** what it removed, what it retained and under which legal basis, and what it **could not** remove (an emailed report, a printed copy, a bank's own records). Honesty about the limits of erasure is part of the erasure.

## 7. Validation

- `templates/schemas/*.json` are JSON Schema 2020-12.
- Python validates with `jsonschema` at write time inside `tools/py/ledger.py`.
- Node validates with `ajv` inside hooks and `pre-commit`, where startup time matters.
- **A record that fails validation is never written to a ledger.** It goes to `proposed/rejected/` with the validation error attached, and a gap record is opened.
