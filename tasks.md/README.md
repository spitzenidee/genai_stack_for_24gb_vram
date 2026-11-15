[Back to main README](../README.md)

# Task board (tasks.md)

## TL;DR

A self-hosted, markdown-based task board (the [Tasks.md](https://github.com/BaldissaraMatheus/Tasks.md) app, pinned release) running as the `tasks-md` compose service on port `8090`. Cards are plain markdown files in lanes; the board is the backbone of the stack's agentic "Ralph loop" — humans write cards, a dumb Python orchestrator polls the board and launches agent workers one at a time, and humans stay in the loop asynchronously via the lanes. You touch this when you want to create or move cards, watch the board in a browser, or script board operations with the `tmd` CLI.

## What & why

The board is a kanban board implemented as a folder of markdown files: one directory per lane, one `.md` file per card. No database, no lock-in — the files *are* the board, human-readable and diffable, and the web UI is just an editor over them.

It exists because the stack's agent workflow needs a task system that both humans and agents can work in:

- **Humans** write cards (specs, research questions, implementation requests) and keep full decision power: card content, sign-off (`Review` → `Done`), and flow (lane moves; order within a lane = priority).
- **Agents** work cards one at a time. The [orchestrator](../orchestrator/README.md) — a "dumb" Python supervisor with no LLM in the scheduling loop — polls the board over HTTP and launches at most one headless worker (refiner / implementer / reviewer) at a time, because the LLM backend has a single model slot.
- **The human stays in the loop asynchronously** via the handover lanes (`AskUser`, `Review`, `Ready`) — no one has to sit at the terminal while the loop runs.

## How it works

### The service

Compose service `tasks-md`, image `tasks-md:latest` built from `tasks.md/Dockerfile`. The Dockerfile differs from upstream deliberately: the frontend is built **at image build time** (upstream rebuilds it in the entrypoint on every start), the runtime is the same node image (no second runtime stage), and the app is pinned to an official release tag (`REPO_REF`, currently `3.3.0`) rather than `main`.

| Piece | Where |
|---|---|
| Cards (lanes) | `tasks.md/tasks/` — one directory per lane, one `.md` file per card (gitignored runtime state) |
| Board state | `tasks.md/config/` — `sort.json` (lane/card order), `tags.json` (tag chip colors), `stylesheets/`, `images/` (gitignored runtime state) |
| Port | `${TASKS_MD_PORT}:8080` — `8090` in `.env` |

### Lanes

| Lane | Owner | Meaning |
|---|---|---|
| `Backlog` | human | ideas, not yet scheduled |
| `Ready` | human | human→AI handover — the orchestrator pulls the top card into `Active` |
| `Spec` | handover (human→AI→human) | free-form prose cards; the **refiner** rewrites them in place into the canonical card structure |
| `Active` | AI | the card being worked — **at most one** (single LLM slot) |
| `OnHold` | AI | parked on a condition (e.g. a predecessor card must finish first) |
| `AskUser` | handover (AI→human→AI) | the agent is blocked on a human decision; the human is the unblocker |
| `Review` | AI → human | finished work awaiting human sign-off (`Review` → `Done` approves, `Review` → `Ready` sends it back with feedback) |
| `Done` | — | approved and finished |

**Order within a lane is priority** (top = highest). Parked cards (`AskUser`, `OnHold`) hold no slot and block nothing.

### Card format

A card is a markdown file with a strict shape (enforced by the `tmd` CLI):

1. **Line 1** — zero or more flow tags, one bracket group per tag (e.g. `[tag:spec][tag:review-by-ai]`); topics live in the card body, not in tags.
2. **H1 title**, then the human-written spec (Story, acceptance criteria, …) — never rewritten by agents.
3. **Content sections** (e.g. `## Result`, `## Repo`, `## LLM`) — inserted before the Log section.
4. **A single `## Log` section, always last** — one timestamped bullet line per agent action (`**Created**`, `**Moved** X → Y: reason`, `**Question**`, `**Result**`). A parked card must be resumable *cold* from its Log alone.

### The flow

```
Backlog → Ready → Active → Review → Done
              ↑        │  ↑          │
              │        ↓  │          │ (feedback)
              └──────────┘  │
          AskUser / OnHold / Spec (handovers, parked states)
```

The orchestrator's trigger queue is `Active` (continuation) → `Spec` (first unrefined card) → `Review` (first `review-by-ai` card) → `Ready` (top) → `OnHold` (first cleared condition). It performs the `Ready → Active` and `OnHold → Active` pulls itself (plain HTTP, before the worker boots) and then launches the worker with a card-specific entry prompt.

### The `tmd` CLI

`.pi/skills/tasks-board/scripts/tmd` is a stateless CLI over the board's HTTP API — the board is the source of truth, every command re-reads it. The wrapper runs `tmd.py` (Python stdlib, no host deps) in a transient `python:3.12-slim` container on the host network, so it works in every stack mode. Everyday commands:

| Command | Effect |
|---|---|
| `tmd list` | all lanes + cards in stored order |
| `tmd get <Lane/card>` | print a card |
| `tmd new-card <Lane/card> [--template]` | create a card (from stdin, or from the canonical template) |
| `tmd move <src> <dst>` | move a card between lanes |
| `tmd append <Lane/card>` | append log entries (stdin) |
| `tmd insert <Lane/card>` | insert a content section before the Log section (stdin) |
| `tmd tag <Lane/card> --add … --remove …` | edit line-1 tags (the only way to change tags) |
| `tmd claim <Lane/card>` | verify `Active` is empty, move the card in, print it |
| `tmd check <Lane/card>` | structural + Log-format validation |
| `tmd img <name>` | upload an image, prints the embed path |

## How to use

**Board UI** — open <http://localhost:8090>: create cards, drag them between lanes, edit content, upload images, adjust tag chip colors.

**`tmd` CLI** — for scripted or agent work (agents always use `tmd`, never the UI editor):

```sh
T=.pi/skills/tasks-board/scripts/tmd
$T list                                        # what's where
$T get Ready/<card>                            # read a card
echo '…' | $T new-card Backlog/my-card.md      # create a card
$T move Backlog/my-card.md Ready/              # schedule it
$T tag Ready/my-card.md --add review-by-ai     # tag it
```

**As the human unblocker** — the two manual moves that keep the loop going:

1. **`AskUser` answered** → edit the answer into the card, move it to `Ready` (top, if it should resume with priority).
2. **`Review` sign-off** → move to `Done` (approved) or back to `Ready` (feedback in the card).

Everything else — pulling `Ready` into `Active`, claiming cleared `OnHold` cards, launching workers — is the orchestrator's job.

## Configuration & influence

| Knob | Where | Meaning |
|---|---|---|
| `TASKS_MD_PORT` | `.env` | host port for the board (default `8090`) |
| `TASKS_MD_URL` | env of the `tmd` wrapper | board URL override (default `http://localhost:8090`) |
| `tasks.md/config/tags.json` | board state | tag chip colors (seeded from `tasks.md/tags.json` on first start; edit via the UI) |
| `tasks.md/config/stylesheets/custom.css` | board state | user CSS (first start: adwaita theme import) |
| `tasks.md/config/sort.json` | board state | lane/card order — managed by the app and `tmd`, never hand-edited |
| `REPO_REF` / `BASE_PATH` | `tasks.md/Dockerfile` build args | pinned app release / subpath (PWA requires `/`) |
| `card-template.md` | `.pi/skills/tasks-board/` | canonical card template; mirrored as the read-only board card `Backlog/TEMPLATE CARD` (refresh with `tmd sync-template`) |

Upgrading the app: `docker build --build-arg REPO_REF=<tag> -t tasks-md:latest tasks.md/ && docker compose up -d tasks-md`.

## Troubleshooting

- **UI saves reformat the card.** The app normalizes card bytes on save (harmless but deterministic). Agents always use `tmd`; humans should expect a UI save to reformat.
- **Card names with forbidden characters.** The UI refuses `< > : % " / \ | ? *` (and `%` additionally 500s every update server-side — a double-decode bug in the pinned app). Leading `.` hides the card entirely (dotfiles are filtered out of the board tree).
- **A literal `## Log` in card content** breaks section insertion (`tmd insert` places content before the last exact `## Log` line) — refer to it as "the Log section" in prose.
- **Two cards in `Active`** is corrupt state (the single-slot invariant); the orchestrator logs an anomaly and works the topmost.

## Related

- The orchestrator that drives the board loop (single slot, worker roles, timers): [orchestrator/README.md](../orchestrator/README.md)
- Board protocol — the single source of truth for board facts (lanes, card format, flow, `tmd`): `.pi/skills/tasks-board/SKILL.md`, with the role skills `.pi/skills/tasks-implementer/`, `.pi/skills/tasks-refiner/`, `.pi/skills/tasks-reviewer/`
- Services & ports, GPU work modes: main README ([../README.md](../README.md))

[Back to main README](../README.md)
