#!/usr/bin/env python3
"""orchestrator — script-based board orchestrator (v1: single eGPU worker).

A dumb supervisor: polls the tasks.md board over HTTP, launches at most one
headless `pi` worker at a time (eGPU llama-server brain), watches it with a
startup grace + exit timer, and relaunches after failures. All intelligence
stays in the worker + the tasks-board skill — this script only dispatches.
Dispatch includes the pre-launch pull: a Ready trigger is moved into Active
by the orchestrator itself (plain HTTP, ~ms) before the worker boots, so the
card is in its target lane before any LLM turn happens.

Stdlib only. Run on the host:

    python3 orchestrator/orchestrator.py

Stop: SIGINT/SIGTERM (graceful — no new launches, wait for the current
worker, then exit). A second SIGINT/SIGTERM force-kills the worker
(15 s grace, then SIGKILL) and exits. See README.md.

Files (all in this directory):
    orchestrator.log   decision log (launch/exit/kill/adopt/idle/timer/anomaly/slot + why)
    state.json         single slot record + auxiliary flags
    logs/session-*.log per-worker session capture (stdout+stderr of `pi -p`)
"""
import fcntl
import json
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.parse
import urllib.request

# --------------------------------------------------------------------------
# Tunables (constants by design — no flags, no env vars)
# --------------------------------------------------------------------------
BOARD_URL = "http://localhost:8090"            # tasks.md board
EGPU_URL = "http://192.168.1.XX:8092"          # llama-server (worker brain)
# Worker model/provider: NO override here. The worker uses pi's own defaults
# (defaultModel / defaultProvider in ~/.pi/agent/settings.json). Note that
# PI_MODEL / PI_PROVIDER are pi *output* vars (injected into shell tools),
# not inputs — setting them on the worker env did nothing.
PI_BIN = "pi"                                  # resolved via PATH at start

TICK_SECONDS = 20                  # supervisor tick interval (the only sleep)
GRACE_SECONDS = 300                # startup grace: no kill inside this window
EXIT_TIMER_SECONDS = 120           # kill if still alive this long after arming
COOLDOWN_NORMAL_SECONDS = 60       # re-launch cooldown (Active/Ready pending)
COOLDOWN_ONHOLD_ONLY_SECONDS = 300  # re-launch cooldown (only trigger: OnHold)
FORCE_KILL_GRACE_SECONDS = 15      # SIGTERM -> SIGKILL grace
HTTP_TIMEOUT_SECONDS = 5           # board / eGPU probe timeout

# Markers embedded in the worker prompts (provenance only — pi rewrites its
# process title at startup, so they are NOT usable for process detection).
# The marker in the entry prompt also assigns the worker's ROLE: the agent
# never infers its role from board state (see tasks-board "Role dispatch").
WORKER_MARKER = "board-worker-v1"        # implementer
REVIEWER_MARKER = "board-reviewer-v1"    # reviewer


def implementer_entry_prompt(lane, card):
    """Card-specific implementer prompt (built at launch).

    The card is already in its target lane: Ready triggers are pulled into
    `Active` by the orchestrator at launch time (pre-launch pull), so the
    worker never selects from `Ready`. The OnHold exception stays worker-side:
    the condition-cleared check needs judgment (reading the card's Log), which
    the orchestrator cannot do — the worker claims with `tmd claim`.
    """
    if lane == "OnHold":
        task = ("scan the OnHold lane top→bottom, find the first card whose "
                "condition is cleared (check mechanically; the card's Log "
                "states how to verify), claim it with `tmd claim "
                "OnHold/<card>`, then work it")
    else:
        # lane == "Active" (Ready cards arrive here via the pre-launch pull).
        task = (f"work card `Active/{card}` — it is already in Active "
                "(pulled in at launch). Verify it is still in Active, then "
                "work it")
    return (f"[{WORKER_MARKER}] You are a board worker. Read "
            ".pi/skills/tasks-board/SKILL.md and follow it: " + task
            + ", park it (AskUser/OnHold) or complete it (Review), then end "
            "the session. Work exactly one card per session.")


def reviewer_entry_prompt(card):
    """Card-specific reviewer prompt (built at launch).

    The orchestrator already picked the first eligible Review card
    (top→bottom, tagged review-by-ai) — the worker reviews exactly that one.
    """
    return (f"[{REVIEWER_MARKER}] You are a board reviewer. Read "
            ".pi/skills/tasks-board/SKILL.md and follow it: review card "
            f"`Review/{card}` (tagged review-by-ai), document findings in "
            "a ## Review section, apply the tag changes, and move/park the "
            "card, then end the session. Review exactly one card per "
            "session.")

# Per-mode worker model (V1: both None = pi default, one shared eGPU slot).
# When set, the worker is launched with `--model <pattern>` (pi CLI flag;
# supports "provider/id"). V2 (future iGPU): review = "igpu-..." + a 2nd
# independent single-slot queue (see README).
WORKER_MODEL = {"implement": None, "review": None}

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
ORCH_DIR = os.path.dirname(os.path.abspath(__file__))
STACK_ROOT = os.path.dirname(ORCH_DIR)
STATE_FILE = os.path.join(ORCH_DIR, "state.json")
LOG_FILE = os.path.join(ORCH_DIR, "orchestrator.log")
SESSION_LOG_DIR = os.path.join(ORCH_DIR, "logs")
LOCK_FILE = os.path.join(ORCH_DIR, ".lock")

_logger = logging.getLogger("orchestrator")


def log(msg, *args):
    """Decision-log line (one per decision / state change)."""
    _logger.info(msg, *args)


# --------------------------------------------------------------------------
# Board / eGPU access (plain HTTP — no container spawns)
# --------------------------------------------------------------------------
def _http_json(url, timeout=HTTP_TIMEOUT_SECONDS):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def board_sort():
    """Lane -> ordered card map (the priority-queue input). Raises on failure."""
    return _http_json(BOARD_URL + "/_api/sort")


def board_resource():
    """Full board tree (lanes -> files with content). Raises on failure."""
    return _http_json(BOARD_URL + "/_api/resource")


def _http_request(method, url, body=None):
    """HTTP request to the board API (JSON body optional). Raises on failure."""
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
        resp.read()


def board_move_card(card, src_lane, dst_lane):
    """Move a card between lanes: file move + sort sync (mirrors tmd move).

    The board's move endpoint does NOT update sort state, so both halves are
    done here (same as tmd.py cmd_move). Raises on any HTTP failure — the
    caller decides (evaluate_launch: log anomaly, skip launch, retry tick).
    """
    _http_request("PATCH",
                  BOARD_URL + "/_api/resource/"
                  + urllib.parse.quote(f"{src_lane}/{card}.md", safe="/"),
                  body={"newPath": f"{dst_lane}/{card}.md"})
    sort = board_sort()
    if src_lane in sort:
        sort[src_lane] = [c for c in sort[src_lane] if c != card]
    sort.setdefault(dst_lane, [])
    if card not in sort[dst_lane]:
        sort[dst_lane].append(card)
    _http_request("PUT", BOARD_URL + "/_api/sort", body=sort)


def _lane_files(resource, lane_name):
    """Ordered file list for a lane from a board resource tree. [] if absent."""
    for lane_obj in resource:
        if lane_obj.get("name") == lane_name:
            return lane_obj.get("files", [])
    return []


def active_on_disk(resource):
    """Card names physically present in the Active lane (file truth).

    sort.json is a last-write-wins whole map and can transiently list cards
    whose file has already moved (concurrent movers); the file tree is
    authoritative for lane membership.
    """
    return {f.get("name") for f in _lane_files(resource, "Active")}


def review_on_disk(resource):
    """Card names physically present in the Review lane (file truth).

    Same rationale as active_on_disk(): the file tree is authoritative for
    lane membership; sort.json can transiently miss entries.
    """
    return {f.get("name") for f in _lane_files(resource, "Review")}


def _card_tags(content):
    """Tags on a card's first line, e.g. ['review-by-ai', 'genai_stack']."""
    first_line = content.split("\n", 1)[0]
    return re.findall(r"\[tag:([^\]]+)\]", first_line)


def review_tags(resource):
    """Set of Review cards currently tagged review-by-ai."""
    tagged = set()
    for f in _lane_files(resource, "Review"):
        if "review-by-ai" in _card_tags(f.get("content", "")):
            tagged.add(f.get("name"))
    return tagged


def first_review_tagged(resource):
    """First Review card (top→bottom) tagged review-by-ai. None if none.

    Position = priority (exactly like Ready). A card without the tag (e.g.
    already clean with ai-reviewed) is skipped, not a blocker — so 1–n tagged
    cards anywhere in Review are all reviewed, highest first.
    """
    for f in _lane_files(resource, "Review"):
        if "review-by-ai" in _card_tags(f.get("content", "")):
            return f.get("name")
    return None


def egpu_up():
    """Probe the eGPU llama-server (GET /v1/models)."""
    try:
        _http_json(EGPU_URL + "/v1/models")
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------
# Worker process helpers
# --------------------------------------------------------------------------
def pid_alive(pid):
    # Reap our own exited children first: an unreaped child is a zombie and
    # kill(pid, 0) would still succeed on it (false "alive").
    try:
        p, _ = os.waitpid(pid, os.WNOHANG)
        if p == pid:
            return False
    except ChildProcessError:
        pass  # not our child (e.g. adopted orphan) — fall through
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def pid_start_time(pid):
    """Process start time: field 22 of /proc/<pid>/stat (clock ticks since boot).

    Stable across exec and across pi's process.title rewrite (which erases the
    cmdline marker within ~2 s of launch). None if the process is gone or the
    read fails.
    """
    try:
        with open(f"/proc/{pid}/stat", "rb") as f:
            data = f.read().decode(errors="replace")
    except OSError:
        return None
    # comm (field 2) is parenthesized and may contain spaces/parens — split
    # after the LAST ')' so the remaining fields parse cleanly.
    head, sep, rest = data.rpartition(")")
    if not sep:
        return None
    fields = rest.split()
    # rest starts at field 3 (state); field 22 (starttime) is index 19.
    if len(fields) < 20:
        return None
    try:
        return int(fields[19])
    except ValueError:
        return None


def worker_identity_ok(slot):
    """Liveness + identity for the tracked slot.

    The slot pid is our direct Popen child, so liveness is authoritative; the
    start-time comparison guards against PID reuse. (The old cmdline-marker
    check was unusable: pi sets process.title='pi' at startup, erasing the
    marker before the first supervisor tick.)
    """
    pid = slot["pid"]
    if not pid_alive(pid):
        return False
    ref = slot.get("start_time")
    if ref is None:
        return True  # no reference recorded (legacy state) — trust liveness
    st = pid_start_time(pid)
    if st is None:
        return True  # transient read failure — benefit of the doubt, re-check next tick
    return st == ref


def session_log_tail(log_file, width=200):
    """Last non-empty line of a worker session log, truncated. None if unreadable."""
    if not log_file:
        return None
    try:
        with open(os.path.join(ORCH_DIR, log_file)) as f:
            lines = [l.strip() for l in f if l.strip()]
        return lines[-1][:width] if lines else None
    except OSError:
        return None


# --------------------------------------------------------------------------
# State file (single slot record + auxiliary flags)
# --------------------------------------------------------------------------
def empty_state():
    return {
        "slot": None,              # {pid, card, mode, start_time, card_seen_active, started_at, log_file, exit_timer_armed_at} | None
        "last_exit_at": None,
        "last_launch_at": None,
        "board_down": False,
        "egpu_down": False,
        "idle_no_work": False,
        "cooldown_announced": False,
        "dead_board_down_announced": False,
    }


def load_state():
    try:
        with open(STATE_FILE) as f:
            state = json.load(f)
    except (OSError, ValueError):
        return empty_state()
    if not isinstance(state, dict) or "slot" not in state:
        log("anomaly: state file missing/corrupt — starting fresh")
        return empty_state()
    base = empty_state()
    base.update(state)
    return base


def save_state(state):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
        f.write("\n")
    os.replace(tmp, STATE_FILE)


# --------------------------------------------------------------------------
# Worker lifecycle
# --------------------------------------------------------------------------
def launch_worker(state, now, trigger):
    os.makedirs(SESSION_LOG_DIR, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    log_file = os.path.join(SESSION_LOG_DIR, f"session-{ts}.log")
    n = 1
    while os.path.exists(log_file):  # same-second relaunch guard
        log_file = os.path.join(SESSION_LOG_DIR, f"session-{ts}-{n}.log")
        n += 1
    lane, card = trigger
    mode = "review" if lane == "Review" else "implement"
    model = WORKER_MODEL.get(mode)
    if mode == "review":
        entry_prompt = reviewer_entry_prompt(card)
    else:
        entry_prompt = implementer_entry_prompt(lane, card)
    cmd = [PI_BIN, "-p", entry_prompt]
    if model:
        cmd += ["--model", model]
    env = os.environ.copy()
    with open(log_file, "wb") as lf:
        proc = subprocess.Popen(
            cmd,
            cwd=STACK_ROOT,
            env=env,
            stdout=lf,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,  # survive orchestrator death / terminal Ctrl-C
        )
    state["slot"] = {
        "pid": proc.pid,
        "card": card,               # seeded from the trigger; refined on ticks
        "mode": mode,               # "implement" | "review"
        "start_time": pid_start_time(proc.pid),
        "card_seen_active": False,  # set once the card is observed in the mode lane
        "started_at": now,
        "log_file": os.path.relpath(log_file, ORCH_DIR),
        "exit_timer_armed_at": None,
    }
    state["last_launch_at"] = now
    state["cooldown_announced"] = False
    save_state(state)
    log("launch: pid=%d trigger=%s/%s mode=%s model=%s log=%s",
        proc.pid, lane, card, mode, model or "pi-default",
        os.path.relpath(log_file, ORCH_DIR))


def kill_worker(state, reason):
    """SIGTERM the worker, wait FORCE_KILL_GRACE_SECONDS, then SIGKILL."""
    slot = state["slot"]
    pid = slot["pid"]
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    deadline = time.time() + FORCE_KILL_GRACE_SECONDS
    while time.time() < deadline:
        if not worker_identity_ok(slot):
            break
        time.sleep(0.5)
    if worker_identity_ok(slot):
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        log("kill: pid %d ignored SIGTERM for %ds — SIGKILL", pid, FORCE_KILL_GRACE_SECONDS)
    log("kill: worker pid %d terminated (%s)", pid, reason)
    state["last_exit_at"] = time.time()
    state["slot"] = None
    state["cooldown_announced"] = False
    save_state(state)


# --------------------------------------------------------------------------
# Supervisor tick components
# --------------------------------------------------------------------------
def watch_worker(state, now, mode_lane, review_tagged=None):
    """Liveness + timers for the current worker.

    `mode_lane` = ordered card list for the slot's mode lane (Active for
    implement, Review for review), or None when the board is down
    (board-dependent checks are deferred). `review_tagged` = set of Review
    cards currently tagged review-by-ai (reviewer mode only; None otherwise).
    """
    slot = state["slot"]
    if slot is None:
        return
    pid = slot["pid"]
    mode = slot.get("mode", "implement")
    lane_name = "Review" if mode == "review" else "Active"

    if not worker_identity_ok(slot):
        if mode_lane is None:
            if not state.get("dead_board_down_announced"):
                log("idle: worker pid %d dead but board down — deferring to board recovery", pid)
                state["dead_board_down_announced"] = True
            return  # keep the slot; re-evaluate when the board is back
        state["dead_board_down_announced"] = False
        card = slot["card"]
        card_in_lane = (card in mode_lane) if card else bool(mode_lane)
        last_line = session_log_tail(slot.get("log_file"))
        if card_in_lane:
            log("exit: worker pid %d gone (card %r still in %s %s) — card stays in "
                "%s, re-launch after %ds cooldown; last session line: %s",
                pid, card, lane_name, mode_lane, lane_name, COOLDOWN_NORMAL_SECONDS, last_line)
        else:
            log("exit: worker pid %d gone (card %r left %s; %s now %s) — "
                "slot free; last session line: %s",
                pid, card, lane_name, lane_name, mode_lane or "empty", last_line)
        state["last_exit_at"] = now
        state["slot"] = None
        state["cooldown_announced"] = False
        save_state(state)
        return

    # Worker alive: track the slot card, arm / check the exit timer.
    if mode_lane is not None:
        card = slot["card"]
        if card in mode_lane:
            slot["card_seen_active"] = True
        elif len(mode_lane) == 1 and mode_lane[0] != card:
            slot["card"] = mode_lane[0]
            card = mode_lane[0]
            slot["card_seen_active"] = True
            log("slot: card is %r (pid %d)", card, pid)
            save_state(state)

        # Arm the exit timer (mode-aware).
        if slot["exit_timer_armed_at"] is None:
            seen = slot.get("card_seen_active")
            in_lane = card in mode_lane
            if mode == "review":
                # Reviewer: arm when the card left Review (issues → Ready)
                # OR lost review-by-ai (clean pass — consumed, stays in Review).
                tagged = (card in review_tagged) if review_tagged is not None else None
                lost_tag = tagged is False
                if (seen and not in_lane) or lost_tag:
                    slot["exit_timer_armed_at"] = now
                    if lost_tag:
                        log("timer: exit timer armed (%ds) — card %r lost review-by-ai "
                            "(clean pass, stays in Review)", EXIT_TIMER_SECONDS, card)
                    else:
                        log("timer: exit timer armed (%ds) — card %r left Review",
                            EXIT_TIMER_SECONDS, card)
                    save_state(state)
            elif seen and not in_lane:
                # Implementer (unchanged): card left Active.
                slot["exit_timer_armed_at"] = now
                log("timer: exit timer armed (%ds) — card %r left Active",
                    EXIT_TIMER_SECONDS, card)
                save_state(state)
            # Grace-ended backstop (both modes): never seen in the mode lane
            # and the lane is now empty.
            if slot["exit_timer_armed_at"] is None \
                    and not seen and not mode_lane \
                    and now - slot["started_at"] >= GRACE_SECONDS:
                slot["exit_timer_armed_at"] = now
                log("timer: exit timer armed (%ds) — grace ended, no card ever in %s",
                    EXIT_TIMER_SECONDS, lane_name)
                save_state(state)

    if slot["exit_timer_armed_at"] is not None \
            and now - slot["exit_timer_armed_at"] >= EXIT_TIMER_SECONDS:
        log("kill: exit timer expired (pid %d, card %r) — SIGTERM", pid, slot["card"])
        kill_worker(state, "exit timer expired")


def evaluate_launch(state, now, active, onhold, ready, review_trigger=None):
    """Launch evaluation: eGPU probe -> trigger -> cooldown -> launch.

    Queue order: Active → Ready → OnHold → Review. `review_trigger` is the
    first Review card (top→bottom) tagged review-by-ai, or None (computed in
    tick from the board resource). Reviews never preempt in-flight (Active),
    fresh (Ready) or unblocking (OnHold) work.

    Pre-launch pull: a Ready trigger is moved into Active by the orchestrator
    itself (board_move_card, plain HTTP ~ms) before launch_worker — the card
    is in its target lane before the worker boots. On failure: anomaly logged,
    launch skipped, retried next tick. OnHold triggers are NOT pulled (the
    condition-cleared check is worker-side judgment; the worker claims with
    `tmd claim`).
    """
    if not egpu_up():
        if not state.get("egpu_down"):
            log("idle: eGPU server %s unreachable — no launches", EGPU_URL)
        state["egpu_down"] = True
        save_state(state)
        return
    if state.get("egpu_down"):
        log("idle: eGPU server back up")
    state["egpu_down"] = False

    if active:
        trigger, cooldown = ("Active", active[0]), COOLDOWN_NORMAL_SECONDS
    elif ready:
        trigger, cooldown = ("Ready", ready[0]), COOLDOWN_NORMAL_SECONDS
    elif onhold:
        trigger, cooldown = ("OnHold", onhold[0]), COOLDOWN_ONHOLD_ONLY_SECONDS
    elif review_trigger:
        trigger, cooldown = ("Review", review_trigger), COOLDOWN_NORMAL_SECONDS
    else:
        if not state.get("idle_no_work"):
            log("idle: no workable cards (Active/Ready/OnHold/Review empty)")
        state["idle_no_work"] = True
        save_state(state)
        return
    state["idle_no_work"] = False

    last_exit = state.get("last_exit_at")
    if last_exit is not None and now - last_exit < cooldown:
        if not state.get("cooldown_announced"):
            log("idle: re-launch cooldown (%ds) — %ds until launch (trigger %s/%s)",
                cooldown, int(cooldown - (now - last_exit)), trigger[0], trigger[1])
            state["cooldown_announced"] = True
            save_state(state)
        return

    # Pre-launch pull (Ready → Active): the move is plain HTTP (~ms, no
    # container, no LLM) — the card is in Active before the worker boots, so
    # card_seen_active is true from the first tick and the "no card ever in
    # Active" backstop cannot mis-fire for a launched worker. Active is empty
    # by construction (Ready is only reached when the Active trigger is
    # absent). On failure (user moved the card in the UI between read and
    # write): log anomaly, skip this launch, retry next tick.
    if trigger[0] == "Ready":
        try:
            board_move_card(trigger[1], "Ready", "Active")
            log("pull: %s -> Active at launch (pre-worker move)", trigger[1])
            trigger = ("Active", trigger[1])
        except Exception as e:
            log("anomaly: pre-launch pull %s -> Active failed (%s: %s) — "
                "skipping launch this tick",
                trigger[1], type(e).__name__, e)
            return

    launch_worker(state, now, trigger)


def tick(state, stopping):
    """One supervisor tick: poll -> liveness -> timers -> launch evaluation."""
    now = time.time()

    # 1. Board poll.
    try:
        sort = board_sort()
    except Exception as e:
        if not state.get("board_down"):
            log("idle: board down (%s) — no launches, no state writes", e)
            state["board_down"] = True
        watch_worker(state, now, mode_lane=None, review_tagged=None)
        return
    if state.get("board_down"):
        log("idle: board back up")
    state["board_down"] = False

    active = list(sort.get("Active") or [])
    onhold = list(sort.get("OnHold") or [])
    ready = list(sort.get("Ready") or [])
    review = list(sort.get("Review") or [])

    # Full board tree (file truth + tags), fetched once per tick.
    resource = None
    try:
        resource = board_resource()
    except Exception:
        resource = None

    # Cross-check the Active lane against file truth (sort.json can transiently
    # list cards whose file has already moved — concurrent movers). Two-way:
    # the file tree is authoritative for lane membership in BOTH directions.
    if resource is not None:
        on_disk = active_on_disk(resource)
        stale = [c for c in active if c not in on_disk]
        if stale:
            log("anomaly: sort lists %s in Active but file(s) absent on disk — "
                "ignored this tick", stale)
            active = [c for c in active if c in on_disk]
        # Reverse: a card physically in Active on disk but transiently missing
        # from sort.json is restored. Without this, a transiently missing sort
        # entry makes watch_worker() see the slot's card as "left Active" and
        # falsely arms the exit timer (the 2026-10-11 06:57 mis-fire). Appended
        # after the sort-ordered cards, so launch priority (active[0]) is
        # unchanged — evaluate_launch() only runs when the slot is free.
        missing = [c for c in on_disk if c not in active]
        if missing:
            log("anomaly: file(s) %s in Active on disk but absent from sort — "
                "restored this tick (file truth authoritative)", missing)
            active.extend(missing)
    if len(active) > 1:
        log("anomaly: %d cards in Active %s — taking topmost %r",
            len(active), active, active[0])

    # Cross-check the Review lane against file truth (same two-way gap; reviewer
    # mode previously had no file-truth cross-check at all).
    if resource is not None:
        review_disk = review_on_disk(resource)
        stale = [c for c in review if c not in review_disk]
        if stale:
            log("anomaly: sort lists %s in Review but file(s) absent on disk — "
                "ignored this tick", stale)
            review = [c for c in review if c in review_disk]
        missing = [c for c in review_disk if c not in review]
        if missing:
            log("anomaly: file(s) %s in Review on disk but absent from sort — "
                "restored this tick (file truth authoritative)", missing)
            review.extend(missing)

    # Review trigger: first Review card (top→bottom) tagged review-by-ai.
    review_trigger = first_review_tagged(resource) if resource is not None else None

    # 2. Worker liveness + 3. timers (mode-aware).
    slot = state["slot"]
    if slot is not None:
        mode = slot.get("mode", "implement")
        mode_lane = review if mode == "review" else active
        review_tagged = review_tags(resource) if (mode == "review" and resource is not None) else None
    else:
        mode_lane = None
        review_tagged = None
    watch_worker(state, now, mode_lane, review_tagged)

    # 4. Launch evaluation (disabled during graceful stop).
    if state["slot"] is None and not stopping:
        evaluate_launch(state, now, active, onhold, ready, review_trigger)


# --------------------------------------------------------------------------
# Startup adoption
# --------------------------------------------------------------------------
def adopt_at_startup(state):
    slot = state.get("slot")
    if slot is not None:
        pid = slot["pid"]
        if worker_identity_ok(slot):
            log("adopt: state-file worker pid=%d alive (card=%r) — resuming watch",
                pid, slot.get("card"))
            return
        log("adopt: state-file worker pid=%d dead (card=%r) — stuck-worker path on first tick",
            pid, slot.get("card"))
        return
    # No recorded slot: nothing to adopt. (The old /proc orphan scan was
    # removed — pi rewrites its process title at startup, so a cmdline-marker
    # scan can never match a live worker; state.json is the record.)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def setup_logging():
    fmt = logging.Formatter("%(asctime)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    fh = logging.FileHandler(LOG_FILE)
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    _logger.setLevel(logging.INFO)
    _logger.addHandler(fh)
    _logger.addHandler(sh)


def main():
    global PI_BIN
    os.makedirs(SESSION_LOG_DIR, exist_ok=True)
    setup_logging()

    # Single instance (flock; a second start exits immediately).
    lock_fh = open(LOCK_FILE, "w")
    try:
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        log("start: another orchestrator instance holds %s — exiting", LOCK_FILE)
        sys.exit(1)
    lock_fh.write(str(os.getpid()))
    lock_fh.flush()

    pi_path = shutil.which(PI_BIN)
    if not pi_path:
        log("start: FATAL: %r not found on PATH — workers cannot launch", PI_BIN)
        sys.exit(1)
    PI_BIN = pi_path

    state = load_state()
    log("start: orchestrator v1 (pid %d, board %s, eGPU %s, model=pi-default)",
        os.getpid(), BOARD_URL, EGPU_URL)
    adopt_at_startup(state)

    stopping = False
    force = False

    def on_signal(signum, _frame):
        nonlocal stopping, force
        if force:
            return
        if not stopping:
            stopping = True
            log("stop: graceful (signal %d) — no new launches; waiting for current worker",
                signum)
        else:
            force = True
            log("stop: forced (second signal) — killing worker, then exiting")

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    while True:
        if force:
            if state["slot"] is not None:
                kill_worker(state, "forced stop")
            log("stop: exiting (forced)")
            return
        try:
            tick(state, stopping)
        except Exception as e:
            # Backstop: a transient failure (Popen error, disk full on state
            # write, ...) must not kill the supervisor — log and keep ticking.
            log("anomaly: tick failed (%s: %s) — continuing", type(e).__name__, e)
        if stopping and state["slot"] is None:
            log("stop: no worker running — exiting (graceful)")
            return
        # Sleep in 1 s increments so a second signal is acted on promptly;
        # the tick interval itself stays TICK_SECONDS.
        for _ in range(TICK_SECONDS):
            if force:
                break
            time.sleep(1)


if __name__ == "__main__":
    main()
