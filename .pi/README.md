[Back to main README](../README.md)

# Agent skills (`.pi/skills/`)

## TL;DR

`.pi/skills/` is the stack's agent-skills directory: one subdirectory per skill, each a
`SKILL.md` (frontmatter + protocol, plus optional assets/scripts) that the pi coding
agent loads when a task matches the skill's description. This file is the index — every
skill with a one-line description. You touch it when you want to see what the agents on
this stack can do, find the protocol a board worker follows, or add a new skill.

## What & why

The stack's agentic loop (the [orchestrator](../orchestrator/README.md) driving the
[tasks.md board](../tasks.md/README.md)) works because the workers' intelligence lives
in **skills**, not in the orchestrator: the orchestrator only dispatches, each worker
session loads its role skill and follows it. Skills are the unit of agent capability on
this stack — a self-contained, version-controlled instruction set (with assets and
helper scripts) that any pi session in this repo can pick up.

## How it works

- A skill is a directory under `.pi/skills/` with a `SKILL.md`: YAML frontmatter
  (`name` + `description`) followed by the protocol. Optional siblings: `assets/`,
  `scripts/`, `references/`.
- The pi agent discovers project skills from `.pi/skills/` and loads the one whose
  `description` matches the current task.
- The board-worker skills form a chain: `tasks-board` (the shared board facts — lanes,
  `tmd` CLI, card format, priority queue) is the entry point; the role skills
  (`tasks-implementer` / `tasks-refiner` / `tasks-reviewer`) carry the
  role-specific work protocol.

## The skills

| Skill | What it does |
|---|---|
| `tasks-board` | Board protocol for the tasks.md board (localhost:8090) via the `tmd` CLI — the shared entry point for every board worker. |
| `tasks-implementer` | Work protocol for implementer board workers (`[board-worker-v1]`) — work one card per session, park it or complete it. |
| `tasks-refiner` | Work protocol for refiner board workers (`[board-refiner-v1]`) — refine `Spec`-lane cards in place per the canonical template. |
| `tasks-reviewer` | Review protocol for reviewer board workers (`[board-reviewer-v1]`) — review from all angles, document findings, never fix. |
| `vuln-scan` | Vulnerability scanning (Trivy SCA, Semgrep CE SAST, ShellCheck, slopsquatting) in transient containers — tag-triggered in the review phase. |
| `gromacs-sim` | State machine + deterministic gates for end-to-end GROMACS MD simulations on this stack (2026.3 HIP build). |
| `gromacs-kb-audit` | Audits the GROMACS knowledge base against the local `gromacs-rocm` build — documents issues in `issues_kb.md`, never fixes KB files. |
| `gromacs-kb-fix` | Fixes open GROMACS KB issues against the local `gromacs-rocm` build — re-verifies every fix, never commits. |
| `aa-mutation-advisor` | Expert advisor for protein / amino-acid chemistry and site-directed mutagenesis design, grounded in the quantitative AAindex knowledge base. |

## Related

- The board the worker skills drive: [tasks.md/README.md](../tasks.md/README.md)
- The orchestrator that launches the workers: [orchestrator/README.md](../orchestrator/README.md)
- Per-component READMEs whose "Related" sections reference these skills:
  [gromacs/README.md](../gromacs/README.md), [orchestrator/README.md](../orchestrator/README.md),
  [tasks.md/README.md](../tasks.md/README.md)
- Main README: [../README.md](../README.md)

[Back to main README](../README.md)
