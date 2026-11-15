[Back to main README](../README.md)

# Board orchestrator (v1 — single eGPU slot, refiner + implementer + reviewer)

A dumb supervisor script that keeps cards flowing on the tasks.md board without
manual "check the board" prompts. It polls the board over HTTP and launches at
most **one** headless `pi` worker at a time (eGPU llama-server brain). There
are three worker roles — **refiner** (`[board-refiner-v1]`), **implementer**
(`[board-worker-v1]`) and **reviewer** (`[board-reviewer-v1]`) — but in V1
they share the **same single slot** (one eGPU model slot, `--models-max 1`), so
they can never run in parallel. Each worker works exactly one card per session
following its role skill (`tasks-refiner` / `tasks-implementer` /
`tasks-reviewer`, all entered via `tasks-board`), then exits; the orchestrator
launches a fresh worker for the next card.

All intelligence is in the worker + skills. The script only dispatches:
launch / kill / adopt / relaunch, guarded by timers and cooldowns.

## Files

| Path | Purpose |
|---|---|
| `orchestrator.py` | the script (single file, Python stdlib only) |
| `orchestrator.log` | decision log — one timestamped line per decision: `launch` / `exit` / `kill` / `adopt` / `idle` / `timer` / `anomaly` + why |
| `state.json` | single slot record `{pid, card, mode, start_time, card_seen_active, started_at, log_file, exit_timer_armed_at}` + auxiliary flags (`mode` = `implement` \| `review` \| `refine`) |
| `logs/session-<ts>.log` | per-worker session capture (stdout+stderr of `pi -p`), one file per card session |
| `.lock` | flock file — a second instance exits immediately |

## Prerequisites

Host process (not containerized — it must own the workers' PIDs):

- `python3` ≥ 3.8 (system Python, stdlib only — **no venv, no pip**)
- managed `pi` launcher at `~/.pi/agent/bin/pi` (workers are host `pi` processes; falls back to `pi` on `PATH` if the launcher is missing)
- `docker` (workers' `tmd` calls run in a transient container)
- Board up at `http://localhost:8090`
- eGPU llama-server up at `http://192.168.1.XX:8092`

Nothing else. The script adds no new host dependencies.

## Start

```sh
python3 orchestrator/orchestrator.py
```

Foreground, manual, no flags. Tunables are constants at the top of the file.
A second concurrent instance is refused (flock on `orchestrator/.lock`).

At start it reconciles: a state-file worker whose pid is alive **and whose
/proc start-time matches the recorded one** is **adopted** (survives
orchestrator restarts). There is no orphan scan — pi rewrites its process
title at startup, so a cmdline-marker scan can never match a live worker;
`state.json` is the record.

## Stop

| Signal | Effect |
|---|---|
| `SIGINT` / `SIGTERM` (1st) | **Graceful**: no new launches; keeps watching the current worker (exit timer stays armed); exits when the worker exits. No worker running → exits immediately. |
| `SIGINT` / `SIGTERM` (2nd) | **Force**: SIGTERM the worker (15 s grace, then SIGKILL), then exit. The card stays in `Active`; the next start cold-resumes it from its Log. |

`Ctrl-C` in the running terminal = 1st signal. Send it twice to force.

## Status / logs

```sh
tail -f orchestrator/orchestrator.log   # decisions (launch/kill/adopt/idle/relaunch + why)
cat orchestrator/state.json             # slot: pid, card, timers
ls -t orchestrator/logs/                # per-card session logs (newest first)
tail -f orchestrator/logs/session-<ts>.log
```

## Kill a hung worker

v1 has **no hang auto-detection** (a live PID with an unresponsive model is
invisible to the script). To kill a hung worker:

```sh
PID=$(python3 -c "import json;print(json.load(open('orchestrator/state.json'))['slot']['pid'])")
kill $PID            # SIGTERM; the script sees the dead PID -> stuck-worker relaunch
# if it ignores SIGTERM:
kill -9 $PID
```

The card stays in its lane (`Active` for an implementer, `Review` for a
reviewer); the script relaunches a worker, which cold-resumes the card from its
Log. (A max-runtime watchdog is a v2 candidate.)

## Crash behavior (`kill -9` / power loss)

Any running worker is orphaned and unwatched (the exit timer is gone). It is
one-shot, so it exits when its card leaves its lane (`Active`/`Review`). On the
next start the orchestrator **adopts** it from the state-file record (pid alive
+ /proc start-time match). If the worker is already dead and its card is in its
lane, the first tick takes the stuck-worker path: relaunch, card stays in its
lane.

## Behavior summary

- **Tick**: every 20 s — poll `GET /_api/sort` → **Active-lane cross-check**
  (sort entries verified against the file tree `GET /_api/resource`; stale
  entries from concurrent movers are ignored + anomaly logged) → worker
  liveness (pid alive + /proc start-time identity) → timers → launch
  evaluation. Cooldowns/timers are timestamp gates checked per tick, never
  blocking sleeps.
- **Launch**: no live worker AND a trigger is present AND cooldown elapsed AND
  eGPU reachable. Never two workers. Trigger queue order:
  **`Active` → `Spec` → `Review` → `Ready` → `OnHold`** (top card each; for
  `Spec`, the **first** card top→bottom **without** the `refined` tag —
  refined cards are skipped, not blockers; for `Review`, the **first** card
  top→bottom tagged `review-by-ai` — clean cards are skipped, not blockers;
  for `OnHold`, see the pre-check below). Only in-flight (Active) work takes
  precedence; refinement (Spec) preempts Review/Ready/OnHold.
- **Pre-launch pull (Ready → Active, OnHold → Active)**: a Ready trigger is
  moved into `Active` by the orchestrator itself — plain HTTP
  (`board_move_card`: file move + sort sync, ~ms, no container, no LLM) —
  *before* the worker boots. The card is in its target lane before any LLM
  turn, so `card_seen_active` is true from the first tick and the "no card
  ever in Active" backstop cannot mis-fire for a launched worker. On move
  failure (user moved the card in the UI between read and write): anomaly
  logged, launch skipped, retried next tick. Workers get a **card-specific
  entry prompt** ("work card `Active/<card>`" / "review card
  `Review/<card>`"). The `Spec` trigger is NOT pulled (the refiner works in
  place in `Spec` — the card never moves before the worker boots).
- **OnHold pre-check (scan hot-loop guard)**: before an OnHold trigger
  launches a worker, the orchestrator cheaply classifies each OnHold card's
  condition (board data already fetched each tick — no container, no LLM).
  It recognizes only the **canonical tag-based chain condition** (the
  predecessor card has `ai-reviewed` AND is in `Review` or `Done`, stated in
  the card's `## OnHold condition` section):
  - **satisfied** → the orchestrator pulls that card `OnHold → Active`
    itself (pre-launch pull, like Ready) and the worker works it as a normal
    Active card — no scan worker.
  - **all canonical, none satisfied** → no launch this tick (one log line,
    in the style of the idle/cooldown announcements) — this kills the 300 s
    scan hot loop (a worker every 5 min that found nothing).
  - **any non-canonical condition** (legacy prose, external conditions like
    "gitea reachable") → a scan worker launches as before: the
    condition-cleared check stays worker-side judgment, the worker scans
    top→bottom and claims the first cleared card with `tmd claim`. The
    pre-check is an optimization, not a gate — it never blocks a card a
    worker could clear.
- **Cooldowns** after a worker exits: 60 s normal; 5 min when the *only*
  trigger is an `OnHold` scan worker (non-canonical conditions — avoids
  hot-looping token-burning no-op sessions; an all-canonical blocked OnHold
  lane is skipped by the pre-check and never reaches the cooldown).
- **Startup grace** (5 min from launch): the exit timer cannot arm before the
  window ends — unless the card was already observed in its mode lane
  (`Active`/`Spec`) and then left it (a worker that finished but hangs gets
  killed 120 s after the card left, even inside the window). Covers boot +
  skill load + cold 27B model load.
- **Exit timer** (120 s, mode-aware): armed when the slot's card *leaves* its
  mode lane (`Active` for implementer, `Review` for reviewer, `Spec` for
  refiner), **or** — reviewer only — when the card *loses* `review-by-ai`
  (clean pass: consumed, stays in `Review`), **or** when the grace ends with no
  card ever in the mode lane; kill if the worker is still alive.
- **Stuck worker** (PID dead + card in its lane `Active`/`Review`/`Spec`):
  relaunch after cooldown; the card stays in its lane and is cold-resumed.
  Covers crash, mode switch, and mid-worker eviction by a human eGPU session.
- **Board down** (`:8090` unreachable): idles + logs (once per state change);
  no launches, no state writes; worker liveness keeps being checked.
- **eGPU down** (`:8092` unreachable): no launches; logged once per state change.
- **Two cards in `Active`** (corrupt state): topmost wins, anomaly logged.
- **Shared eGPU slot**: a worker launch evicts whatever model is loaded; a
  human eGPU session loading a model mid-worker kills the worker (stuck-worker
  path). The user avoids interfering while the orchestrator loops.
- **Three roles, one slot (V1)**: refiner, implementer and reviewer are
  separate worker roles (separate entry prompt + skill) but share the single
  eGPU slot — `evaluate_launch` runs only when `slot is None`, so they can
  never run in parallel (structural single-slot, no locking). The slot record
  carries a `mode` (`implement`/`review`/`refine`) so the exit timer is
  mode-aware. V2 (future iGPU) splits this into two independent single-slot
  queues (see "Worker model").
- **Slot card**: seeded from the launch trigger, refined to a single
different card observed in the mode lane **only while the original card has
never been observed in that lane** (the OnHold-claim case — the trigger card
was never in the lane, so the slot is reassigned to the card that landed
there). Once the slot card has been observed in the mode lane and then left
(work done), the slot card is **never reassigned** — the exit timer arms
instead (liveness backstop for a finished-but-hung worker). Worker exits are
logged as `exit:` with the actual mode-lane state and the last line of the
worker's session log; `kill:` is reserved for orchestrator-initiated kills.

## Tunables (constants at the top of `orchestrator.py`)

| Constant | Default | Meaning |
|---|---|---|
| `TICK_SECONDS` | 20 | supervisor tick interval (the only sleep) |
| `GRACE_SECONDS` | 300 | startup grace — no kill inside this window |
| `EXIT_TIMER_SECONDS` | 120 | kill if alive this long after the exit timer arms |
| `COOLDOWN_NORMAL_SECONDS` | 60 | re-launch cooldown (Active/Ready pending) |
| `COOLDOWN_ONHOLD_ONLY_SECONDS` | 300 | re-launch cooldown (only trigger: uncleared OnHold) |
| `FORCE_KILL_GRACE_SECONDS` | 15 | SIGTERM → SIGKILL grace |
| `HTTP_TIMEOUT_SECONDS` | 5 | board / eGPU probe timeout |
| `BOARD_URL` / `EGPU_URL` | see file | endpoints |
| `WORKER_MODEL` | `{"implement": None, "review": None, "refine": None}` | per-mode worker model; `None` = pi default. When set, that worker is launched with `--model <pattern>` (supports `provider/id`) |

No flags, no env vars — edit the constants to change behavior.

**Worker model (per-mode):** the orchestrator pins no model in V1.
`WORKER_MODEL = {"implement": None, "review": None, "refine": None}` — `None`
means the worker runs with pi's own defaults (`defaultModel` / `defaultProvider` in
`~/.pi/agent/settings.json`), so all three roles share the eGPU default
model and one slot. When a mode's value is set, that worker is launched with
`--model <pattern>` (pi CLI flag; supports `provider/id`). This is the
iGPU-ready hook for V2: set `WORKER_MODEL["review"] = "igpu-..."` and split the
single `slot` into two independent single-slot queues (`slots: {implement,
review}`) + an iGPU probe gate — `evaluate_launch` already takes a mode, so the
split is local. (`PI_MODEL` / `PI_PROVIDER` are pi *output* vars for shell
tools, not inputs — the old env injection was a no-op.)

## Related

- The board the orchestrator drives — lanes, card format, flow, `tmd` CLI,
  user interaction: [tasks.md/README.md](../tasks.md/README.md)
- The worker role skills (all entered via `tasks-board` — the shared board
  facts live there):
  - `.pi/skills/tasks-board/SKILL.md` — board protocol (lanes, `tmd` CLI,
    card format, priority queue, single-Active guardrail)
  - `.pi/skills/tasks-implementer/SKILL.md` — implementer work protocol
    (`[board-worker-v1]`)
  - `.pi/skills/tasks-refiner/SKILL.md` — refiner work protocol
    (`[board-refiner-v1]`)
  - `.pi/skills/tasks-reviewer/SKILL.md` — reviewer work protocol
    (`[board-reviewer-v1]`)
- Services & ports, GPU work modes: main README ([../README.md](../README.md))

[Back to main README](../README.md)
