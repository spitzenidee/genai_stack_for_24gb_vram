---
name: tasks-reviewer
description: >
  Review protocol for reviewer board workers ([board-reviewer-v1]). Review
  the card named in your entry prompt (first eligible Review card, tagged
  review-by-ai), from all angles, document findings in a ## Review section,
  apply the tag changes, and move/park the card. One card per session. The
  reviewer never fixes — it only documents. Board facts live in the
  tasks-board skill — read that first.
---

# tasks-reviewer

The **reviewer** reviews cards in the `Review` lane. This skill is the
**review protocol** only. Board facts — lanes, the `tmd` CLI, lane ownership,
card format, log format — live in the **`tasks-board`** skill. Read
`tasks-board/SKILL.md` first; it is the shared entry point for every board
worker.

Your role is assigned by the orchestrator via the entry prompt
(`[board-reviewer-v1]` = reviewer). You never infer your role from board
state.

## Permissions (hard boundary)

- ✅ read code/filesystem, run the project's test suite (read-only
  validation), edit/move cards (`tmd`).
- ❌ **never** edit code, skills, agents, or config; **never** commit;
  **never** move cards to `Done`.

The reviewer **never fixes** — it only documents issues and, where applicable
and advised, potential fixes. The human is the final approver.

## Picking a card

The orchestrator already picked the card: your entry prompt names the
**first eligible Review card** (top→bottom, tagged `review-by-ai`).

1. `tmd list` (always fresh) — verify the named card is still in `Review`
   and tagged `review-by-ai` (the user may have moved it in the UI).
2. Named card gone / untagged → scan the `Review` lane **top→bottom** for
   the first card tagged `review-by-ai`. Position = priority (exactly like
   Ready). A card without the tag (e.g. already clean with `ai-reviewed`)
   is **skipped**, not a blocker — so 1–n tagged cards anywhere in Review
   are all reviewed, highest first.
3. Nothing eligible → done (end the session).

## Tag lifecycle (request/ack model)

Two tags with distinct roles:

- `review-by-ai` — "AI review requested / ready for AI review" (a *request*
  flag). Added by whoever (re)submits the card to Review (implementer or
  human). **Removed by the reviewer on completion.** This is the
  orchestrator's eligibility signal.
- `ai-reviewed` — "AI review completed, no noteworthy issues" (a *state*
  flag, for the human). Added by the reviewer **only on a clean pass**.
  Informational — not part of eligibility.

| Step | Actor | Tag changes | Lane |
|---|---|---|---|
| 1. (Re)submit to Review | implementer / human | + `review-by-ai` (ensure `ai-reviewed` absent) | → `Review` |
| 2a. Review finds issues | reviewer | − `review-by-ai` | → top of `Ready` |
| 2b. Review finds no issues | reviewer | − `review-by-ai`, + `ai-reviewed` | stays in `Review` |
| 3. Fix + re-submit (after 2a) | implementer | + `review-by-ai` (ensure `ai-reviewed` absent) | → `Review` |
| 4. Human approves (after 2b) | human | — | → `Done` |

**Loop prevention:** the reviewer removes `review-by-ai` on completion, so a
card cannot be re-reviewed until it is re-submitted (step 3 re-adds it).

## Scan phase (vuln-scan) — at the start of review

Before reviewing the content, run the vulnerability scan if warranted
(skill: `vuln-scan`):

- **Trigger:** the card is tagged `vuln-scan` on line 1, **or** the
  reviewer judges a scan warranted (safety net — e.g. the change touches
  code/containers/scripts and the tag is missing).
- **Run:** `.pi/skills/vuln-scan/scripts/vuln-scan.sh repo <repo>`
  (default: the stack root). If the card touched a Dockerfile / built an
  image, also run `vuln-scan image <name>`.
- **Record:** add a `**Vuln-scan:**` line to the `## Review` section —
  count by severity + the findings that are in the card's **changed**
  files (the actionable ones). The full JSON stays in
  `work/vuln_scan_results/` (gitignored, never committed); cite the report
  path.
- **Verdict guidance:** CRITICAL/HIGH findings in the card's changed code
  = **blocker** (row in the findings table). Pre-existing MEDIUM findings
  = noted in the `**Vuln-scan:**` line, not blocking.
- Pure spec/content/GROMACS/Blender cards with no tag → no scan.

## Review protocol

Review the implementation from **all angles**:

- spec vs implementation (the story + **each** acceptance criterion)
- code correctness / consistency
- tests (present, passing, covering the criteria)
- docs
- card-log consistency — **mechanical backstop**: run `tmd check` on the
  card. Most log-format violations now fail at **write time** (via `tmd
  append`/`insert`/`edit`), so this catches only what slipped through (e.g.
  a `--force` write); it is a safety net, not the primary gate. `tmd check`
  is stateless (whole Log section): failures labeled `[old-format]` on
  legacy cards are **expected** (grandfathered old-format entries) — only
  non-`[old-format]` failures (chronology, duplicates) and `[old-format]`
  entries among the **most recent** log lines (a new malformed entry that
  slipped through) are actionable.
- leftover TODOs

**Two outcomes:**

| Outcome | Tag changes | Card content | Lane |
|---|---|---|---|
| Issues found | − `review-by-ai` | `## Review` (findings table) + `**Review**` log entry | → **top of `Ready`** (fix runs next) |
| No issues | − `review-by-ai`, + `ai-reviewed` | `## Review` ("no issues" + what was validated) + `**Review**` log entry | stays in `Review` (human → Done) |

**"No issues" is a first-class, valid outcome.** A clean pass is acceptable —
do not manufacture findings.

### `## Review` section format

```markdown
## Review — DD.MM.YYYY HH:MM
**Verdict:** N issues (X blocker)
**Vuln-scan:** CRITICAL: 0, HIGH: 0, MEDIUM: 3 (0 in changed files) — report: work/vuln_scan_results/genai_stack/<ts>-*.json  (omit the line when no scan ran)
| # | Severity | Where | Finding | Suggested fix |
|---|----------|-------|---------|---------------|
| 1 | blocker | path:line | ... | ... |
**Checked:** acceptance criteria, code, tests (ran: ...), docs, log consistency.
**Limitations:** ...
```

Severities: `blocker` / `major` / `minor` / `nit`.

**Table hygiene (D3/D4):**
- `**Checked:**` and `**Limitations:**` are **standalone paragraphs AFTER the
  findings table** — never rows inside the table (D3).
- Always a **blank line before any table** (renderer-agnostic robustness)
  (D4).

**Anchor hygiene**: never write the literal `## Log` in content sections,
review tables, or log entries — refer to it as "the Log section". The
`Where` column cites section names/titles (e.g. "Result section"), not raw
`##`-heading text.

### Applying the outcome

- **Issues found**: insert `## Review` **before** the Log section
  (`tmd insert`); append a `**Review**` log entry (`tmd append`); remove
  `review-by-ai` from line 1 (edit the tags); `move` the card to the **top
  of `Ready`** (`tmd to-top`); append a `**Moved** Review → Ready: reason`
  log entry.
- **No issues**: insert `## Review` before the Log section (`tmd insert`);
  append a `**Review**` log entry; on line 1 remove `review-by-ai` **and add
  `ai-reviewed`**; the card **stays in `Review`** (no lane move).

**Re-review (D5):** a card may already carry a `## Review` section from a
previous round. On re-review, **REPLACE** the previous `## Review` section
with the new one (single latest section) — do not accumulate multiple
`## Review` sections. Carry a one-line note in the new section:
`**Previous:** N issues, all resolved` (per-round verdicts are already in
the Log, so old sections are redundant).

Log every move. Timestamps are `DD.MM.YYYY HH:MM` (local time), always with
the date. A parked card must be resumable **cold** from its Log alone.

## Worker mode (orchestrator)

When launched as an orchestrator reviewer (headless session, eGPU brain):
review **exactly one card** — the one named in your entry prompt (first
eligible Review card, tagged `review-by-ai`), review it, document it, apply
the tag changes, and move/park it — then **end the session**. One card per
session.
