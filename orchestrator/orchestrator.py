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
# Tunables (constants by design — no flags, no env vars; the one exception:
# the EGPU_BUSY_* overrides below, which are hardware-calibrated to this
# host's eGPU and operator-tunable at runtime)
# --------------------------------------------------------------------------
BOARD_URL = "http://localhost:8090"            # tasks.md board
EGPU_URL = "http://192.168.1.XX:8092"          # llama-server (worker brain)
# Worker model/provider: NO override here. The worker uses pi's own defaults
# (defaultModel / defaultProvider in ~/.pi/agent/settings.json). Note that
# PI_MODEL / PI_PROVIDER are pi *output* vars (injected into shell tools),
# not inputs — setting them on the worker env did nothing.
# Managed pi launcher (reads ~/.pi/agent/install/current-version itself, so
# version bumps don't touch this). Absolute path on purpose: the .bashrc PATH
# export only exists in interactive shells, and a non-interactive launch
# (script/cron/systemd) would otherwise fail Popen with FileNotFoundError.
# Falls back to PATH lookup if the managed launcher is missing.
_PI_LAUNCHER = os.path.expanduser("~/.pi/agent/bin/pi")
PI_BIN = _PI_LAUNCHER if os.path.exists(_PI_LAUNCHER) else "pi"

TICK_SECONDS = 20                  # supervisor tick interval (the only sleep)
GRACE_SECONDS = 300                # startup grace: no kill inside this window
EXIT_TIMER_SECONDS = 120           # kill if still alive this long after arming
COOLDOWN_NORMAL_SECONDS = 60       # re-launch cooldown (Active/Ready pending)
COOLDOWN_ONHOLD_ONLY_SECONDS = 300  # re-launch cooldown (only trigger: OnHold)
FORCE_KILL_GRACE_SECONDS = 15      # SIGTERM -> SIGKILL grace
HTTP_TIMEOUT_SECONDS = 5           # board / eGPU probe timeout

# eGPU busy gate (the env-var exception to "constants by design"): measured
# defaults from this host's eGPU (RX 7900 XT, drm card1) — idle baseline is
# exactly 0%, active inference 86-93%. Each is overridable per call via the
# same-named env var (EGPU_BUSY_BLOCK_PCT, EGPU_BUSY_RESUME_PCT,
# EGPU_BUSY_WINDOW_SAMPLES, EGPU_BUSY_SAMPLE_INTERVAL_S), so operator changes
# take effect without an orchestrator restart. The 5-point hysteresis band
# (5-10) prevents flapping; a false "busy" costs at most one tick, a false
# "idle" would kill an in-flight background task AND the new worker session.
EGPU_BUSY_SYSFS = "/sys/class/drm/card1/device/gpu_busy_percent"  # card1 = eGPU (card2 = iGPU, NOT gated — persistent ~92% baseline)
EGPU_BUSY_BLOCK_PCT_DEFAULT = 10   # windowed avg >= 10% -> busy -> block launches
EGPU_BUSY_RESUME_PCT_DEFAULT = 5   # windowed avg < 5% -> idle -> allow launches
EGPU_BUSY_WINDOW_SAMPLES_DEFAULT = 5
EGPU_BUSY_SAMPLE_INTERVAL_S_DEFAULT = 2

# Markers embedded in the worker prompts (provenance only — pi rewrites its
# process title at startup, so they are NOT usable for process detection).
# The marker in the entry prompt also assigns the worker's ROLE: the agent
# never infers its role from board state (see tasks-board "Role dispatch").
WORKER_MARKER = "board-worker-v1"        # implementer
REVIEWER_MARKER = "board-reviewer-v1"    # reviewer
REFINER_MARKER = "board-refiner-v1"      # refiner


def implementer_entry_prompt(lane, card):
    """Card-specific implementer prompt (built at launch).

    The card is already in its target lane: Ready triggers are pulled into
    `Active` by the orchestrator at launch time (pre-launch pull), so the
    worker never selects from `Ready`. OnHold triggers with a satisfied
    canonical condition are pulled the same way (OnHold → Active). The OnHold
    scan exception stays worker-side for NON-canonical conditions (legacy
    prose, external conditions like "gitea reachable"): the condition-cleared
    check needs judgment (reading the card's Log), which the orchestrator
    cannot do — the worker claims with `tmd claim`.
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


def refiner_entry_prompt(card):
    """Card-specific refiner prompt (built at launch).

    The refiner works IN PLACE in the Spec lane — the card never moves before
    the worker boots (no pre-launch pull). It refines the card per the
    canonical template, parks it in AskUser with a refinement section if there
    are open points, or marks it refined (AskUser) when done.
    """
    return (f"[{REFINER_MARKER}] You are a board refiner. Read "
            ".pi/skills/tasks-board/SKILL.md and follow it: refine card "
            f"`Spec/{card}` in place per the canonical template, park it in "
            "AskUser with a refinement section if there are open points, or "
            "mark it refined (AskUser) when done; one card per session.")

# Per-mode worker model (V1: all None = pi default, one shared eGPU slot).
# When set, the worker is launched with `--model <pattern>` (pi CLI flag;
# supports "provider/id"). V2 (future iGPU): review = "igpu-..." + a 2nd
# independent single-slot queue (see README).
# Model precedence at launch: card `## LLM` section > per-mode WORKER_MODEL
# > pi default (no --model flag).
WORKER_MODEL = {"implement": None, "review": None, "refine": None}

# Known-models allowlist for the card's `## LLM` section (union of the two
# llama-server presets llamacpp/models-egpu-rdna.ini +
# llamacpp/models-igpu.ini; verified live 08.11.2026). Bare model IDs — no
# provider prefix (`://` breaks the `provider/id` split in `--model`); the
# `egpu-`/`igpu-` prefix encodes the server and the IDs are globally unique.
# The card-facing copy of this vocabulary lives in the canonical card
# template's "known models" appendix
# (.pi/skills/tasks-board/card-template.md) — keep the two in sync.
KNOWN_MODELS = frozenset({
    "egpu-SWIFT-1.5",            # pi default (no `## LLM` section needed)
    "egpu-SWIFT-1.5-Uncensored",  # uncensored Swift 1.5 eGPU (pentesting)
    "igpu-Gemma4-26B-A4B",       # iGPU (V2 concern — v1 is eGPU-only)
    "igpu-Qwen3.6-35B-A3B",      # iGPU (V2 concern — v1 is eGPU-only)
})

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
    tags = []
    for group in re.findall(r"\[tag:([^\]]+)\]", first_line):
        # Lenient: split comma-joined groups (legacy `[tag:a,b]` corruption)
        # so a malformed card is still recognized instead of stalling the
        # review loop silently (the 29.10.2026 11-min stall). Loud: log an
        # anomaly when a comma-joined group is detected.
        parts = [p.strip() for p in group.split(",")]
        if len(parts) > 1:
            log("anomaly: comma-joined tag group %r on a card line 1 — "
                "normalized to %s (legacy corruption; fix with `tmd tag`)",
                group, parts)
        tags.extend(p for p in parts if p)
    return tags


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


def spec_on_disk(resource):
    """Card names physically present in the Spec lane (file truth).

    Same rationale as active_on_disk(): the file tree is authoritative for
    lane membership; sort.json can transiently miss entries.
    """
    return {f.get("name") for f in _lane_files(resource, "Spec")}


def first_spec_unrefined(resource):
    """First Spec card (top→bottom) WITHOUT the refined tag. None if none.

    Position = priority (exactly like Review). A card already tagged `refined`
    (refinement done, awaiting the human's Ready/Backlog decision) is skipped,
    not a blocker — the hot-loop guard (G5).
    """
    for f in _lane_files(resource, "Spec"):
        if "refined" not in _card_tags(f.get("content", "")):
            return f.get("name")
    return None


# Canonical OnHold chain condition (tasks-board skill, "OnHold chain
# condition"): the predecessor card has the `ai-reviewed` tag AND is in the
# Review or Done lane. A card states it in its `## OnHold condition` section
# as a `Condition:` line naming the predecessor in quotes. Backticks and the
# bold markers are optional (the skill's template wraps the literals, real
# cards often don't).
_CANONICAL_ONHOLD_CONDITION = re.compile(
    r'(?m)^\s*\*{0,2}Condition:\*{0,2}\s+the\s+"(?P<card>[^"]+)"\s+card\s+'
    r'has\s+the\s+`?ai-reviewed`?\s+tag\s+AND\s+is\s+in\s+the\s+`?Review`?\s+'
    r'or\s+`?Done`?\s+lane\.')


def _onhold_condition_section(content):
    """Text of the card's `## OnHold condition` section (any heading suffix),
    up to the next `## ` heading or end of card. None if the section is absent.

    Legacy cards use suffixed headings (`## OnHold condition (mechanically
    checkable — ALL must be true)`) with numbered external conditions — those
    sections contain no canonical `Condition:` line, so matching the suffix is
    harmless.
    """
    m = re.search(r'(?m)^## OnHold condition[^\n]*\n(.*?)(?=^## |\Z)',
                  content, re.DOTALL)
    return m.group(1) if m else None


def _card_llm_model(content):
    """Model ID from the card's `## LLM` section (`- Model: <model-id>` line).

    None if the section or the line is absent (the common case — the pi
    default applies). The returned ID is NOT validated here; the caller
    validates it against KNOWN_MODELS (invalid -> pi default + anomaly log).
    """
    m = re.search(r'(?m)^## LLM[^\n]*\n(.*?)(?=^## |\Z)', content, re.DOTALL)
    if not m:
        return None
    lm = re.search(r'(?m)^\s*-\s*Model:\s*`?([^`\s]+)`?', m.group(1))
    return lm.group(1) if lm else None


def _card_repo_name(content):
    """Repo name from the card's `## Repo` section (`- Name: <name>` line).

    None if the section or the line is absent (the common case — the worker
    runs from STACK_ROOT). The returned name is NOT validated here; the
    caller validates it (path separators / missing checkout -> fallback +
    anomaly log).
    """
    m = re.search(r'(?m)^## Repo[^\n]*\n(.*?)(?=^## |\Z)', content, re.DOTALL)
    if not m:
        return None
    nm = re.search(r'(?m)^\s*-\s*Name:\s*`?([^`\s]+)`?', m.group(1))
    return nm.group(1) if nm else None


def _resolve_card_model(resource, card):
    """Validated model ID for a trigger card's `## LLM` section, or None.

    None = the pi default applies (section absent — the common case — or the
    ID is not in KNOWN_MODELS, which also logs an anomaly). The launch never
    fails on model choice. `resource` is the board file tree (already fetched
    in tick) — no extra HTTP.
    """
    if resource is None:
        return None
    content = ""
    for lane_obj in resource:
        for f in lane_obj.get("files", []):
            if f.get("name") == card:
                content = f.get("content", "")
                break
    model = _card_llm_model(content)
    if model is None:
        return None
    if model not in KNOWN_MODELS:
        log("anomaly: card %r `## LLM` model %r not in the known-models "
            "allowlist %s — falling back to the pi default (launch not "
            "failed)", card, model, sorted(KNOWN_MODELS))
        return None
    return model


def _resolve_worker_cwd(resource, card):
    """Launch cwd for a trigger card's `## Repo` section, or STACK_ROOT.

    STACK_ROOT = today's behavior (section absent — the common case — or the
    name is unusable, which also logs an anomaly). The launch never fails on
    cwd resolution (same philosophy as `## LLM` model choice). `resource` is
    the board file tree (already fetched in tick) — no extra HTTP.

    Rules:
    - `## Repo` present, `Name` is a plain directory name (no path
      separators), and `work/orchestrator/<name>` exists -> that checkout
      (the session lands in the repo's own Hindsight bank,
      `coding-agent::<name>`).
    - `Name` equals the stack repo's own basename -> STACK_ROOT (the live
      stack root IS that repo's checkout; the work-folder copy is a second
      clone — editing it would edit the wrong tree).
    - Otherwise (no `## Repo`, missing checkout, invalid name) -> STACK_ROOT
      (anomaly logged when `## Repo` is present but unusable).
    """
    if resource is None:
        return STACK_ROOT
    content = ""
    for lane_obj in resource:
        for f in lane_obj.get("files", []):
            if f.get("name") == card:
                content = f.get("content", "")
                break
    name = _card_repo_name(content)
    if name is None:
        return STACK_ROOT
    if name == os.path.basename(STACK_ROOT):
        return STACK_ROOT
    if "/" in name or "\\" in name:
        log("anomaly: card %r `## Repo` name %r contains a path separator — "
            "falling back to the stack root cwd (launch not failed)",
            card, name)
        return STACK_ROOT
    checkout = os.path.join(STACK_ROOT, "work", "orchestrator", name)
    if not os.path.isdir(checkout):
        log("anomaly: card %r `## Repo` checkout %s missing — falling back "
            "to the stack root cwd (launch not failed; first-run exception — "
            "this session's work lands in the stack bank)",
            card, checkout)
        return STACK_ROOT
    return checkout


def onhold_precheck(onhold, resource):
    """Cheap pre-check over the OnHold lane before launching a scan worker.

    Returns the OnHold trigger for evaluate_launch():
    - ("OnHold", card): launch a scan worker (worker-side judgment) — at
      least one card's condition is NOT in the canonical tag-based form
      (legacy prose, external conditions like "gitea reachable") and no
      canonical condition is satisfied.
    - ("Active", card): a canonical condition IS satisfied (the predecessor's
      line 1 has `ai-reviewed` and its lane is Review or Done) — the
      orchestrator pulls the card OnHold → Active itself (pre-launch pull,
      like Ready) and the worker works it as a normal Active card. No scan
      worker.
    - None: every card's condition is canonical and none is satisfied —
      skip the launch this tick (the scan hot-loop guard).

    The pre-check is an optimization, not a gate: it recognizes only the
    canonical tag-based form; everything else falls through to a worker scan.
    `resource` is the board file tree (already fetched in tick) — no extra
    HTTP. A predecessor missing from the board is mechanically unsatisfied
    (canonical, not satisfied) — the card waits for a human fix, no hot loop.
    """
    if not onhold:
        return None
    board = {}
    for lane_obj in resource:
        for f in lane_obj.get("files", []):
            board[f.get("name")] = (lane_obj.get("name"), f.get("content", ""))
    non_canonical = False
    for card in onhold:
        content = board.get(card, (None, ""))[1]
        section = _onhold_condition_section(content)
        m = _CANONICAL_ONHOLD_CONDITION.search(section) if section else None
        if not m:
            non_canonical = True
            continue
        pred_lane, pred_content = board.get(m.group("card"), (None, ""))
        if pred_lane in ("Review", "Done") \
                and "ai-reviewed" in _card_tags(pred_content):
            return ("Active", card)
    if non_canonical:
        return ("OnHold", onhold[0])
    return None


def egpu_up():
    """Probe the eGPU llama-server (GET /v1/models)."""
    try:
        _http_json(EGPU_URL + "/v1/models")
        return True
    except Exception:
        return False


def _egpu_busy_env(name, default):
    """Read an EGPU_BUSY_* env-var tunable (per call — operator changes take
    effect without an orchestrator restart); missing/invalid -> default."""
    try:
        return int(os.environ.get(name))
    except (TypeError, ValueError):
        return default


def _read_gpu_busy():
    """One read of card1 gpu_busy_percent (int 0-100); None on read failure."""
    try:
        with open(EGPU_BUSY_SYSFS) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def egpu_busy_avg():
    """Windowed average of eGPU GPU-core utilization (card1 = RX 7900 XT).

    Takes EGPU_BUSY_WINDOW_SAMPLES (default 5) reads of
    /sys/class/drm/card1/device/gpu_busy_percent, EGPU_BUSY_SAMPLE_INTERVAL_S
    (default 2) seconds apart — a 10 s windowed average. Called only when a
    launch is being evaluated (no sampling cost on idle ticks). The caller
    applies the hysteresis thresholds (EGPU_BUSY_BLOCK_PCT / RESUME_PCT).

    Returns the integer average, or None on any read failure (the caller
    fails closed — an unknown state must not permit a launch).
    """
    n = _egpu_busy_env("EGPU_BUSY_WINDOW_SAMPLES", EGPU_BUSY_WINDOW_SAMPLES_DEFAULT)
    if n < 1:
        n = EGPU_BUSY_WINDOW_SAMPLES_DEFAULT
    interval = _egpu_busy_env("EGPU_BUSY_SAMPLE_INTERVAL_S",
                              EGPU_BUSY_SAMPLE_INTERVAL_S_DEFAULT)
    samples = []
    for i in range(n):
        v = _read_gpu_busy()
        if v is None:
            return None
        samples.append(v)
        if i < n - 1:
            time.sleep(interval)
    return sum(samples) // len(samples)


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
        "egpu_busy": False,
        "idle_no_work": False,
        "cooldown_announced": False,
        "onhold_blocked_announced": False,
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
def launch_worker(state, now, trigger, card_model=None, worker_cwd=None):
    """Launch the worker for a trigger. `card_model` is the validated model ID
    from the trigger card's `## LLM` section (None = section absent or its ID
    failed validation — see _resolve_card_model). Model precedence: card
    `## LLM` > per-mode WORKER_MODEL > pi default (no --model flag).
    `worker_cwd` is the resolved launch cwd from the trigger card's
    `## Repo` section (None = no `## Repo` or it is unusable — see
    _resolve_worker_cwd). When it differs from STACK_ROOT the launch gains
    `--skill <STACK_ROOT>/.pi/skills` (the board skills are project skills of
    the stack root; a checkout has no `.pi`) + `--approve` (explicit
    project-trust decision for the automated run), and the entry prompt notes
    the checkout cwd (the worker's repo-setup step operates on `.`)."""
    os.makedirs(SESSION_LOG_DIR, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    log_file = os.path.join(SESSION_LOG_DIR, f"session-{ts}.log")
    n = 1
    while os.path.exists(log_file):  # same-second relaunch guard
        log_file = os.path.join(SESSION_LOG_DIR, f"session-{ts}-{n}.log")
        n += 1
    lane, card = trigger
    mode = "review" if lane == "Review" else (
        "refine" if lane == "Spec" else "implement")
    model = card_model or WORKER_MODEL.get(mode)
    cwd = worker_cwd if worker_cwd is not None else STACK_ROOT
    repo_cwd = cwd != STACK_ROOT
    if mode == "review":
        entry_prompt = reviewer_entry_prompt(card)
    elif mode == "refine":
        entry_prompt = refiner_entry_prompt(card)
    else:
        entry_prompt = implementer_entry_prompt(lane, card)
    if repo_cwd:
        entry_prompt += (f" Note: the session cwd is the repo checkout "
                         f"`{cwd}` (the card's `## Repo` target) — your "
                         f"repo-setup step operates on `.` there; do not "
                         f"clone into a subpath.")
    cmd = [PI_BIN, "-p", entry_prompt]
    if model:
        cmd += ["--model", model]
    if repo_cwd:
        cmd += ["--skill", os.path.join(STACK_ROOT, ".pi", "skills"),
                "--approve"]
    env = os.environ.copy()
    with open(log_file, "wb") as lf:
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=env,
            stdout=lf,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,  # survive orchestrator death / terminal Ctrl-C
        )
    state["slot"] = {
        "pid": proc.pid,
        "card": card,               # seeded from the trigger; refined on ticks
        "mode": mode,               # "implement" | "review" | "refine"
        "start_time": pid_start_time(proc.pid),
        "card_seen_active": False,  # set once the card is observed in the mode lane
        "started_at": now,
        "log_file": os.path.relpath(log_file, ORCH_DIR),
        "exit_timer_armed_at": None,
    }
    state["last_launch_at"] = now
    state["cooldown_announced"] = False
    save_state(state)
    log("launch: pid=%d trigger=%s/%s mode=%s model=%s cwd=%s log=%s",
        proc.pid, lane, card, mode, model or "pi-default", cwd,
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
    implement, Review for review, Spec for refine), or None when the board is
    down (board-dependent checks are deferred). `review_tagged` = set of
    Review cards currently tagged review-by-ai (reviewer mode only; None
    otherwise).
    """
    slot = state["slot"]
    if slot is None:
        return
    pid = slot["pid"]
    mode = slot.get("mode", "implement")
    lane_name = ("Review" if mode == "review"
                 else "Spec" if mode == "refine" else "Active")

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
        elif len(mode_lane) == 1 and mode_lane[0] != card \
                and not slot["card_seen_active"]:
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
                # Implementer / refiner: card left its mode lane (Active/Spec).
                slot["exit_timer_armed_at"] = now
                log("timer: exit timer armed (%ds) — card %r left %s",
                    EXIT_TIMER_SECONDS, card, lane_name)
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


def evaluate_launch(state, now, active, onhold, ready, review_trigger=None,
                    spec_trigger=None, onhold_trigger=None, resource=None):
    """Launch evaluation: eGPU probe -> trigger -> eGPU busy gate -> cooldown -> launch.

    `resource` is the board file tree (already fetched in tick) — used to
    resolve the trigger card's `## LLM` model (validated against
    KNOWN_MODELS; absent/invalid -> pi default, the launch never fails)
    and its `## Repo` launch cwd (checkout present -> that checkout; absent
    / invalid -> STACK_ROOT, the launch never fails).

    Queue order: Active → Spec → Review → Ready → OnHold. `spec_trigger` is
    the first Spec card (top→bottom) WITHOUT the refined tag, or None
    (computed in tick from the board resource). `review_trigger` is the first
    Review card (top→bottom) tagged review-by-ai, or None. `onhold_trigger`
    is the OnHold pre-check's decision (computed in tick from the board
    resource, see onhold_precheck()): ("OnHold", card) = launch a scan worker
    (worker-side judgment — at least one non-canonical condition),
    ("Active", card) = a canonical tag-based condition is satisfied (the
    orchestrator pulls the card OnHold → Active itself, see the pre-launch
    pull below), None = no OnHold trigger (lane empty, or every condition
    canonical and unsatisfied — the scan hot-loop guard). Only in-flight
    (Active) work takes precedence over everything; Spec (refinement)
    preempts Review/Ready/OnHold.

    Pre-launch pull: a Ready trigger is moved into Active by the orchestrator
    itself (board_move_card, plain HTTP ~ms) before launch_worker — the card
    is in its target lane before the worker boots. On failure: anomaly logged,
    launch skipped, retried next tick. An OnHold trigger with a satisfied
    canonical condition is pulled the same way (OnHold → Active); the
    worker-side claim (`tmd claim`) remains the fallback for non-canonical
    conditions (the scan worker). Spec triggers are NOT pulled (the refiner
    works in place in Spec — the card never moves before the worker boots).
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
    elif spec_trigger:
        trigger, cooldown = ("Spec", spec_trigger), COOLDOWN_NORMAL_SECONDS
    elif review_trigger:
        trigger, cooldown = ("Review", review_trigger), COOLDOWN_NORMAL_SECONDS
    elif ready:
        trigger, cooldown = ("Ready", ready[0]), COOLDOWN_NORMAL_SECONDS
    elif onhold_trigger:
        trigger, cooldown = onhold_trigger, COOLDOWN_ONHOLD_ONLY_SECONDS
    else:
        if onhold:
            # OnHold pre-check: every card's condition is in the canonical
            # tag-based form and none is satisfied — no scan worker (the
            # hot-loop guard). Log once, in the style of the idle/cooldown
            # announcements.
            if not state.get("onhold_blocked_announced"):
                log("idle: OnHold pre-check — %d card(s), all canonical "
                    "conditions unsatisfied — no scan worker", len(onhold))
                state["onhold_blocked_announced"] = True
        elif not state.get("idle_no_work"):
            log("idle: no workable cards (Active/Review/Ready/OnHold empty)")
        state["idle_no_work"] = True
        save_state(state)
        return
    state["idle_no_work"] = False
    state["onhold_blocked_announced"] = False

    # eGPU busy gate (complements the cooldown: the cooldown handles fast
    # crash loops, this handles long compute occupation). A worker whose
    # session died while a background task still owns the eGPU must not be
    # re-launched — the restart would disturb the eGPU compute and kill the
    # new session too. 10 s windowed average, taken only now that a trigger
    # was selected (no sampling cost on idle ticks). Hysteresis: avg >=
    # BLOCK_PCT -> busy, avg < RESUME_PCT -> idle, in between the state keeps
    # its value. Read failure -> fail closed (busy). Busy mirrors egpu_down:
    # log once on transition, return before the cooldown check -> no launch,
    # last_exit_at/cooldown_announced untouched (no cooldown reset), retry
    # next tick.
    avg = egpu_busy_avg()
    if avg is None:
        if not state.get("egpu_busy"):
            log("anomaly: eGPU busy read failed — treating as busy, no launches")
        state["egpu_busy"] = True
        save_state(state)
        return
    if state.get("egpu_busy"):
        if avg < _egpu_busy_env("EGPU_BUSY_RESUME_PCT", EGPU_BUSY_RESUME_PCT_DEFAULT):
            log("idle: eGPU back to idle (%d%%)", avg)
            state["egpu_busy"] = False
            save_state(state)
    else:
        if avg >= _egpu_busy_env("EGPU_BUSY_BLOCK_PCT", EGPU_BUSY_BLOCK_PCT_DEFAULT):
            log("idle: eGPU busy (%d%%) — no launches", avg)
            state["egpu_busy"] = True
            save_state(state)
    if state.get("egpu_busy"):
        return  # skip this tick: no launch, no cooldown reset; retry next tick

    last_exit = state.get("last_exit_at")
    if last_exit is not None and now - last_exit < cooldown:
        if not state.get("cooldown_announced"):
            log("idle: re-launch cooldown (%ds) — %ds until launch (trigger %s/%s)",
                cooldown, int(cooldown - (now - last_exit)), trigger[0], trigger[1])
            state["cooldown_announced"] = True
            save_state(state)
        return

    # Pre-launch pull (Ready → Active, OnHold → Active): the move is plain
    # HTTP (~ms, no container, no LLM) — the card is in Active before the
    # worker boots, so card_seen_active is true from the first tick and the
    # "no card ever in Active" backstop cannot mis-fire for a launched
    # worker. Active is empty by construction (these triggers are only
    # reached when the Active trigger is absent). On failure (user moved the
    # card in the UI between read and write): log anomaly, skip this launch,
    # retry next tick.
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
    elif trigger[0] == "Active" and not active:
        # OnHold pre-check: a canonical tag-based condition is satisfied —
        # the orchestrator claims the card itself (mechanical, no worker
        # judgment), mirroring the Ready pull. The Active list is empty by
        # construction, so an ("Active", card) trigger here always comes from
        # the OnHold pre-check.
        try:
            board_move_card(trigger[1], "OnHold", "Active")
            log("pull: %s -> Active at launch (OnHold canonical condition "
                "satisfied, pre-worker move)", trigger[1])
        except Exception as e:
            log("anomaly: OnHold pre-launch pull %s -> Active failed (%s: %s) — "
                "skipping launch this tick",
                trigger[1], type(e).__name__, e)
            return

    launch_worker(state, now, trigger, _resolve_card_model(resource, trigger[1]),
                  _resolve_worker_cwd(resource, trigger[1]))


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
    spec = list(sort.get("Spec") or [])

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

    # Cross-check the Spec lane against file truth (same two-way gap; refiner
    # mode — the refiner works in place in Spec).
    if resource is not None:
        spec_disk = spec_on_disk(resource)
        stale = [c for c in spec if c not in spec_disk]
        if stale:
            log("anomaly: sort lists %s in Spec but file(s) absent on disk — "
                "ignored this tick", stale)
            spec = [c for c in spec if c in spec_disk]
        missing = [c for c in spec_disk if c not in spec]
        if missing:
            log("anomaly: file(s) %s in Spec on disk but absent from sort — "
                "restored this tick (file truth authoritative)", missing)
            spec.extend(missing)

    # Review trigger: first Review card (top→bottom) tagged review-by-ai.
    review_trigger = first_review_tagged(resource) if resource is not None else None
    # Spec trigger: first Spec card (top→bottom) WITHOUT the refined tag.
    spec_trigger = first_spec_unrefined(resource) if resource is not None else None
    # OnHold trigger: cheap pre-check (no worker, no extra HTTP — the
    # resource is already fetched): canonical tag-based conditions are
    # mechanically checkable, so the orchestrator decides launch/skip/pull
    # itself. Resource unavailable -> fall back to a scan worker (the
    # pre-check is an optimization, not a gate).
    if resource is not None:
        onhold_trigger = onhold_precheck(onhold, resource)
    else:
        onhold_trigger = ("OnHold", onhold[0]) if onhold else None

    # 2. Worker liveness + 3. timers (mode-aware).
    slot = state["slot"]
    if slot is not None:
        mode = slot.get("mode", "implement")
        if mode == "review":
            mode_lane = review
        elif mode == "refine":
            mode_lane = spec
        else:
            mode_lane = active
        review_tagged = review_tags(resource) if (mode == "review" and resource is not None) else None
    else:
        mode_lane = None
        review_tagged = None
    watch_worker(state, now, mode_lane, review_tagged)

    # 4. Launch evaluation (disabled during graceful stop).
    if state["slot"] is None and not stopping:
        evaluate_launch(state, now, active, onhold, ready, review_trigger,
                        spec_trigger, onhold_trigger, resource)


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
