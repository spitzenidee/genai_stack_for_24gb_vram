---
name: tasks-implementer
description: >
  Work protocol for implementer board workers ([board-worker-v1]). Work the
  card named in your entry prompt (pulled into Active at launch; OnHold via
  tmd claim), log every move, park it (AskUser/OnHold) or complete it
  (Review). One card per session. Board facts (lanes, tmd CLI, card format,
  log format, priority queue, single-Active guardrail) live in the
  tasks-board skill — read that first.
---

# tasks-implementer

The **implementer** works cards on the tasks.md board. This skill is the
**work protocol** only. Board facts — lanes, the `tmd` CLI, lane ownership,
card format, log format, the priority queue, and the single-Active guardrail —
live in the **`tasks-board`** skill. Read `tasks-board/SKILL.md` first; it is
the shared entry point for every board worker.

Your role is assigned by the orchestrator via the entry prompt
(`[board-worker-v1]` = implementer). You never infer your role from board
state.

## Board check protocol (pick the next card)

The orchestrator pulls `Ready` cards into `Active` **at launch time**
(pre-launch pull, plain HTTP — the card is in its target lane before you
boot). Your entry prompt names the card already in `Active` (or the `OnHold`
lane to scan). You never select from `Ready`.

1. `tmd list` (always fresh — the user moves cards in the UI at any time).
2. **Move/claim first, read second.** The first board action after picking a
   card is the one that puts it in `Active` — *before* any deep reading or
   investigation:
   - Entry prompt names **`Active/<card>`** → it is already in `Active`
     (pulled in at launch, or a disrupted continuation). Verify it is still
     there, then work it from its Log.
   - Entry prompt names the **`OnHold`** lane → scan top→bottom; the
     **first** card whose condition is **cleared** (check mechanically; the
     card's Log states how to verify) → **`tmd claim OnHold/<card>`** (one
     call: verifies `Active` is empty, moves the card in, prints its
     content), then work it. A blocked card does not shield the cleared ones
     below it. None cleared → log it, end the session (the cards stay
     parked; the orchestrator's OnHold cooldown prevents hot-looping).
3. **Single-Active guardrail**: there is at most **one** card in `Active`.
   `tmd claim` enforces it (refuses when `Active` is not empty); a manual
   `tmd move` into `Active` is only valid when `Active` is empty (verify
   first).
4. **Not in the queue**: `AskUser` (the human is the unblocker) and `Review`
   (the human owns it). Never judge an `AskUser` card as "answered" yourself;
   never pull from `Review`.

## Work protocol (working the current card)

**Log every move.** Every lane move gets its own `**Moved** X → Y: reason`
entry — the pickup (`→ Active`) as well as the move that ends the phase
(park / completion). The orchestrator performs the Ready→Active pickup at
launch time; you still log it (`**Moved** Ready → Active: pulled in at
launch`). Timestamps are `DD.MM.YYYY HH:MM` (local time), always with the
date. A parked card must be resumable **cold** from its Log alone.

**Canonical log format.** Every entry is exactly ONE bullet line, timestamp
first, in the general (`- DD.MM.YYYY HH:MM **Action** — summary`) or Moved
(`- DD.MM.YYYY HH:MM **Moved** <src> → <dst>: reason`) form — see the
`tasks-board` skill, *Log format (canonical, strict)*. One-line summary +
pointer to a content section for long content; bullets are mandatory. `tmd
append`/`tmd insert`/`tmd edit` validate newly written Log lines and refuse
the write on violation, so a malformed entry fails at write time, not in a
later review pass.

- **Blocked on a user decision** → append `**Question** — …` (self-sufficient:
  context + the exact decision needed) + `**Moved** Active → AskUser: reason`
  → `move` to `AskUser`.
  (When the user is present, also ask in chat; if they answer in chat, act
  immediately — `move` the card to `Active` and continue.)
- **Blocked on an external condition** → append the condition + how to verify
  it + `**Moved** Active → OnHold: condition` → `move` to `OnHold`.
- **Done** → append `**Result** — what changed + how to verify` +
  `**Moved** Active → Review: reason` → `move` to `Review`.
  On (re)submission to `Review`, **ensure the card is tagged `review-by-ai`**
  (the AI-review request flag) and that `ai-reviewed` is absent — see the
  tag lifecycle in `tasks-reviewer`.
- **Images**: `tmd img name.png < file`, then embed `![](_api/image/name.png)`
  in the card.

Content sections (e.g. `## Result`) go in with `tmd insert` (it places them
before the Log section and validates the result — never hand-splice with
`tmd edit`); log entries are appended at the end with `tmd append`. The Log
section is a single section and is always last. **Anchor hygiene**: never
write the literal `## Log` in content sections, review tables, or log
entries — refer to it as "the Log section". Never rewrite the
human-written spec.

## Worker mode (orchestrator)

When launched as an orchestrator worker (headless session, eGPU brain): work
on **exactly one card** — pick it via the priority queue, work it, park it
(AskUser/OnHold) or complete it (Review) — then **end the session**. Do not
re-run the queue for the next card; the orchestrator launches a fresh worker
for that (one card per session).
