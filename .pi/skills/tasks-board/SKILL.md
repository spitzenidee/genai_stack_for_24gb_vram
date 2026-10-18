---
name: tasks-board
description: >
  Board protocol for the tasks.md board (localhost:8090) via the tmd CLI.
  Board facts: lanes, tmd commands, lane ownership, card format, log format,
  priority queue, single-Active guardrail, role dispatch. The shared entry
  point for every board worker — the role-specific protocol (implementer /
  reviewer) lives in its own skill. Use when the user says "check the board",
  "work the board", "any tasks?", or references board lanes (Ready, Active,
  AskUser, OnHold, Review) or board tickets.
---

# tasks.md board

Board: `http://localhost:8090`. CLI: `./scripts/tmd` in this skill directory
(co-located with `scripts/tmd.py`; the wrapper runs it in a transient
`python:3.12-slim` container on the host network, so it works in every stack
mode). On a usage error: `tmd -h`.

## Commands (stateless — the board is the source of truth)

| Command | Effect |
|---|---|
| `tmd list` | all lanes + cards in stored order, one line per lane |
| `tmd get <Lane/card.md>` | print card markdown |
| `tmd new-card <Lane/card.md>` | create card, content from stdin |
| `tmd append <Lane/card.md>` | append stdin to card |
| `tmd insert <Lane/card.md>` | insert a content section (markdown via stdin) **before the last exact `## Log` line** (body quotes in backticks/tables/code fences can't mislead it); cards without a `## Log` header get it appended at the end (with a note) |
| `tmd check <Lane/card.md>` | structural validation (P2): tag line on line 1, H1 present, at most one standalone `## Log` heading, `## Log` last; + Log format (P3): canonical entry regex, non-decreasing timestamps, no consecutive duplicates (stateless, whole Log section — non-matching entries labeled `[old-format]`, i.e. grandfathered legacy entries); exit 0 = OK, 1 = violations with line numbers |
| `tmd edit <Lane/card.md> [--force]` | replace card content, from stdin; **validates the new content (P2)** — refuses if it would orphan the `## Log` header; `--force` overrides with a loud warning |
| `tmd move <src> <dst>` | move card (dst may be `Lane/` to keep name); auto-updates sort |
| `tmd claim <Lane/card>` | claim for work: verify `Active` is empty, move card into `Active`, print its content (one call) |
| `tmd to-top <Lane/card.md>` | move card to the top of its lane (highest priority) |
| `tmd reorder <Lane> <a,b,c,…>` | set a lane's card order (top→bottom); unlisted cards keep their order after |
| `tmd rm <card \| Lane>` | delete |
| `tmd img <name>` | upload image from stdin, prints `_api/image/<name>` for embedding |

**Always `tmd list` fresh before acting.** The user moves cards in the UI at
any time; never assume last-seen state. In-card `## Log` is the agent's
journal, not official history.

**Ordering = priority.** Card order within a lane *is* the priority (top =
highest). To set it, use `tmd to-top` / `tmd reorder` — never hand-edit the
sort map. Card paths may omit the `.md` suffix (`move`/`new-card`/`append`/
`edit`/`insert`/`claim` add it); `rm` keeps `.md` to tell a card from a lane.

## Lane ownership

- **Human lanes** `Backlog`, `Spec`, `Ready` (Ready = human→AI handover) —
  **never touch Backlog/Spec**.
- **AI lanes** `Active`, `OnHold`, `Review`, `Done`.
- **Handover lane** `AskUser` (AI→human→AI).
- **Lane moves are the agent's job**, with three human exceptions — the user
  is the *unblocker*:
  - `AskUser` answered → user edits the answer in and `move`s the card to
    `Ready` (top, if it should resume with priority).
  - `OnHold` condition cleared → the *agent* moves it to `Active`; the user
    *may* also `move` it to `Ready` (not required).
  - `Review` → user moves it to `Ready` (feedback in the card) or to `Done`
    (approved).

## Card format

Line 1: `[tag:<project>]`. Then H1 title, the human-written spec (never
rewrite it), content sections (e.g. `## Result`), and `## Log` — timestamped
entries for every agent action: `**Created**`, `**Moved** X → Y: reason`,
`**Question**`, `**Result**`. Timestamps are **`DD.MM.YYYY HH:MM`** (local
time) — always include the date, so entries from different days never
collide. A parked card must be resumable **cold** from its log alone.

Section order is canonical: tag → H1 → spec/content sections → `## Log`.
`## Log` is a **single** section and is **always last** in the card. When work
produces content (e.g. a `## Result` section), insert it **before** `## Log`
— never between log entries. Log entries are appended at the end of the card
(so `tmd append` is the natural tool for log entries); content sections are
inserted with `tmd insert` (it places them before `## Log`). `tmd edit`
(full replace) validates the new content the same way (P2).

**Anchor hygiene**: never write the literal `## Log` in content sections,
review tables, or log entries — refer to it as "the Log section".

### Log format (canonical, strict)

Every Log entry is **exactly ONE bullet line**, in one of two forms
(timestamp first — scannable + mechanically checkable chronology):

- General: `- DD.MM.YYYY HH:MM **Action** — one-line summary (details in <section>)`
- Moved (lane transitions — the most common entry): `- DD.MM.YYYY HH:MM **Moved** <src> → <dst>: reason`

Rules:
1. **Bullets are mandatory.** One line per entry — never a run-on paragraph.
2. **One-line summary.** Long content (questions, results, findings) goes into a content section (e.g. `## Result`, `## Question — <date>`); the log entry is a one-line summary + pointer to that section.
3. `tmd append` is the only way to add log entries.
4. **Mechanical validation.** The write path `tmd append`/`tmd insert`/`tmd edit` validates **newly written** Log lines: canonical entry regex, non-decreasing timestamps, no consecutive duplicates. On violation the write is refused with the offending line numbers (`--force` overrides for deliberate repair). Pre-existing old-format entries are **grandfathered**: validation is scoped to the newly written delta, so editing a legacy card never fails on old lines. The standalone `tmd check` is **stateless** — it validates the **whole** Log section and labels non-matching entries `[old-format]` (grandfathered legacy entries; a new malformed entry is labeled the same way — distinguish by position/timestamp). The card still FAILs on them: the write path is the primary gate, `tmd check` the backstop.

## Protocol notes

- **Bulk card transforms** (any scripted/`tmd edit` rewrite of a card's content) must verify **content preservation line-by-line** (diff old vs. new), not only grep for the target pattern — a transform that silently drops lines is a data-loss bug (D2).
- **UI saves reformat the card.** The tasks.md UI normalizes card bytes on save (harmless but deterministic). Agents always use `tmd` (never the UI editor); humans should expect a UI save to reformat the card (D6).

## Priority queue (board fact)

The order in which lanes are scanned for the next workable card (within a
lane, position = priority, top = highest):

1. **`Active`** — a disrupted card needing continuation (it was the most
   recent work).
2. **`OnHold`** — the **first** card (top→bottom) whose condition is cleared.
   A blocked card does not shield the cleared ones below it.
3. **`Ready`** — the top card.

The **orchestrator** performs this scan at launch time and pulls a `Ready`
trigger into `Active` itself (pre-launch pull, plain HTTP — the card is in
its target lane before the worker boots; the worker gets a card-specific
entry prompt). The `OnHold` condition check stays worker-side (judgment);
the worker claims the first cleared card with `tmd claim`.

`AskUser` and `Review` are **not** in the implementer's queue (see lane
ownership). The single-Active guardrail (below) applies to any move into
`Active`.

## One card at a time (single slot)

The stack's llama.cpp servers (igpu, egpu) each have **exactly one model
slot** (`--models-max 1`). Therefore there is **at most one card in `Active`
at a time**, and the agent works (implements/thinks) on **one card at a
time, sequentially**.

**Parked cards hold no slot and block nothing.** `AskUser` (waiting on the
human) and `OnHold` (waiting on a condition) are park states: after parking a
card, continue with the next card in the queue (below). In-flight = `Active`
only.

## Role dispatch

The worker's **role is assigned by the orchestrator via the entry prompt** —
the agent never infers its role from board state. Each session is unambiguous
and testable.

| Entry-prompt marker | Role | Protocol skill |
|---|---|---|
| `[board-worker-v1]` | implementer | `tasks-implementer` (work protocol) |
| `[board-reviewer-v1]` | reviewer | `tasks-reviewer` (review protocol) |

This skill (`tasks-board`) is the **shared entry point**: it carries the board
facts above (lanes, `tmd` CLI, lane ownership, card format, log format,
priority queue, single-Active guardrail). After reading it, follow the
role-specific skill for your protocol.
