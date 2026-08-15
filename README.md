# LifeOS

**Know where you stand.** Drop your bank statements, policies and tax
certificates into a folder. LifeOS reads them, keeps track of what you have,
and tells you what needs attention.

It is built for South Africa: SARS, the March to February tax year, Reg 28,
estate duty, the Master's Office. Personal and business are treated as one
connected picture.

> **Status: finished and working.** Documents come in and get filed with a
> record of where every number came from. Statements turn into a sorted picture
> of your spending, a dashboard and a ranked list of things worth fixing. Your
> medical scheme, gap cover, work benefits and personal policies get read
> together, so you can see where you are covered twice and where you are not
> covered at all. Tax deadlines run off dated SARS tables that flag themselves
> when they go stale. And the estate model answers the question families
> actually hit: not whether the estate is solvent, but whether anyone can get
> hold of cash in the first thirty days.

## What you need first

LifeOS runs inside **Claude Code**, Anthropic's app for letting Claude read and
write files on your own computer. It is a different thing to the Claude website
or the phone app. [Get Claude Code](https://claude.com/claude-code) before you
start.

Once you have it, everything else is just a folder.

## Three steps, about ten minutes

**1. Get the LifeOS folder.**
[Download the ZIP](https://github.com/taxnetix/LifeOS/archive/refs/heads/main.zip)
and unzip it, or clone it if you use git.

**2. Open that folder in Claude Code.** Everything LifeOS needs is already
inside it. Nothing to install, nothing to sign up for.

**3. Type `/lifeos-init` and press enter.** Words starting with a slash are
commands. You type them into Claude Code the same way you would type a message.
Typing just `/` shows you the whole list.

That first command asks you a few questions and sets your folder up. After
that, put a document in `vault/inbox/` and type `/heartbeat`.

### If you are comfortable with a terminal

Cloning lets you add the extra tools that read PDFs and turn the Life File into
a printable document. Everything else works fine without them.

```bash
git clone https://github.com/taxnetix/LifeOS.git && cd LifeOS
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt
npm install
bash tools/scripts/install-hooks.sh      # stops your documents being shared. Do this.
```

If you took the ZIP route, `install-hooks.sh` has nothing to install into. The
safety check is a git hook, and an unzipped folder is not a git repository. If
you later run `git init` in there, install the hook before your first commit.

## Two folders, kept apart

```
life-os/     THE SYSTEM   this repo. Shareable, MIT, no personal data in it.
vault/       YOUR STUFF   your real life. Never uploaded. Stays on your machine.
```

Set `$LIFEOS_VAULT` if you want your vault somewhere else. Every agent looks it
up the same way, so nothing has a folder path baked in.

## Commands

| | |
|---|---|
| `/lifeos-init` | Ask you questions, set up your folder, pick what you need |
| `/boot` | Where you stand, what is next, what LifeOS needs from you |
| `/heartbeat` | One pass. Safe to run as often as you like |
| `/status` · `/selftest` | How the system is doing · run all its own tests |
| `/ingest` | Go through the inbox now |
| `/readiness` | Your Life File score, and the quickest way to improve it |
| **`/life-file`** | **The document you hand your family when you die** |
| `/dashboard` · `/optimise` | Spending dashboard · ranked, costed suggestions |
| `/review cover` | **All your cover in one view**, which no single document gives you |
| `/review <area>` | A proper look at one area |
| `/deadlines` | Everything due, with how long each one takes and why it applies |
| `/ask` · `/what-if` · `/life-event` | Ask anything · model a scenario · record a life change |
| `/trust-review` | Section 7C, trustee independence, keeping the trust separate |
| `/install-pack` | List, add or remove an optional area |
| `/issues` | The system's own to-do list on GitHub |
| `/consolidate` · `/audit` · `/add-domain` · `/forget` | Tidy its memory · prove where a number came from · add an area · delete a person's data |

Full details: [docs/commands.md](docs/commands.md).

## Meet the agents

An agent is simply a set of written instructions for one job. There are 17 of
them, each a file in [`.claude/agents/`](.claude/agents/), each written to the
same template: what it looks after, what it stays out of, when it runs, and what
counts as finished. **Only one agent can change any given record.** A test
checks this every time and fails if two agents ever end up in charge of the same
thing.

### The machinery

Six agents that run the system rather than your data.

| Agent | What it does | Runs on |
|---|---|---|
| **`orchestrator`** | Runs each cycle and decides what happens next. The only one allowed to hand work to the others, so nothing runs behind its back. | `/heartbeat` |
| **`librarian`** | Sorts your inbox. Files each document, names it, spots duplicates and passes it to the right agent. Never changes or deletes an original. | `/ingest`, any new file |
| **`memory-keeper`** | Remembers what LifeOS has learned about you and drops what has gone stale. When two things contradict, it shows you both instead of picking one. | `/consolidate` |
| **`meta-architect`** | Looks after LifeOS itself: new areas, tidy-ups, bug reports. It cannot see your documents, which is why it is the one allowed to post in public. | `/add-domain`, `/issues` |
| **`analyst`** | Does the maths for everyone else: totals, trends, projections, what-ifs. Keeps no records of its own and shows its working every time. | On request |
| **`visualiser`** | Builds the dashboards and reports. Each is a single file that opens in any browser with no internet needed. | `/dashboard` |

### Your life

Eleven agents, each in charge of one area.

| Agent | What it looks after | Runs on |
|---|---|---|
| **`identity`** | Everyone in the picture: you, your spouse, children, dependants and your companies, plus how they all connect. Everything else hangs off this one. | ID documents, a new person |
| **`finance`** | Bank accounts, transactions, debit orders, budgets. Turns a pile of statements into a sorted picture of your spending. | Statements, `/dashboard`, `/optimise` |
| **`living`** | Medical aid and gap cover, work benefits, subscriptions, online accounts, leases, and who holds your spare keys. | Medical and benefit statements |
| **`insurance`** | Every policy you hold: life, disability, income protection, dread disease, funeral, car and home. Finds where you are covered twice and where you are not covered at all. | Policy schedules, `/review insurance` |
| **`investments`** | Retirement annuities, pension and provident funds, unit trusts, shares, offshore, tax-free savings and crypto. Watches what the fees cost you. | Investment statements |
| **`assets`** | Property, cars, valuables, and everything you owe. Including any surety you have signed, which is the one people forget and the one that hurts most. | Title deeds, bond and vehicle papers |
| **`tax`** | Deadlines, medical credits, how much more you can still put into retirement, tax-free savings limits. It gets you ready. It does not file anything. | IRP5, IT3(b), assessments, `/deadlines` |
| **`estate`** | Your will, who inherits what, what winding up the estate costs, and whether your policy beneficiaries match your will. | Wills, `/review estate` |
| **`trusts`** | Trustees, resolutions, beneficiaries, loan accounts and the yearly section 7C bill. Optional. Add it only if you have a trust. | Trust deeds, `/trust-review` |
| **`final-wishes`** | Burial or cremation, the plot, funeral contacts, and how your family gets hold of cash in the first month. | `/life-file` |
| **`readiness`** | Scores how ready your paperwork is, says what is missing, and writes the Life File. | `/readiness`, `/life-file` |

Every agent finishes by answering three questions: what do I now know that I
did not, what is still missing, and what would make me more useful next time.
Those answers become the next round of work. Full details:
[docs/agent-catalogue.md](docs/agent-catalogue.md).

## What makes it different

**It checks in on its own.** You do not have to remember to run it. It spots a
policy about to expire or a deadline coming up, not just new files. When
nothing has changed it says so and stops, which costs almost nothing.

**Every number shows its source.** Take any figure in any report and you can
see the document it came from, down to the page. When LifeOS is not confident
it read something properly, it asks you rather than guessing. `/audit` walks any
number back to the page it came off.

**It admits what it does not know.** Anything missing goes on a list of gaps.
You will not find an invented figure, or a zero sitting where nobody checked.

**Your details stay on your computer.** A built-in guard blocks anything going
out that contains an ID number, an account number or a name from your profile.
The guard is code, so it still works when the AI gets something wrong.

**It reports its own bugs.** When a bank changes its statement layout or a tax
table goes out of date, LifeOS raises an issue about *itself* on GitHub. Those
issues never mention anything about you, and the same guard enforces that.

**It never quotes a tax rate from memory.** Rates and thresholds live in dated
files that say where they came from and whether a human has checked them. The
ones shipped are marked unchecked, written from memory rather than confirmed
against SARS, so anything built on them arrives with that warning attached.
LifeOS will tell you its own tax tables are a year out of date, because they
are.

**It sees what no single document says.** Your medical scheme covers hospital.
Your gap policy covers what the scheme leaves. Your employer covers part of your
income, and a personal policy covers a part that may not stack with it. None of
those documents mentions the others. `/review cover` reads them together.

## The Life File

The main thing LifeOS makes: **a document you can hand to your family.** It
comes in three versions, depending on who is reading.

| Version | Who it is for | Numbers shown |
|---|---|---|
| First 48 Hours *(default)* | whoever finds it | none at all |
| Executor Pack | executor, spouse, attorney | last 4 digits only |
| Sealed Annexure | the executor, on death | in full, and only if asked for by name |

No passwords, PINs or safe codes at any version. LifeOS says *where* a
credential is kept, never what it is. Its first section is **"What your family
will NOT find"**: the will you never signed, the missing title deed, the surety
nobody knew about. Listing only the sorted parts would give your family false
comfort. [ADR-0018](docs/adr/0018-life-file-document.md).

**Have a look at a real one.** Straight out of LifeOS, built from a made-up
vault: [Tier 1](site/examples/life-file-tier1-first-48-hours.pdf) ·
[Tier 2](site/examples/life-file-tier2-executor-pack.pdf) ·
[what to look at](site/examples/README.md). Tier 3 shows full numbers, so there
is no published example of it.

## Optional areas

Extra bundles that layer onto the core rather than forking it, so one fix
reaches every installation.

```
/install-pack install trusts
```

`trusts` is the first: the trust register, trustees and their independence,
resolutions, beneficiaries, loan accounts, **section 7C**, distributions, and
the Master and SARS calendar. Adding a pack gives you the machinery and none of
anyone else's records. [ADR-0019](docs/adr/0019-packs-merge-not-fork.md).

## Roadmap

| Phase | | Status |
|---|---|---|
| 0 | Design, agent list, record shapes, decisions | Done |
| 1 | The loop, the safety hooks, the vault, 4 system agents | Done |
| 2 | Reading documents, the readiness score, the Life File | Done |
| 3 | Money: statements to dashboard to suggestions | Done |
| 4 | Cover and savings: insurance, medical, investments, the gaps | Done |
| 5 | Tax and estate: SARS tables, duty and cash-in-30-days | Done |
| 6 | Trusts, installable on its own | Done |
| 7 | `/ask`, `/what-if`, life events, memory, adding your own areas | Done |

## IntelliTax

LifeOS never submits anything to SARS. It reads documents, keeps records, works
out the numbers and tracks deadlines, then tells you when you need a registered
practitioner. [IntelliTax](https://www.intellitax.co.za) is where that part
happens, over its API, its MCP server, or agent to agent.

The [`intellitax` skill](.claude/skills/intellitax/SKILL.md) describes how the
connection would work and what it would need: an account, a subscription,
billing and an API key. **There is no IntelliTax code inside LifeOS today.** It
is a documented path, not a shipped feature.

Site: **<https://taxnetix.github.io/LifeOS/>**

## Documentation

[docs/README.md](docs/README.md) tells you what to read in what order. Start
with [architecture](docs/architecture.md) and [the loop](docs/loop.md). The
[18 decision records](docs/adr/README.md) explain every choice that would be
expensive to undo.

## Safety

Read [SECURITY.md](SECURITY.md) before you put real documents in a vault.

## Licence

MIT. See [LICENSE](LICENSE). The licence covers the system. Your vault is
yours.
