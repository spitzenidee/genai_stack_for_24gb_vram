<!--
  Canonical card template for the tasks.md board.
  SINGLE SOURCE OF TRUTH — edit here, then:
    - refresh the board mirror:   tmd sync-template
    - create a card from it:      tmd new-card "Lane/title.md" --template
  The board card "Backlog/TEMPLATE CARD" is a read-only UI mirror (copy-paste
  source for the board UI) — never hand-edit it.
-->

## How to use this template

**Create a card — board UI only (no agent needed):**
open `Backlog/TEMPLATE CARD` in the UI → copy the fenced block below →
paste it into a new card → fill the placeholders.

**Create a card — shell / agent:**
`tmd new-card "Ready/my feature.md" --template` — substitutes the title and
writes a canonical `Created` log line (real timestamp + lane). Options:
`--tag spec|research` sets the optional type tag (line 1 stays empty
otherwise), `--actor human` marks a human-created card.

**Change the template:**
edit this file (`.pi/skills/tasks-board/card-template.md`), then run
`tmd sync-template` to refresh the board mirror (its Log is preserved).
Never hand-edit the board card.

## Design notes

- **Line 1 (tags)** — the only place tags live. Write each as a bracketed `tag:` entry (the board's line-1 contract; only the orchestrator reads line 1 — the UI renders *any* bracketed tag in the card body as a real tag chip). Body prose must not use bracketed tags (free text only; mention tags unbracketed, e.g. `tag:spec`). Line 1: zero or more flow tags — topics/projects belong in the Story (they are not tags).
- **Card type (line 1)** — optional type tag: `tag:spec` (repo-based spec — `## Repo` required, the agent works the repo read-only and delivers the spec in the card) or `tag:research` (findings / brainstorming — `## Repo` optional, read-only). No type tag = implementation card (default: feature branch, merge to dev). `merge-pending` is a workflow-state tag the agents manage — never set it by hand.
- **Description** — user-story form (`As a… I want… so that…`) + optional context. This is the human spec; the agent never rewrites it.
- **Refiner bounded exception (G7)** — the "never rewrite the human spec" rule has exactly one bounded exception: the **refiner** (`tasks-refiner`) *transforms* free-form prose in the `Spec` lane into this canonical structure, preserving **all** human intent, requirements and decisions (content-preservation check: every requirement in the original prose must survive into the refined card). The refiner's output *is* the spec the implementer then works from — the "never rewrite" rule applies to the refined spec as-is.
- **Repo** — optional `## Repo` section (name, remote, base branch) for cards that touch a repo; **required for `tag:spec` cards**. Absent = the card touches no repo (no checkout, no merge step). The repo is checked out to `work/orchestrator/<name>` by the implementer; the exact remote URL is in the card's ## Repo section.
- **LLM** — optional `## LLM` section (`- Model: <model-id>`) for cards that need a non-default worker model (e.g. pentesting → `egpu-SWIFT-1.5-Uncensored`). Absent = the pi default (`egpu-SWIFT-1.5`) applies — the common case. The orchestrator parses the section at launch and passes `--model <id>` to pi; an ID outside the known-models allowlist falls back to the pi default (anomaly logged, the launch never fails). The [known models](#known-models-appendix--the-card-facing-llm-vocabulary) appendix below is the card-facing vocabulary (the refiner's single source of truth; keep in sync with the orchestrator's `KNOWN_MODELS` allowlist).
- **Acceptance criteria** — checklist = definition of done; the agent ticks boxes as verified. For repo implementation cards, the standard DoD lines are: work on a feature branch from the base branch · merged to the base branch + feature branch deleted · pushed to origin (or push pending recorded, card parked OnHold).
- **Links** — explicit relations: Related / Blocks / Blocked by / Part of (parent or epic).
- **Comments** — deliberately omitted. Discussion goes in the card log (chronological, auditable) — a separate Comments section would be a second, unstructured place for the same content.
- **Card log** — required, always last. One line per significant step, chronological; the board protocol is built on it.
- **Task breakdown** — optional checklist (sub-tasks / steps). Distinct from the acceptance criteria (the *what* / done-ness) — the breakdown is the *how* / work steps.
- **Deliberately omitted** — attachments, a separate metadata block, and a Comments section (see above).

### Known models appendix (the card-facing `## LLM` vocabulary)

The `## LLM` section's `- Model:` line takes a **bare** model ID from this
table (no provider prefix — `://` breaks the `--model` split; the `egpu-`/
`igpu-` prefix encodes the server, and the IDs are globally unique). This
appendix is the single source of truth for the **card-facing** vocabulary —
the refiner resolves semantic model mentions (e.g. "uncensored") to these
IDs. Keep it in sync with the orchestrator's `KNOWN_MODELS` allowlist and the
llama-server presets (`llamacpp/models-egpu-rdna.ini` +
`llamacpp/models-igpu.ini`).

| Model ID | Semantic alias | Notes |
| --- | --- | --- |
| `egpu-SWIFT-1.5` | (default — no section needed) | non-ablated Swift 1.5 eGPU; the pi default |
| `egpu-SWIFT-1.5-Uncensored` | "uncensored" | uncensored Swift 1.5 eGPU; the pentesting use case |
| `igpu-Gemma4-26B-A4B` | — | iGPU (V2 concern — v1 is eGPU-only) |
| `igpu-Qwen3.6-35B-A3B` | — | iGPU (V2 concern — v1 is eGPU-only) |

## Template

```

# <Story title — keep identical to the card name>

## How to fill this card
1. **Title** — the card name (filename) *is* the title: keep the `#` heading identical to it.
2. **Line 1 (tags)** — optional type tag only: `tag:spec` (repo-based spec) / `tag:research` (findings / brainstorm) / none = implementation (line 1 may be empty — zero tags is valid).
3. **Story** — what + why, in 1–2 sentences. This is the spec — the agent never rewrites it.
4. **Repo** — keep only if the card touches a repo (**required for `spec` cards**); delete the section otherwise.
5. **LLM** — keep only if the card needs a non-default worker model (e.g. pentesting); delete the section otherwise (the pi default applies).
6. **Acceptance criteria** — the definition of done: verifiable conditions. Repo implementation cards add the DoD lines (feature branch / merged to base + branch deleted / pushed to origin).
7. **Breakdown** — optional work steps (the *how*); distinct from the criteria (the *what*).
8. **Done filling?** Delete this section. The `## Log` is managed by the board protocol — never edit it by hand.

## Story
As a <role>, I want <capability>, so that <benefit>.

<Optional: context, background, constraints.>

## Repo
<Delete this section if the card touches no repo. Required for `tag:spec` cards.>
- Name: <repo_name>
- Remote: <url — the project's Git server (local Gitea); the exact host is per-project>
- Base branch: dev

## LLM
<Delete this section if the card runs on the default model (the common case).>
- Model: <model-id — see the "known models" appendix>

## Acceptance criteria
- [ ] <verifiable condition — how do we know it's done?>
- [ ] <…>
<Repo implementation cards: add the standard DoD lines — work on a feature
branch from the base / merged to the base + branch deleted / pushed to origin
(or push pending recorded, card in OnHold).>

## Breakdown
- [ ] <sub-task / step — the work, not the outcome>
- [ ] <…>

## Links
- Related: <card name>
- Blocks / Blocked by: <card name>
- Part of (parent / epic): <card name>

## Notes
<Free-form discussion, decisions, open questions.>

## Log
- <DD.MM.YYYY HH:MM> **Created** — created in `<Lane>` (human | agent).
```
