#!/usr/bin/env python3
"""Dry-run validation for the AI-reviewer orchestrator changes.

Imports orchestrator.py and exercises the NEW logic in isolation — no worker
is launched, no eGPU is probed, no real board is mutated. HTTP + process
functions are monkeypatched, and STATE_FILE is redirected to a temp file so
no test can touch the live orchestrator/state.json (some watch_worker /
evaluate_launch paths call the real save_state). Run:
python3 orchestrator/test_review_dryrun.py
"""
import os
import sys
import types

ORCH_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ORCH_DIR)
import orchestrator as o  # noqa: E402

PASS = []
FAIL = []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail and not cond else ""))


# A fake board resource tree (lanes -> files with content), mirroring the
# live /_api/resource shape. Review order: clean card, tagged card, tagged card.
FAKE_RESOURCE = [
    {"name": "Active", "files": []},
    {"name": "Ready", "files": []},
    {"name": "OnHold", "files": []},
    {"name": "Review", "files": [
        {"name": "clean-card", "content": "[tag:ai-reviewed] [tag:genai_stack]\n\n# clean\n"},
        {"name": "tagged-first", "content": "[tag:review-by-ai] [tag:genai_stack]\n\n# first\n"},
        {"name": "tagged-second", "content": "[tag:review-by-ai]\n\n# second\n"},
    ]},
]


def test_tag_helpers():
    print("tag helpers (first_review_tagged / review_tags / _card_tags)")
    check("first_review_tagged skips clean, returns topmost tagged",
          o.first_review_tagged(FAKE_RESOURCE) == "tagged-first",
          f"got {o.first_review_tagged(FAKE_RESOURCE)!r}")
    check("review_tags returns both tagged cards",
          o.review_tags(FAKE_RESOURCE) == {"tagged-first", "tagged-second"},
          f"got {o.review_tags(FAKE_RESOURCE)!r}")
    check("_card_tags parses multi-tag line",
          o._card_tags("[tag:review-by-ai] [tag:genai_stack]\nrest") == ["review-by-ai", "genai_stack"])
    check("active_on_disk from resource", o.active_on_disk(FAKE_RESOURCE) == set())
    # No tagged cards -> None.
    empty = [dict(l, files=[dict(f, content="[tag:x]\n") for f in l["files"]]) for l in FAKE_RESOURCE]
    check("first_review_tagged None when no tags", o.first_review_tagged(empty) is None)


def _mk_state(slot=None):
    s = o.empty_state()
    s["slot"] = slot
    return s


def test_evaluate_launch_review_trigger():
    print("evaluate_launch — Review is the 4th trigger")
    # Monkeypatch the eGPU probe + launch + pre-launch pull so nothing real
    # happens (board_move_card would hit the live board otherwise).
    o.egpu_up = lambda: True
    o.board_move_card = lambda card, src, dst: None
    launched = {}

    def fake_launch(state, now, trigger):
        launched["trigger"] = trigger
        state["slot"] = {"pid": 999999, "card": trigger[1], "mode": "review" if trigger[0] == "Review" else "implement",
                         "start_time": None, "card_seen_active": False, "started_at": now,
                         "log_file": None, "exit_timer_armed_at": None}
    o.launch_worker = fake_launch

    now = 1_000_000.0
    # Active empty, Ready empty, OnHold empty, review_trigger set -> Review wins.
    st = _mk_state()
    o.evaluate_launch(st, now, active=[], onhold=[], ready=[], review_trigger="tagged-first")
    check("review trigger chosen when other lanes empty",
          launched.get("trigger") == ("Review", "tagged-first"), f"got {launched.get('trigger')!r}")
    check("slot mode = review", st["slot"]["mode"] == "review")

    # Ready present -> Ready preempts Review (and is pulled into Active:
    # the launch trigger is re-assigned to ("Active", card) after the pull).
    launched.clear()
    st = _mk_state()
    o.evaluate_launch(st, now, active=[], onhold=[], ready=["ready-card"], review_trigger="tagged-first")
    check("Ready preempts Review (pulled to Active)",
          launched.get("trigger") == ("Active", "ready-card"),
          f"got {launched.get('trigger')!r}")

    # Active present -> Active preempts all.
    launched.clear()
    st = _mk_state()
    o.evaluate_launch(st, now, active=["active-card"], onhold=[], ready=["ready-card"], review_trigger="tagged-first")
    check("Active preempts Ready+Review", launched.get("trigger") == ("Active", "active-card"),
          f"got {launched.get('trigger')!r}")

    # OnHold present, no Active/Ready -> OnHold preempts Review.
    launched.clear()
    st = _mk_state()
    o.evaluate_launch(st, now, active=[], onhold=["onhold-card"], ready=[], review_trigger="tagged-first")
    check("OnHold preempts Review", launched.get("trigger") == ("OnHold", "onhold-card"),
          f"got {launched.get('trigger')!r}")

    # Nothing at all -> no launch, idle_no_work set.
    launched.clear()
    st = _mk_state()
    o.evaluate_launch(st, now, active=[], onhold=[], ready=[], review_trigger=None)
    check("no launch when all lanes empty", "trigger" not in launched and st["idle_no_work"] is True)


def test_single_slot_guard():
    print("single-slot guarantee (structural)")
    # evaluate_launch is only ever called from tick() when slot is None.
    # Verify tick() does not call evaluate_launch while a slot is occupied.
    import inspect
    src = inspect.getsource(o.tick)
    check("tick gates evaluate_launch on slot is None",
          'if state["slot"] is None and not stopping:' in src)
    check("launch only via evaluate_launch (single path)",
          "launch_worker" not in src.replace("def launch_worker", ""))


def test_mode_aware_exit_timer():
    print("watch_worker — mode-aware exit timer arming")
    o.egpu_up = lambda: True
    now = 1_000_000.0

    # --- Reviewer: clean pass (card stays in Review, loses review-by-ai) ---
    slot = {"pid": 424242, "card": "tagged-first", "mode": "review", "start_time": None,
            "card_seen_active": True, "started_at": now - 100, "log_file": None,
            "exit_timer_armed_at": None}
    st = _mk_state(slot)
    # Worker "alive": make pid_alive True for this pid.
    o.pid_alive = lambda pid: True
    o.pid_start_time = lambda pid: None
    review_lane = ["tagged-first"]           # card still in Review
    review_tagged = set()                     # ...but lost the tag (clean pass)
    o.watch_worker(st, now, review_lane, review_tagged)
    check("reviewer clean pass arms timer (lost review-by-ai)",
          slot["exit_timer_armed_at"] is not None,
          f"armed_at={slot['exit_timer_armed_at']!r}")

    # --- Reviewer: issues found (card left Review -> Ready) ---
    slot = {"pid": 424242, "card": "tagged-first", "mode": "review", "start_time": None,
            "card_seen_active": True, "started_at": now - 100, "log_file": None,
            "exit_timer_armed_at": None}
    st = _mk_state(slot)
    review_lane = []                          # card left Review
    review_tagged = set()
    o.watch_worker(st, now, review_lane, review_tagged)
    check("reviewer issues (left Review) arms timer",
          slot["exit_timer_armed_at"] is not None, f"armed_at={slot['exit_timer_armed_at']!r}")

    # --- Reviewer: still working (in Review + still tagged) -> NO arm ---
    slot = {"pid": 424242, "card": "tagged-first", "mode": "review", "start_time": None,
            "card_seen_active": True, "started_at": now - 100, "log_file": None,
            "exit_timer_armed_at": None}
    st = _mk_state(slot)
    review_lane = ["tagged-first"]
    review_tagged = {"tagged-first"}
    o.watch_worker(st, now, review_lane, review_tagged)
    check("reviewer still working does NOT arm", slot["exit_timer_armed_at"] is None,
          f"armed_at={slot['exit_timer_armed_at']!r}")

    # --- Implementer: card left Active -> arm (unchanged behavior) ---
    slot = {"pid": 424242, "card": "impl-card", "mode": "implement", "start_time": None,
            "card_seen_active": True, "started_at": now - 100, "log_file": None,
            "exit_timer_armed_at": None}
    st = _mk_state(slot)
    o.watch_worker(st, now, [], None)
    check("implementer card left Active arms timer",
          slot["exit_timer_armed_at"] is not None, f"armed_at={slot['exit_timer_armed_at']!r}")

    # --- Implementer: card in Active -> no arm ---
    slot = {"pid": 424242, "card": "impl-card", "mode": "implement", "start_time": None,
            "card_seen_active": True, "started_at": now - 100, "log_file": None,
            "exit_timer_armed_at": None}
    st = _mk_state(slot)
    o.watch_worker(st, now, ["impl-card"], None)
    check("implementer card in Active does NOT arm", slot["exit_timer_armed_at"] is None)

    # --- Grace-ended backstop (reviewer): never seen, Review empty, grace over ---
    slot = {"pid": 424242, "card": "tagged-first", "mode": "review", "start_time": None,
            "card_seen_active": False, "started_at": now - (o.GRACE_SECONDS + 10), "log_file": None,
            "exit_timer_armed_at": None}
    st = _mk_state(slot)
    o.watch_worker(st, now, [], set())
    check("reviewer grace-ended backstop arms", slot["exit_timer_armed_at"] is not None)


def test_worker_model_passthrough():
    print("WORKER_MODEL per-mode config + --model passthrough")
    check("WORKER_MODEL has both modes", set(o.WORKER_MODEL) == {"implement", "review"})
    check("V1 both None (pi default)", o.WORKER_MODEL["implement"] is None and o.WORKER_MODEL["review"] is None)
    # Simulate the cmd build in launch_worker (card-specific prompts).
    for mode, model in (("implement", None), ("review", "igpu-Gemma4-26B-A4B")):
        if mode == "review":
            entry_prompt = o.reviewer_entry_prompt("rev-card")
        else:
            entry_prompt = o.implementer_entry_prompt("Active", "impl-card")
        cmd = [o.PI_BIN, "-p", entry_prompt]
        if model:
            cmd += ["--model", model]
        expected = ["--model", "igpu-Gemma4-26B-A4B"] if model else None
        if expected:
            check(f"cmd includes --model for {mode}", cmd[-2:] == expected, f"cmd={cmd}")
        else:
            check(f"cmd has no --model for {mode} (None)", "--model" not in cmd, f"cmd={cmd}")


def main():
    # Hermetic: point the state file at a temp file so no test can touch the
    # live orchestrator/state.json (2026-10-11 12:28 review finding 1: the
    # unpatched save_state overwrote it with fixture data). Covers every path
    # (save_state, load_state), unlike a save_state monkeypatch alone.
    import tempfile
    o.STATE_FILE = os.path.join(tempfile.mkdtemp(prefix="orch-test-"), "state.json")
    test_tag_helpers()
    test_evaluate_launch_review_trigger()
    test_single_slot_guard()
    test_mode_aware_exit_timer()
    test_worker_model_passthrough()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED:", FAIL)
        sys.exit(1)
    print("ALL PASS")


if __name__ == "__main__":
    main()
