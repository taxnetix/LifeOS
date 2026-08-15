"""LifeOS leaf tools.

Determinism lives here; judgment lives in .claude/skills/.  Nothing in this
package orchestrates — every module is invoked by an agent, does one thing,
prints JSON, and exits.  See docs/adr/0004-tools-compute-skills-judge.md.
"""

__version__ = "0.1.0"
SCHEMA_BASE = "https://lifeos.local/schemas"
