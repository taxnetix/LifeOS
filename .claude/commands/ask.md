---
description: Answer a question across every domain, with citations to your own documents.
argument-hint: "<question>"
allowed-tools: Bash, Read, Grep, Glob, Task
---

# /ask $ARGUMENTS

Answer across every domain, from the ledgers — **never from recollection of this conversation**.

## Gather

!`.venv/bin/python -m lifeos.status`

Then read the ledgers the question actually touches. Delegate to the owning domain agent when the question needs judgment rather than lookup.

## Cite everything

Every factual claim names its source: the record id, the document, and the locator. `/audit --trace <record-id>` walks any of them back to a page. If you cannot cite it, you cannot claim it.

## Distinguish four things, visibly

1. **What the documents say** — quoted, with hash and page.
2. **Arithmetic derived from them** — with the formula shown.
3. **Suggestions** — marked as such.
4. **Matters needing a professional** — a registered financial advisor, tax practitioner, attorney, or the Master's Office.

## When you don't know

Say so, plainly, and **open a gap record**. "I don't know" is a first-class answer here and always better than an inference dressed as a fact. If the answer is partly knowable, give the part you can evidence and name precisely what is missing.

Watch for the near-miss: a figure that exists but is *stale*, or a rule that applies but is *unverified*. Both need saying — an answer computed from a year-old tax table is not wrong so much as untrustworthy, and the user cannot tell which unless you say.

## Rules

- Money is never estimated. If the ledger does not have it, it is a gap.
- Never state a tax rate, limit or threshold from memory — read `.claude/rules/`, and give its "as at" date.
- Personal and business are separate views; say which one you answered for.
