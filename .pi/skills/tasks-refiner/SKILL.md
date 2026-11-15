---
name: tasks-refiner
description: >
  Work protocol for refiner board workers ([board-refiner-v1]). Refine the
  card named in your entry prompt (top non-`refined` card in the Spec lane)
  in place per the canonical template, preserving all human intent, and
  assign it the correct type tag. Park it in AskUser with a `## Refinement`
  section if there are open points, or mark it `refined` (AskUser) when done.
  One card per session. Board facts live in the tasks-board skill — read that
  first.
---

# tasks-refiner

The **refiner** refines free-form prose cards in the `Spec` lane into the
canonical card structure, so that implementer/reviewer iterations work only on
best-practice, correctly-typed cards. This skill is the **work protocol**
only. Board facts — lanes, the `tmd` CLI, lane ownership, card format, log
format, the priority queue, and the single-Active guardrail — live in the
**`tasks-board`** skill. Read `tasks-board/SKILL.md` first; it is the shared
entry point for every board worker.

Your role is assigned by the orchestrator via the entry prompt
(`[board-refiner-v1]` = refiner). You never infer your role from board state.

## What the refiner is (and is not)

The refiner is a **third worker role upstream of the implementer/reviewer
loop**, running in the same single-slot orchestrator loop (orchestrator.py
launches at most one `pi` worker at a time — no concurrency). It does **no
implementation**: no repo checkout, no code, no feature branch. Its only
output is a **refined card in place** (the card is the deliverable).

- **Input:** a card the human moved into `Spec` — free-form prose, or already
  template-aligned.
- **Output:** the same card, restructured into the canonical template
  (`.pi/skills/tasks-board/card-template.md` — the single source of truth,
  **no copy in this skill dir**), correctly *typed* (`spec` / `research` /
  none = implementation), with all open points resolved or deferred to the
  human.

**Session cwd:** the entry prompt may note that the session cwd is the
card's repo checkout (the orchestrator resolves it from `## Repo` — see
tasks-board, *Worker cwd for repo cards*). The refiner reads the repo's
code there **read-only** (or from `work/orchestrator/<name>` when the cwd
is the stack root) — it never edits it.

## Permissions (hard boundary)

- ✅ read the card, read the canonical template, edit/move the **named** card
  (`tmd` only: `tmd edit` / `insert` / `append` / `tag` / `move`).
- ❌ **never** touch any lane other than `Spec` and `AskUser`. Never touch
  `Backlog` / `Ready` / `Active` / `OnHold` / `Review` / `Done`.
- ❌ **never** edit code, skills, agents, config, or the repo. **Never**
  commit. **Never** check out a repo (the refiner works on the card, not the
  repo — even when the card carries a `## Repo` section).

**Lane permissions: `Spec` and `AskUser` only.** The refiner works the card
**in place in `Spec`** (it never moves before the worker boots — there is no
pre-launch pull), and parks it in `AskUser` whenever it needs the human.

## The canonical template (single source of truth)

The target structure is `.pi/skills/tasks-board/card-template.md` — read it
before refining. Do **not** copy it into this skill dir (a second copy would
drift). The refiner *references* the canonical path and reshapes the card to
match it: tag line → H1 (identical to the card name) → `## Story` → optional
`## Repo` → optional `## LLM` → `## Acceptance criteria` → optional
`## Breakdown` → `## Links` → `## Notes` → `## Log` (always last).

## Content preservation (G7 — the bounded exception)

Every other role "never rewrites the human-written spec". The refiner is the
**one bounded exception**: it *transforms* spec prose into the standard
structure. The rule that keeps this safe:

- **Preserve ALL human intent, requirements, and decisions.** Every
  requirement, constraint, decision, and open question in the original prose
  must be present in the refined card — reworded and restructured, never
  dropped.
- **Content-preservation check (mandatory before parking/done):** re-read the
  original prose and confirm each requirement has a home in the refined card
  (Story / Acceptance criteria / Notes / Links). If one is missing, restore it
  before moving the card.
- The implementer's "never rewrite the spec" rule then applies to the
  **refined** spec as-is — the refiner's output *is* the spec the implementer
  works from.

## Type tag (part of the refinement output)

As part of refining, assign the correct **type tag** on line 1 (via `tmd
tag`):

- `spec` — repo-based spec (`## Repo` required; the implementer works the repo
  read-only and delivers the spec in the card).
- `research` — findings / brainstorming (`## Repo` optional; read-only).
- **none** — implementation card (default: feature branch, merge to dev).

The refined card is a correctly *typed* card. If the prose implies a type the
human did not state and it is not obvious, that is an **open point** (ask in
the refinement section — do not guess).

## The `## LLM` section (worker model choice)

The canonical template defines an optional `## LLM` section (`- Model:
<model-id>`) for cards that need a non-default worker model (e.g. pentesting
→ an uncensored model). The refiner introduces it the same way it introduces
`## Repo` — when the prose implies it:

- **Semantic model mention in the prose** (e.g. "this task demands an
  uncensored agent") → resolve it to the **exact model ID** from the
  template's "known models" appendix. The refiner reads the canonical
  template before refining — that appendix is the single source of truth for
  the card-facing vocabulary. **No model vocabulary is hardcoded in this
  skill** (a second copy would drift), and the refiner does **not** probe
  live `/v1/models` (it stays a card transformer, not a system integrator).
- **Unresolvable or ambiguous mention** (unknown term, or a term that fits
  more than one model) → **open point** in the refinement section (context +
  the exact decision needed + options with a recommendation — the human
  confirms the exact ID).
- **No mention** → no `## LLM` section (the pi default applies; the refiner
  adds nothing).

The section is independent of `## Repo` (a card can have both, either, or
neither).

## Refinement rounds (the core loop)

The refiner works in **rounds**. Each round either resolves the card (→ done)
or surfaces new open points to the human (→ AskUser). Convergence is
guaranteed by the human in the loop — **no round cap**.

### Round N — open points found

1. Read the card + the canonical template.
2. Restructure the card in place (tmd only), preserving all human intent
   (G7), and assign the type tag.
3. Collect the **new** open points — gaps, decision points, contradictions,
   missing type, missing `## Repo` for a `spec` card, ambiguous acceptance
   criteria. (Each round asks only *new* points; already-answered ones are
   merged, not re-asked.)
4. Insert a `## Refinement — round N (DD.MM.YYYY HH:MM)` section **before the
   Log section** (`tmd insert`), with **numbered points**, each = **context +
   the exact decision needed + options with a recommendation**:

   ```markdown
   ## Refinement — round 1 (DD.MM.YYYY HH:MM)

   1. **<point title>** — <context: what the card says / what is missing>.
      **Decision needed:** <the exact decision>. **Options:** (a) …; (b) … —
      **Recommendation:** (a) because …
   2. **<point title>** — …
   ```

5. Append a `**Question**` log entry (one-line summary + pointer to the
   Refinement section) + a `**Moved** Spec → AskUser: open points in
   Refinement round N` log entry.
6. `tmd move` the card to `AskUser`.

### Round N+1 — card back in `Spec` with the human's answers

The human edits the answers into the card (in the Refinement section or
inline) and moves it back to `Spec` (the G2 unblock rule). The refiner:

1. **Merge** the human's answers into the card structure — `## Story` /
   `## Acceptance criteria` / `## Notes` / `## Links` as appropriate. This is
   a real **merge, not a simple append**: fold each answer into the section
   that owns it, reword for consistency, and close the point.
2. **Remove the `## Refinement` section** (it is disposable — see below).
3. Append a `**Result**` log entry (one-line: "merged round N answers into
   <sections>; refinement section removed").
4. If **more** open points remain → go to *Round N+1 — open points found*
   (new Refinement section, new round number, → AskUser).
5. If **no** open points remain → *Done* (below).

### Done — no more open points

1. Remove any `## Refinement` section (there must be **none** in the final
   card).
2. Add the `refined` tag: `tmd tag <card> --add refined` (a **state flag**
   like `ai-reviewed` — added once, **never removed**; the orchestrator's
   Spec scan skips `refined` cards, so the card is ignored until the human
   moves it to `Ready`/`Backlog`).
3. Append a `**Result**` log entry ("Refinement done, card ready for
   implementation") + a `**Moved** Spec → AskUser: refined — ready for
   implementation` log entry.
4. `tmd move` the card to `AskUser` with the one-line "Refinement done, card
   ready for implementation".

**Why AskUser (not `Ready`):** moving a finished card straight to `Ready` is a
hazard — the orchestrator's pre-launch pull takes the top `Ready` card
quickly (within one scan tick + cooldown), so implementation could start
before the human decides. `AskUser` is the decision point: the human moves the card to
`Ready` (implement now) or `Backlog` (later).

### Already template-aligned cards — quick validation pass

If the card is **already** in the canonical structure (tag line, H1, Story,
Log last, no prose to restructure): do a **quick validation pass** — check the
structure and the **type tag** (assign it if absent/ambiguous), run the
content-preservation check trivially (nothing to preserve), then add `refined`
and move to `AskUser` ("Refinement done — card was already template-aligned").
No Refinement section, no round.

## The refinement section is disposable

The `## Refinement` section is the **in-progress state** of refinement (the
single source of truth — there is deliberately no second "in-progress" tag,
which would drift from it). It is **disposable**: it must **NEVER be present
in a final card** after refinement rounds. Every exit path (merge, done,
validation pass) removes it. A `## Refinement` section surviving into `Review`
is a defect the reviewer flags as a **blocking** finding (see
`tasks-reviewer`).

## Log every move

Every lane move gets its own `**Moved** X → Y: reason` entry — the park to
`AskUser` and any return. Timestamps are `DD.MM.YYYY HH:MM` (local time),
always with the date. A parked card must be resumable **cold** from its Log
alone (the Log + the Refinement section tell the human exactly what to answer
and where the card returns).

**Canonical log format.** Every entry is exactly ONE bullet line, timestamp
first — see the `tasks-board` skill, *Log format (canonical, strict)*.
`tmd append`/`insert`/`edit` validate newly written Log lines and refuse the
write on violation.

**Anchor hygiene**: never write the literal `## Log` in content sections,
refinement sections, or log entries — refer to it as "the Log section".

## Worker mode (orchestrator)

When launched as an orchestrator refiner (headless session, eGPU brain):
refine **exactly one card** — the one named in your entry prompt (top
non-`refined` card in `Spec`) — refine it in place, park it in `AskUser`
(with a Refinement section if there are open points) or mark it `refined`
(`AskUser`) when done — then **end the session**. One card per session. The
orchestrator does **no pre-launch pull** for the refiner (the card stays in
`Spec` until the refiner moves it); the exit timer arms when the card leaves
`Spec`.
