#!/usr/bin/env python3
"""Dry-run validation for the two-way file-truth reconciliation (Work item A).

Imports orchestrator.py and exercises the NEW reconciliation in tick() in
isolation — no worker is launched, no eGPU is probed, no real board is
mutated. board_sort / board_resource / pid_alive / pid_start_time / egpu_up /
launch_worker / save_state / log are monkeypatched.

The headline case is the 2026-10-11 06:57 mis-fire: a slot whose card is
physically in Active on disk (fake resource) but transiently absent from the
sort-derived active list -> the exit timer must NOT arm (card treated as
in-lane) and an anomaly must be logged.

Run:  python3 orchestrator/test_reconcile_dryrun.py
"""
import os
import sys

ORCH_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ORCH_DIR)
import orchestrator as o  # noqa: E402

PASS = []
FAIL = []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail and not cond else ""))


def _mk_resource(active_files=(), review_files=(), review_tag="review-by-ai"):
    """Build a fake board resource tree (lanes -> files with content)."""
    return [
        {"name": "Active",
         "files": [{"name": n, "content": f"[tag:genai_stack]\n\n# {n}\n"} for n in active_files]},
        {"name": "Ready", "files": []},
        {"name": "OnHold", "files": []},
        {"name": "Review",
         "files": [{"name": n, "content": f"[tag:{review_tag}]\n\n# {n}\n"} for n in review_files]},
    ]


def _mk_slot(card, mode="implement", seen=True):
    now = 1_000_000.0
    return {
        "pid": 424242, "card": card, "mode": mode, "start_time": None,
        "card_seen_active": seen, "started_at": now - 100, "log_file": None,
        "exit_timer_armed_at": None,
    }


def _run_tick(sort_map, resource, slot):
    """Run one tick() with everything monkeypatched; return (state, log_lines)."""
    log_lines = []
    o.board_sort = lambda: sort_map
    o.board_resource = lambda: resource
    o.pid_alive = lambda pid: True
    o.pid_start_time = lambda pid: None
    o.egpu_up = lambda: True
    o.launch_worker = lambda state, now, trigger: None  # must not fire (slot occupied)
    o.save_state = lambda state: None
    orig_log = o.log
    o.log = lambda msg, *args: log_lines.append(msg % args if args else msg)

    state = o.empty_state()
    state["slot"] = slot
    try:
        o.tick(state, stopping=False)
    finally:
        o.log = orig_log
    return state, log_lines


def test_active_missing_restore():
    print("Active lane — missing-from-sort card restored (the 06:57 mis-fire fix)")
    slot = _mk_slot("impl-card", mode="implement", seen=True)
    # sort says Active is EMPTY, but the card is physically in Active on disk.
    sort_map = {"Active": [], "OnHold": [], "Ready": [], "Review": []}
    resource = _mk_resource(active_files=("impl-card",))
    state, log_lines = _run_tick(sort_map, resource, slot)
    check("exit timer does NOT arm (card treated as in-lane)",
          state["slot"]["exit_timer_armed_at"] is None,
          f"armed_at={state['slot']['exit_timer_armed_at']!r}")
    check("anomaly logged for the restore",
          any("absent from sort" in l and "Active" in l for l in log_lines),
          f"log={log_lines!r}")


def test_active_stale_filter_still_works():
    print("Active lane — stale-from-disk card filtered (existing behavior preserved)")
    slot = _mk_slot("real-card", mode="implement", seen=True)
    # sort lists a card that is NOT on disk (stale) + the real card.
    sort_map = {"Active": ["ghost-card", "real-card"], "OnHold": [], "Ready": [], "Review": []}
    resource = _mk_resource(active_files=("real-card",))
    state, log_lines = _run_tick(sort_map, resource, slot)
    check("exit timer does NOT arm (real-card in-lane)",
          state["slot"]["exit_timer_armed_at"] is None,
          f"armed_at={state['slot']['exit_timer_armed_at']!r}")
    check("stale anomaly logged",
          any("absent on disk" in l and "Active" in l for l in log_lines),
          f"log={log_lines!r}")


def test_active_normal_no_anomaly():
    print("Active lane — card in both sort and disk (no anomaly, no arm)")
    slot = _mk_slot("impl-card", mode="implement", seen=True)
    sort_map = {"Active": ["impl-card"], "OnHold": [], "Ready": [], "Review": []}
    resource = _mk_resource(active_files=("impl-card",))
    state, log_lines = _run_tick(sort_map, resource, slot)
    check("no arm", state["slot"]["exit_timer_armed_at"] is None)
    check("no anomaly logged",
          not any("anomaly" in l for l in log_lines), f"log={log_lines!r}")


def test_active_genuinely_left_still_arms():
    print("Active lane — card truly left Active (timer still arms — backstop intact)")
    slot = _mk_slot("impl-card", mode="implement", seen=True)
    # Card is in NEITHER sort NOR Active on disk (the worker moved it to Ready).
    sort_map = {"Active": [], "OnHold": [], "Ready": ["impl-card"], "Review": []}
    resource = _mk_resource(active_files=(), review_files=())
    state, log_lines = _run_tick(sort_map, resource, slot)
    check("exit timer ARMS (card genuinely left Active)",
          state["slot"]["exit_timer_armed_at"] is not None,
          f"armed_at={state['slot']['exit_timer_armed_at']!r}")


def test_review_missing_restore():
    print("Review lane — missing-from-sort card restored (new cross-check)")
    slot = _mk_slot("rev-card", mode="review", seen=True)
    # sort says Review is empty, but the card is physically in Review on disk
    # and still tagged review-by-ai.
    sort_map = {"Active": [], "OnHold": [], "Ready": [], "Review": []}
    resource = _mk_resource(active_files=(), review_files=("rev-card",))
    state, log_lines = _run_tick(sort_map, resource, slot)
    check("exit timer does NOT arm (card in-lane + still tagged)",
          state["slot"]["exit_timer_armed_at"] is None,
          f"armed_at={state['slot']['exit_timer_armed_at']!r}")
    check("anomaly logged for the restore",
          any("absent from sort" in l and "Review" in l for l in log_lines),
          f"log={log_lines!r}")


def test_review_stale_filter():
    print("Review lane — stale-from-disk card filtered (new cross-check)")
    slot = _mk_slot("real-rev", mode="review", seen=True)
    sort_map = {"Active": [], "OnHold": [], "Ready": [], "Review": ["ghost-rev", "real-rev"]}
    resource = _mk_resource(active_files=(), review_files=("real-rev",))
    state, log_lines = _run_tick(sort_map, resource, slot)
    check("no arm (real-rev in-lane)", state["slot"]["exit_timer_armed_at"] is None)
    check("stale anomaly logged",
          any("absent on disk" in l and "Review" in l for l in log_lines),
          f"log={log_lines!r}")


def test_reviewer_lost_tag_still_arms():
    print("Review lane — card lost review-by-ai (timer still arms — clean-pass intact)")
    slot = _mk_slot("rev-card", mode="review", seen=True)
    # Card is in Review on disk + in sort, but the tag is gone (clean pass).
    sort_map = {"Active": [], "OnHold": [], "Ready": [], "Review": ["rev-card"]}
    resource = _mk_resource(active_files=(), review_files=("rev-card",), review_tag="ai-reviewed")
    state, log_lines = _run_tick(sort_map, resource, slot)
    check("exit timer ARMS (lost review-by-ai = clean pass)",
          state["slot"]["exit_timer_armed_at"] is not None,
          f"armed_at={state['slot']['exit_timer_armed_at']!r}")


def test_review_helper():
    print("review_on_disk() helper")
    resource = _mk_resource(active_files=("a",), review_files=("r1", "r2"))
    check("review_on_disk returns Review card names",
          o.review_on_disk(resource) == {"r1", "r2"},
          f"got {o.review_on_disk(resource)!r}")
    check("active_on_disk still returns Active card names",
          o.active_on_disk(resource) == {"a"}, f"got {o.active_on_disk(resource)!r}")


def main():
    test_review_helper()
    test_active_missing_restore()
    test_active_stale_filter_still_works()
    test_active_normal_no_anomaly()
    test_active_genuinely_left_still_arms()
    test_review_missing_restore()
    test_review_stale_filter()
    test_reviewer_lost_tag_still_arms()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED:", FAIL)
        sys.exit(1)
    print("ALL PASS")


if __name__ == "__main__":
    main()
