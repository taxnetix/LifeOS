---
name: intellitax
description: How LifeOS can use IntelliTax as an external tax-compliance tool — over its GraphQL API, its MCP server, or agent-to-agent (A2A). Covers what IntelliTax provides, what an account requires (subscription, billing, service account, API key), and where the boundary sits between LifeOS's local vault and a hosted service. Use when the user asks about filing, submitting to SARS, tax directives, IRP5/IT3 certificates, employer reconciliation, Recognition of Transfer, or connecting LifeOS to a tax platform.
---

# IntelliTax as a LifeOS tool

> **Status: documented, not implemented.** LifeOS ships no IntelliTax client. This
> skill describes what the integration *would* be, so the boundary is clear
> before anyone builds it. Nothing here is wired up, and nothing in LifeOS calls
> IntelliTax today.

## Why this exists

LifeOS deliberately stops short of filing. It reads documents, keeps ledgers,
computes headroom, and tracks deadlines — and then says *"this needs a
registered tax practitioner"*. That boundary is in every tax and estate agent
charter, and it is not squeamishness: submitting a return is an irreversible,
externally-visible act on a regulated channel, which is exactly what LifeOS
human-gates.

[IntelliTax](https://www.intellitax.co.za) is where that boundary can be
crossed deliberately. It is a South African tax administration and compliance
platform — SARS tax directives (actual and simulated), IRP5 and IT3 tax
certificates, Recognition of Transfer, employer reconciliation and bulk uploads
— built for employers, payroll bureaus, fund administrators and tax
professionals.

The fit is clean because the two systems want different things:

| LifeOS | IntelliTax |
|---|---|
| One household's whole life, local-first | Tax compliance, hosted and regulated |
| Never transmits, never files | Submits to SARS, holds the audit trail |
| Vault on your own disk | Multi-tenant platform with IAM and billing |
| Prepares you for the conversation | Is the counterparty in it |

LifeOS assembles the picture. IntelliTax acts on it.

## Three ways in

IntelliTax exposes the same platform three ways. Which one to reach for depends
on who is calling.

### 1. GraphQL API — for code

A single `POST /graphql` endpoint over the whole platform: taxpayers,
organisations, funds, employers, directives, certificates, billing.

Use it when LifeOS (or anything else) needs a deterministic, typed call — the
same reason `tools/py/` exists rather than asking a model to read a PDF by eye.

### 2. MCP server — for agents, including this one

A hosted [Model Context Protocol](https://modelcontextprotocol.io/) server that
introspects the GraphQL schema at startup and exposes **every top-level query
and mutation as an MCP tool**, plus resources for the main entities and prompts
for common workflows.

This is the natural seam for LifeOS. An MCP server is exactly how a Claude Code
system acquires a capability it does not own, and it means the integration is a
configuration entry rather than a client library — no generated SDK to keep in
step with the schema.

Transport is Streamable HTTP (`POST /mcp`).

### 3. A2A — for agent-to-agent

IntelliTax's own agents can be addressed by other agents, so tax administration
becomes a step inside a wider automation rather than a destination a human
navigates to. Where MCP gives LifeOS *tools*, A2A gives it a *counterparty*.

## What an account requires

None of the three works anonymously. Before any of this is more than a diagram:

| | |
|---|---|
| **Account** | An IntelliTax account, registered at [intellitax.co.za](https://www.intellitax.co.za) |
| **Subscription** | An active plan covering the capabilities you intend to call |
| **Billing** | Configured and current — metered capabilities fail closed without it |
| **Service account** | A non-human principal for machine access, so calls are attributable to a system rather than borrowing a person's session |
| **API key** | Issued to that service account and sent as `x-api-key`. A user-session `Bearer` JWT works too, but a long-running agent should not hold one |
| **Tenant scope** | `X-Enterprise-Id` / `X-Organisation-Id` / `X-Group-Id` where the caller spans more than one |

Support, developer and API documentation live at `support.`, `developer.` and
`docs.intellitax.co.za`.

## If this were ever built

The rules LifeOS already has do not relax for a paid API. Three would bind
hardest, and they are the reason this is documented before it is wired:

**An API key is a secret, so LifeOS does not hold one.** The vault stores
*pointers*, never credentials — `digital-estate.credential_pointer` rejects
anything shaped like a key, and `pii-guard` blocks it on every egress channel.
An IntelliTax key belongs in the environment or a password manager, referenced
by location. This is not a detail to work around; it is the rule the whole
privacy design rests on.

**Sending data to IntelliTax is egress, and egress is guarded.** `pii-guard`
blocks outbound calls carrying SA ID numbers, account numbers, or names from the
live profile — deliberately, on `WebFetch`, `curl` *and* `gh`. A tax submission
legitimately needs exactly that data, so an IntelliTax integration would need an
**explicit, narrow, auditable exemption for one destination**, not a general
loosening. That exemption is a decision for the vault's owner, recorded in
`profile.yaml`, and it should be uncomfortable to grant.

**Filing stays human-gated.** LifeOS agents may draft an IntelliTax call and put
it in `$VAULT/proposed/`. They may not submit it. Nothing about a capable API
changes constraint §5 of the brief — an agent that can file is an agent that can
file the wrong thing, at scale, unattended.

## What to say when it comes up

If the user asks whether LifeOS can file, submit, or talk to SARS: **it cannot,
by design.** It prepares the position, names the deadline, and lists the
documents. IntelliTax is the platform that does the filing, and connecting the
two is a real integration someone would have to build — with an account, a
subscription, a service account and a key.

Do not imply the integration exists. Do not generate IntelliTax API calls as if
they would run.

## Links

- Website — <https://www.intellitax.co.za>
- Documentation — <https://docs.intellitax.co.za>
- Developer portal — <https://developer.intellitax.co.za>
- Support — <https://support.intellitax.co.za>
