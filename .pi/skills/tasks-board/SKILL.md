---
name: tasks-board
description: >
  Board protocol for the tasks.md board (localhost:8090) via the tmd CLI.
  Board facts: lanes, tmd commands, lane ownership, card format, log format,
  priority queue, single-Active guardrail, role dispatch, repo workflow.
  Shared entry point for every board worker — the role-specific protocol
  lives in its own skill. Use when the user says "check the board",
  "work the board", "any tasks?", or references board lanes or board tickets.
---

# tasks.md board

Board: `http://localhost:8090`. CLI: `./scripts/tmd` in this skill dir
(co-located with `scripts/tmd.py`; the wrapper runs it in a transient
`python:3.12-slim` container on the host network — works in every stack
mode). Usage: `tmd -h`.

## Commands (stateless — the board is the source of truth)

| Command | Effect |
|---|---|
| `tmd list` | all lanes + cards in stored order, one line per lane |
| `tmd get <Lane/card.md>` | print card markdown |
| `tmd new-card <Lane/card.md>` | create card from stdin (validates structure + Log; `--force` for repair). `--template` renders from the canonical template (`card-template.md`: title + canonical `Created` log line); `--tag spec\|research` sets the type tag; `--actor agent\|human` |
| `tmd sync-template` | refresh the mirror card `Backlog/TEMPLATE CARD` from the canonical template (one-way file → card; preserves the mirror's Log) |
| `tmd append <Lane/card.md>` | append stdin to card |
| `tmd tag <Lane/card> --add <t>… --remove <t>…` | edit line-1 tags **surgically (line 1 only, no full-card rewrite)**; idempotent, self-heals comma-joined groups, owns the one-group-per-tag format, validates names. `--add`: **flow tags only** (allowlist: `review-by-ai`, `ai-reviewed`, `merge-pending`, `vuln-scan`, `refined`, `spec`, `research`); `--remove`: any tag (incl. legacy). **The only way to change tags.** |
| `tmd insert <Lane/card.md>` | insert a content section (stdin) **before the last exact `## Log` line** (body quotes can't mislead it); cards without a `## Log` header get it appended at the end |
| `tmd check <Lane/card.md>` | validate (stateless): P2 (structure) + P3 (Log format — see *Log format (canonical, strict)*). Exit 0 = OK, 1 = violations with line numbers |
| `tmd edit <Lane/card.md> [--force]` | replace card content from stdin; **validates new content (P2)** — refuses if it would orphan `## Log`; `--force` overrides |
| `tmd move <src> <dst>` | move card (dst may be `Lane/` to keep name); auto-updates sort |
| `tmd claim <Lane/card>` | verify `Active` empty, move card into `Active`, print its content |
| `tmd to-top <Lane/card.md>` | move card to top of its lane (highest priority) |
| `tmd reorder <Lane> <a,b,c,…>` | set a lane's order (top→bottom); unlisted cards keep their order |
| `tmd rm <card \| Lane>` | delete |
| `tmd img <name>` | upload image from stdin, prints `_api/image/<name>` |

**Always `tmd list` fresh before acting** — the user moves cards in the UI at any time; never assume last-seen state. The in-card Log is the agent's journal, not official history.

**Ordering = priority** (top = highest): set it with `tmd to-top` / `tmd reorder` — never hand-edit the sort map. Card paths may omit `.md` (`move`/`new-card`/`append`/`edit`/`insert`/`claim` add it); `rm` keeps `.md`.

## Lane ownership

- **Human lanes** `Backlog`, `Ready` (Ready = human→AI handover) — **never touch Backlog**.
- **AI lanes** `Active`, `OnHold`, `Review`, `Done`.
- **Handover lanes** `Spec` (human→AI→human) and `AskUser` (AI→human→AI). `Spec` is written **only** by the refiner (in place, via `tmd` only) — it refines free-form prose cards into the canonical structure (G1); humans move cards into `Spec` and read the result back.
- **Lane moves are the agent's job**, with three human exceptions:
  - `AskUser` answered → user edits the answer in and `move`s the card to `Ready` (top, if it should resume with priority) — **except** an answered *refinement* card (came from `Spec`, carries a `## Refinement` section) goes back to **`Spec`** (G2).
  - `OnHold` condition cleared → the *agent* moves it to `Active`; the user *may* also `move` it to `Ready`.
  - `Review` → user moves it to `Ready` (feedback in the card) or `Done`.

## Card format

**Card names (filenames):** no `< > : % " / \ | ? *` (UI refuses, validator `/[<>:%"/\\|?*]/g`); `%` additionally 500s every update/move server-side; no leading `.` (dotfiles are filtered — ghost card, invisible in UI and API). Everything else is fine (`{`, `}`, `;`, `#`, umlauts, emoji, …). `tmd` enforces the same set on every board path; a card with a bad name can no longer be moved via the API — rename it on disk.

Line 1: **zero or more flow tags, one bracket group per tag** (empty line 1 = no tags, valid) — **never comma-join** (no `[tag:a,b]`). Line 1 is reserved for flow tags (the `tmd tag` allowlist) — topics/projects belong in the Story. `refined` is a **state flag**: added once by the refiner, never removed — the Spec scan skips `refined` cards (G5). Tags change **only via `tmd tag`** (never `tmd edit`/`sed`). After line 1: H1 title, the human-written spec (never rewrite it), content sections (e.g. `## Result`, optional `## Repo`/`## LLM`), and the Log — timestamped entries: `**Created**`, `**Moved** X → Y: reason`, `**Question**`, `**Result**`. Timestamps: **`DD.MM.YYYY HH:MM`** (local time, always include the date). A parked card must be resumable **cold** from its log.

Section order is canonical: tag → H1 → spec/content sections → Log. The Log is **single** and **always last**. Content goes in **before** the Log — never between log entries.

**Anchor hygiene**: never write the literal `## Log` in content sections, review tables, or log entries — refer to it as "the Log section".

**Card template:** the canonical template is `card-template.md` in this skill dir (single source of truth, version-controlled). The board card `Backlog/TEMPLATE CARD` is a **read-only UI mirror** (copy-paste source) — refresh it with `tmd sync-template`, never hand-edit it.

### Log format (canonical, strict)

Every Log entry is **exactly ONE bullet line**, timestamp first, in one of two forms:

- General: `- DD.MM.YYYY HH:MM **Action** — one-line summary (details in <section>)`
- Moved: `- DD.MM.YYYY HH:MM **Moved** <src> → <dst>: reason`

Rules:
1. **Bullets are mandatory.** One line per entry — never a run-on paragraph.
2. **One-line summary.** Long content (questions, results, findings) goes into a content section (e.g. `## Result`, `## Question — <date>`); the log entry is a one-line summary + pointer to that section.
3. `tmd append` is the only way to add log entries.
4. **Mechanical validation.** The write path (`tmd append`/`insert`/`edit`) validates **newly written** Log lines: canonical entry regex, non-decreasing timestamps, no consecutive duplicates; on violation the write is refused with the offending line numbers (`--force` overrides for deliberate repair). Pre-existing old-format entries are **grandfathered** (validation is scoped to the newly written delta). The standalone `tmd check` is **stateless** — it validates the **whole** Log section and labels non-matching entries `[old-format]`. The card still FAILs on them: the write path is the primary gate, `tmd check` the backstop.

## Protocol notes

- **Bulk card transforms** (any scripted/`tmd edit` rewrite) must verify **content preservation line-by-line** (diff old vs. new), not only grep for the target pattern (D2).
- **UI saves reformat the card.** The tasks.md UI normalizes card bytes on save. Agents always use `tmd` (never the UI editor) (D6).
- **Bounded shell commands.** Blocking ad-hoc commands (FIFO opens, `read` from pipes/TTY, port waits, long tests) must be wrapped in `timeout`; never launch unbounded background shells for tests. Full rule: `tasks-implementer` (*Bounded shell commands*).

## Repo workflow (board fact)

Cards that touch a repo carry a `## Repo` section (name, remote, base branch). Board facts for all repo work:

- **Canonical checkout path:** `work/orchestrator/<repo_name>` (relative to the genai_stack root; `work/*` is gitignored). The implementer owns the checkout (clone/fetch) — see `tasks-implementer` (*Repo setup*).
- **Worker cwd for repo cards (board fact):** the orchestrator resolves the worker's launch cwd from the trigger card's `## Repo` section: plain `Name` (no path separators) + existing `work/orchestrator/<name>` checkout → cwd = that checkout (session lands in the repo's Hindsight bank, `coding-agent::<name>`); `Name` = the stack repo's own basename → cwd = the stack root (the live stack root IS that repo's checkout); no `## Repo` / missing checkout / invalid name → cwd = the stack root (launch never fails on cwd resolution; anomaly logged when `## Repo` is present but unusable). Applies to all three worker modes. From a checkout cwd the board skills load via `--skill <stack>/.pi/skills` (a checkout has no `.pi`); the tmd CLI is invoked via the skill-dir path (cwd-independent). The entry prompt notes the checkout cwd (the worker's repo-setup step operates on `.`).
- **Remotes** are the project's Git server (local Gitea) — the exact URL is in the card's `## Repo` section (do not hardcode the host). Push to that `origin` **only** — never the `github` mirror remote.
- **Base branch `dev` is the AI merge target.** Merging to `main` is the human's job — the loop never touches `main`.
- **Card type tags** (line 1): `[tag:spec]` (repo-based spec — `## Repo` required, read-only repo access) / `[tag:research]` (findings / brainstorming — `## Repo` optional, read-only) / no type tag = implementation (default, feature branch).
- **`[tag:merge-pending]`** is a workflow-state tag (request/ack model): the reviewer adds it on a clean pass of a repo implementation card; the implementer removes it after the merge & push step. Humans never set it.
- **Feature branches are local-only** — never pushed; only `dev` is pushed.

## LLM choice (board fact)

Cards that need a non-default worker model carry an optional `## LLM` section (independent of `## Repo`):

- **Format:** a single `- Model: <model-id>` line; `<model-id>` is the **bare** llama-server model ID (no provider prefix — `://` breaks the `provider/id` split in `--model`; the `egpu-`/`igpu-` prefix encodes the server; IDs are globally unique).
- **The orchestrator** parses the section at launch and passes `--model <model-id>` to pi. Absent → pi default (`egpu-SWIFT-1.5`), silently. Present but invalid (not in the known-models allowlist) → pi default **+ anomaly log** — a launch never fails on model choice.
- **The known-models vocabulary** (model IDs + semantic aliases) lives in the canonical card template's "known models" appendix (`.pi/skills/tasks-board/card-template.md`) — the single source of truth. The refiner resolves semantic model mentions to these IDs (see `tasks-refiner`); the orchestrator's `KNOWN_MODELS` allowlist is the validity gate at launch.

## Priority queue (board fact)

The order in which lanes are scanned for the next workable card (within a lane, position = priority, top = highest):

1. **`Active`** — a disrupted card needing continuation.
2. **`Spec`** — the **first** card (top→bottom) **without** the `refined` tag (refined cards are skipped, not blockers — hot-loop guard, G5). The refiner works it **in place** (no pre-launch pull — it stays in `Spec` until the refiner moves it).
3. **`Review`** — the **first** card (top→bottom) tagged `review-by-ai` (clean cards are skipped, not blockers) — drain the review queue; the human approves (Review → Done stays the final checkpoint).
4. **`Ready`** — the top card.
5. **`OnHold`** — the **first** card (top→bottom) whose condition is cleared. A blocked card does not shield the cleared ones below it.

The **orchestrator** performs this scan at launch and pulls a `Ready` trigger into `Active` itself (pre-launch pull, plain HTTP — the card is in its target lane before the worker boots). **OnHold pre-check (scan hot-loop guard):** before an OnHold trigger launches a worker, the orchestrator cheaply classifies each OnHold card's condition (plain HTTP, no container, no LLM), recognizing only the canonical tag-based form (above): a **satisfied** canonical condition is pulled `OnHold → Active` by the orchestrator itself (the worker works it as a normal Active card); if **every** condition is canonical and **none** satisfied, the launch is skipped. **Non-canonical** conditions (legacy prose, external) still launch a scan worker: the cleared-check stays worker-side and the worker claims the first cleared card with `tmd claim`. The pre-check is an optimization, not a gate.

`AskUser` is **not** in the queue (see lane ownership). The single-Active guardrail (below) applies to any move into `Active`.

### OnHold chain condition (board fact)

The canonical condition for chained cards:

> **Condition:** the predecessor card has the `ai-reviewed` tag AND is in the `Review` or `Done` lane.
> **Verify:** `tmd list` shows the predecessor in the `Review` or `Done` lane, AND `tmd get <Lane/card>` line 1 contains `[tag:ai-reviewed]`.

Properties: mechanically verifiable, merge-aware (a repo implementation card reaches "Review + ai-reviewed" only after the merge-pending step, so the successor's feature branch is based on the correct base), monotonic (stays true after the human approves the predecessor → Done). Edge: after a merge that changed code, the predecessor returns to Review with `review-by-ai` and WITHOUT `ai-reviewed` — during the post-merge re-review the condition is temporarily false and the successor waits. Non-canonical conditions (legacy prose, external) are judged worker-side.

## One card at a time (single slot)

The stack's llama.cpp servers (igpu, egpu) each have **exactly one model slot** (`--models-max 1`): **at most one card in `Active` at a time**, and the agent works on **one card at a time, sequentially**.

**Parked cards hold no slot and block nothing.** `AskUser` and `OnHold` are park states: after parking a card, continue with the next card in the queue. In-flight = `Active` only.

## Role dispatch

The worker's **role is assigned by the orchestrator via the entry prompt** — the agent never infers its role from board state.

| Entry-prompt marker | Role | Protocol skill |
|---|---|---|
| `[board-worker-v1]` | implementer | `tasks-implementer` |
| `[board-reviewer-v1]` | reviewer | `tasks-reviewer` |
| `[board-refiner-v1]` | refiner | `tasks-refiner` |

This skill is the **shared entry point** (lanes, `tmd` CLI, lane ownership, card format, log format, priority queue, single-Active guardrail, repo workflow). After reading it, follow the role-specific skill for your protocol.
