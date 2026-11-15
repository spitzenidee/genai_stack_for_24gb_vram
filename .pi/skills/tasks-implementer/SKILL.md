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
     **OnHold chain convention:** a condition must be mechanically
     verifiable. The canonical form for chained cards: the predecessor card
     has the `ai-reviewed` tag AND is in the `Review` or `Done` lane (verify
     with `tmd list` + `tmd get <Lane/card>` line 1 — see the tasks-board
     skill, *OnHold chain condition*). Non-canonical conditions (legacy
     prose, external conditions like "gitea reachable") are still judged
     worker-side as today.
     **Note:** the orchestrator pre-checks canonical tag-based conditions
     before launching a scan worker (scan hot-loop guard): a satisfied
     canonical card is pulled into `Active` by the orchestrator itself (you
     work it as a normal Active card), and an all-canonical-blocked OnHold
     lane launches no worker at all. You only scan when a non-canonical
     condition is present (or the pre-check could not run).
3. **Single-Active guardrail**: there is at most **one** card in `Active`.
   `tmd claim` enforces it (refuses when `Active` is not empty); a manual
   `tmd move` into `Active` is only valid when `Active` is empty (verify
   first).
4. **Not in the queue**: `AskUser` (the human is the unblocker) and `Review`
   (the human owns it). Never judge an `AskUser` card as "answered" yourself;
   never pull from `Review`.

## Work protocol (working the current card)

**First check — `merge-pending`:** if the card is tagged `merge-pending`, do
NOT implement — it is a follow-up step after a clean review. Run the *Merge &
push* protocol (below), then end the session.

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
  If the change touches code/containers/scripts/dependencies, add the
  `vuln-scan` tag (`tmd tag <card> --add vuln-scan`) before submitting to
  Review.
  On (re)submission to `Review`, tag via **`tmd tag <card> --add review-by-ai
  --remove ai-reviewed`** (the AI-review request flag; `ai-reviewed` must be
  absent) — never `tmd edit`/`sed` on line 1. See the tag lifecycle in
  `tasks-reviewer`.
- **Images**: `tmd img name.png < file`, then embed `![](_api/image/name.png)`
  in the card.

Content sections (e.g. `## Result`) go in with `tmd insert` (it places them
before the Log section and validates the result — never hand-splice with
`tmd edit`); log entries are appended at the end with `tmd append`. The Log
section is a single section and is always last. **Anchor hygiene**: never
write the literal `## Log` in content sections, review tables, or log
entries — refer to it as "the Log section". Never rewrite the
human-written spec.

## Repo setup (cards with a `## Repo` section)

**Session cwd may already be the checkout:** the entry prompt notes when
the session cwd is the card's repo checkout (the orchestrator resolves it
from `## Repo` — see tasks-board, *Worker cwd for repo cards*). In that
case the canonical checkout is `.` — verify it (`git status`,
`git fetch origin`) and work there; do NOT clone into a subpath.

Before working a card that has a `## Repo` section (name, remote, base
branch), ensure the canonical checkout:

1. **Path:** `work/orchestrator/<name>` (relative to the stack root).
2. **Absent** → `timeout 60 git clone <remote> work/orchestrator/<name>`.
3. **Present** → `timeout 30 git fetch origin`. On fetch failure (gitea
   briefly down): note it in the card and proceed on the local state.
4. **Remote unreachable AND repo absent** → cannot start: append the
   condition + `**Moved** Active → OnHold: condition` → `move` to `OnHold`
   (condition: gitea remote reachable; verify:
   `timeout 15 git ls-remote origin <base>`).
5. **Then, by card type:**
   - `spec` / `research` → stay on the base branch, **read-only** (no
     branches, no commits, no edits) — see *Non-implementation cards*.
   - implementation (default) → create a feature branch from the base:
     `git checkout -b feat/<slug> <base>` — **all** work happens on it.

## Non-implementation cards (`spec` / `research`)

Cards tagged `spec` or `research` produce **content in the card**, not code:

- **No writes to the repo** — no edits, no branches, no commits. Read and
  learn from it (code, tests, docs); verify claims against the actual state.
- **`spec`:** the card must be **self-contained for a fresh implementer** —
  verified code anchors, closed decisions, constraints, and a testable
  definition of done. A spec that an implementer must re-derive is not done.
- **`research`:** findings + options + recommendations, for the human to
  decide on. If you find a fixable problem: **document it, do not fix it** —
  a new card is the vehicle for the fix.
- **Completion:** `**Result**` + `**Moved** Active → Review` as usual, with
  the `review-by-ai` tag. These cards **never** receive `merge-pending`
  (there is nothing to merge).

## Merge & push (cards tagged `merge-pending`)

A `merge-pending` card is a **follow-up step after a clean review** — no new
implementation. The card's Result/Review sections name the feature branch
and the base branch (default `dev`). Work in `work/orchestrator/<name>`:

1. **Verify** the card is tagged `merge-pending` and the tree is clean
   (`git status`); if dirty, commit/stash the leftovers onto the feature
   branch and log it.
2. **Merge:** `git checkout <base>` → `git merge --ff-only <feature>`. On
   failure (base moved) → plain `git merge <feature>` (merge commit) and
   **re-run the test suite** (mandatory after a merge commit).
3. **Delete the feature branch:** `git branch -d <feature>` (local only —
   feature branches are never pushed to the remote).
4. **Push if the remote is up:** `timeout 15 git ls-remote origin <base>`:
   - reachable → `timeout 60 git push origin <base>`, log it.
   - **unreachable (gitea down)** → record it in the card (log entry + the
     exact push command in a note) and park: `**Moved** Active → OnHold:
     condition` (condition: gitea remote reachable; verify:
     `timeout 15 git ls-remote origin <base>`). A later session that claims
     the cleared card **resumes at this step** (the Log shows merge done +
     branch deleted — do NOT re-run steps 2–3): run the push, log it, then
     step 5.
5. **Finish (push succeeded):** remove the tag
   (`tmd tag <card> --remove merge-pending`), move the card to `Review`
   (keep `ai-reviewed`, ensure `review-by-ai` is absent — a mechanical merge
   of already-reviewed code needs no re-review). **Exception:** if the merge
   needed conflict resolution that changed code → remove `ai-reviewed` and
   re-add `review-by-ai` (the changed code must be re-reviewed).
6. **Log every step** (merge, branch deletion, push or OnHold, tag, move) —
   a parked card must be resumable cold.

## Bounded shell commands (no unbounded shells)

Ad-hoc verification scripts and shell commands are a known hang source: an
unbounded blocking command never returns a tool result, so the pi session
blocks with no model inference and the board stalls (see the 45-min hang RCA
on the "Bound worker shell commands (timeout)" card). Rules:

- **Wrap blocking commands in `timeout`.** Any shell command that can block —
  FIFO opens, `read` from pipes/TTY, port waits, long-running tests — MUST be
  wrapped in `timeout` (e.g. `timeout 30 bash test.sh`). Never run an unbounded
  blocking command directly.
- **`docker run` on a server-entrypoint image hangs (and `timeout` orphans it).**
  Some images (e.g. `tasks-md`) have an ENTRYPOINT that `exec`s a long-running
  server and ignores its args — so `docker run --rm <image> sh -c '…'` starts
  the server and never returns; a `timeout` then kills only the client and
  leaves an **orphaned container** running. To inspect a file inside such an
  image, override the entrypoint (`docker run --rm --entrypoint cat <image>
  /path`) or read the host-mounted copy (e.g. `tasks.md/config/…`) instead.
  (RCA: the "flow-only tags" card stalled ~82 min on this, 05.11.2026.)
- **No unbounded background shells for tests.** Never launch a background shell
  that is not bounded. If a background shell is genuinely needed, bound it
  (e.g. `timeout`) and verify it finished before ending the session.
- **FIFO semantics.** A FIFO open-for-write blocks until a reader appears, and
  one reader pairs with one writer per open — a one-shot writer cannot serve
  multiple reads. A FIFO test with no reader, or a one-shot writer serving
  several reads, deadlocks; always pair each writer with a live reader and
  bound the whole thing in `timeout`.

## Worker mode (orchestrator)

When launched as an orchestrator worker (headless session, eGPU brain): work
on **exactly one card** — pick it via the priority queue, work it, park it
(AskUser/OnHold) or complete it (Review) — then **end the session**. Do not
re-run the queue for the next card; the orchestrator launches a fresh worker
for that (one card per session).
