#!/usr/bin/env python3
"""Dry-run validation for the OnHold pre-check (scan hot-loop guard).

Imports orchestrator.py and exercises onhold_precheck() (pure) and
evaluate_launch() in isolation — no worker is launched, no eGPU is probed,
no real board is mutated. board_move_card / launch_worker / egpu_up /
save_state / log are monkeypatched.

Covers:
  Pure onhold_precheck():
  1.  Canonical condition satisfied (predecessor Review + ai-reviewed) ->
      ("Active", card) — orchestrator pulls, no scan worker.
  2.  Canonical condition satisfied (predecessor Done + ai-reviewed) ->
      ("Active", card).
  3.  Canonical condition unsatisfied (predecessor in Ready) -> None.
  4.  Canonical condition unsatisfied (predecessor Review, no ai-reviewed)
      -> None.
  5.  Canonical condition, predecessor missing from the board -> None.
  6.  Legacy prose/external condition (suffixed heading, numbered list) ->
      ("OnHold", card) — scan worker.
  7.  No condition section at all -> scan worker.
  8.  Mixed: canonical unsatisfied + legacy -> scan worker.
  9.  Two canonical cards, first unsatisfied, second satisfied -> pull the
      second (top→bottom, first satisfied wins).
  10. Empty OnHold -> None.
  11. Skill-template condition format (bold + backticked literals) is
      recognized as canonical.
  evaluate_launch() integration:
  12. Satisfied canonical -> pull OnHold -> Active + launch ("Active", card),
      no scan worker.
  13. All canonical unsatisfied -> NO launch, pre-check log once (2nd tick:
      no repeat).
  14. Non-canonical -> scan worker launch ("OnHold", card), no pull.
  15. Pull failure -> anomaly logged, NO launch (retry next tick).
  16. Cooldown -> no pull, no launch.
  17. eGPU down -> no pull, no launch.
  18. Review trigger preempts the OnHold trigger.

Run:  python3 orchestrator/test_onhold_precheck_dryrun.py
"""
import os
import sys

ORCH_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ORCH_DIR)
import orchestrator as o  # noqa: E402

PASS = []
FAIL = []

PRED = "predecessor card"


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}"
          + (f" — {detail}" if detail and not cond else ""))


def _card(tags=()):
    """Card content with a canonical tag line 1 (empty line 1 = no tags)."""
    line1 = "".join(f"[tag:{t}]" for t in tags)
    return line1 + "\n\n# Card\n\nbody\n"


def _canonical(pred):
    """A card's `## OnHold condition` section in the canonical form."""
    return ("## OnHold condition\n\n"
            f'Condition: the "{pred}" card has the `ai-reviewed` tag AND is '
            "in the Review or Done lane.\n"
            "Verify: `tmd list` shows the predecessor in the Review or Done "
            "lane, AND `tmd get <Lane/card>` line 1 contains "
            "`[tag:ai-reviewed]`.\n")


def _canonical_template_style(pred):
    """The tasks-board skill's template form (bold + backticked literals)."""
    return ("## OnHold condition\n\n"
            f"**Condition:** the {pred} card has the `ai-reviewed` tag AND "
            "is in the `Review` or `Done` lane.\n")


def _legacy_condition():
    """A legacy OnHold condition section (suffixed heading, numbered
    external conditions)."""
    return ("## OnHold condition (mechanically checkable — ALL must be "
            "true)\n\n"
            "1. eGPU llama-server healthy: `curl -sf http://localhost:8092/"
            "health`.\n"
            "2. Benchmark completed: `scripts/bench-results/x/summary.md` "
            "exists.\n")


def _resource(lanes):
    """Build a board resource tree from {lane: {card: content}}."""
    return [{"name": lane,
             "files": [{"name": c, "content": content}
                       for c, content in cards.items()]}
            for lane, cards in lanes.items()]


# --------------------------------------------------------------------------
# Pure onhold_precheck()
# --------------------------------------------------------------------------
def test_satisfied_review():
    print("1. Canonical satisfied (predecessor Review + ai-reviewed) -> pull")
    res = _resource({"OnHold": {"s1": _canonical(PRED)},
                     "Review": {PRED: _card(["ai-reviewed"])}})
    check("satisfied -> (\"Active\", card)",
          o.onhold_precheck(["s1"], res) == ("Active", "s1"),
          f"got {o.onhold_precheck(['s1'], res)!r}")


def test_satisfied_done():
    print("2. Canonical satisfied (predecessor Done + ai-reviewed) -> pull")
    res = _resource({"OnHold": {"s1": _canonical(PRED)},
                     "Done": {PRED: _card(["ai-reviewed"])}})
    check("satisfied (Done) -> (\"Active\", card)",
          o.onhold_precheck(["s1"], res) == ("Active", "s1"),
          f"got {o.onhold_precheck(['s1'], res)!r}")


def test_unsatisfied_ready_lane():
    print("3. Canonical unsatisfied (predecessor in Ready) -> None")
    res = _resource({"OnHold": {"s1": _canonical(PRED)},
                     "Ready": {PRED: _card(["ai-reviewed"])}})
    check("predecessor in Ready -> None (skip)",
          o.onhold_precheck(["s1"], res) is None,
          f"got {o.onhold_precheck(['s1'], res)!r}")


def test_unsatisfied_no_tag():
    print("4. Canonical unsatisfied (predecessor Review, no ai-reviewed) -> None")
    res = _resource({"OnHold": {"s1": _canonical(PRED)},
                     "Review": {PRED: _card()}})
    check("predecessor without ai-reviewed -> None (skip)",
          o.onhold_precheck(["s1"], res) is None,
          f"got {o.onhold_precheck(['s1'], res)!r}")


def test_unsatisfied_pred_missing():
    print("5. Canonical condition, predecessor missing from board -> None")
    res = _resource({"OnHold": {"s1": _canonical(PRED)}})
    check("missing predecessor -> None (canonical, unsatisfied)",
          o.onhold_precheck(["s1"], res) is None,
          f"got {o.onhold_precheck(['s1'], res)!r}")


def test_legacy_condition_scan_worker():
    print("6. Legacy prose/external condition -> scan worker")
    res = _resource({"OnHold": {"s1": "## Story\n\nbody\n\n" + _legacy_condition()}})
    check("legacy -> (\"OnHold\", card)",
          o.onhold_precheck(["s1"], res) == ("OnHold", "s1"),
          f"got {o.onhold_precheck(['s1'], res)!r}")


def test_no_condition_section_scan_worker():
    print("7. No condition section at all -> scan worker")
    res = _resource({"OnHold": {"s1": "## Story\n\nbody\n"}})
    check("no section -> (\"OnHold\", card)",
          o.onhold_precheck(["s1"], res) == ("OnHold", "s1"),
          f"got {o.onhold_precheck(['s1'], res)!r}")


def test_mixed_canonical_and_legacy():
    print("8. Mixed: canonical unsatisfied + legacy -> scan worker")
    res = _resource({"OnHold": {"s1": _canonical(PRED),
                                "s2": "## Story\n\nbody\n\n" + _legacy_condition()}})
    check("mixed -> (\"OnHold\", top card)",
          o.onhold_precheck(["s1", "s2"], res) == ("OnHold", "s1"),
          f"got {o.onhold_precheck(['s1', 's2'], res)!r}")


def test_first_satisfied_wins():
    print("9. Two canonical cards, first unsatisfied, second satisfied -> 2nd")
    res = _resource({"OnHold": {"s1": _canonical("absent pred"),
                                "s2": _canonical(PRED)},
                     "Done": {PRED: _card(["ai-reviewed"])}})
    check("first satisfied (top->bottom) -> (\"Active\", s2)",
          o.onhold_precheck(["s1", "s2"], res) == ("Active", "s2"),
          f"got {o.onhold_precheck(['s1', 's2'], res)!r}")


def test_empty_onhold():
    print("10. Empty OnHold -> None")
    res = _resource({})
    check("empty -> None", o.onhold_precheck([], res) is None)


def test_template_style_format():
    print("11. Skill-template format (bold + backticks) is canonical")
    res = _resource({"OnHold": {"s1": _canonical_template_style(f'"{PRED}"')},
                     "Review": {PRED: _card(["ai-reviewed"])}})
    check("template style recognized -> (\"Active\", card)",
          o.onhold_precheck(["s1"], res) == ("Active", "s1"),
          f"got {o.onhold_precheck(['s1'], res)!r}")


# --------------------------------------------------------------------------
# evaluate_launch() integration
# --------------------------------------------------------------------------
def _run_evaluate(active=(), onhold=(), ready=(), review_trigger=None,
                  onhold_trigger=None, pull_raises=False, egpu=True,
                  last_exit_at=None, state=None):
    """Run one evaluate_launch() with everything monkeypatched.

    Returns (state, log_lines, pull_attempts, pulls, launches) where pulls
    is a list of (card, src, dst) and launches a list of (lane, card)
    triggers.
    """
    log_lines = []
    pulls = []
    launches = []
    attempts = [0]

    def fake_pull(card, src_lane, dst_lane):
        attempts[0] += 1
        if pull_raises:
            raise RuntimeError("simulated HTTP failure (user moved card)")
        pulls.append((card, src_lane, dst_lane))

    o.board_move_card = fake_pull
    o.egpu_up = lambda: egpu
    orig_busy_avg = o.egpu_busy_avg
    o.egpu_busy_avg = lambda: 0  # idle eGPU — no real sysfs reads/sleeps
    o.launch_worker = (lambda state, now, trigger, card_model=None, worker_cwd=None:
                       launches.append(trigger))
    o.save_state = lambda state: None
    orig_log = o.log
    o.log = lambda msg, *args: log_lines.append(msg % args if args else msg)

    if state is None:
        state = o.empty_state()
    state["last_exit_at"] = last_exit_at
    now = 2_000_000.0
    try:
        o.evaluate_launch(state, now, list(active), list(onhold),
                          list(ready), review_trigger, None, onhold_trigger)
    finally:
        o.log = orig_log
        o.egpu_busy_avg = orig_busy_avg
    return state, log_lines, attempts[0], pulls, launches


def test_satisfied_pulls_and_launches_active():
    print("12. Satisfied canonical -> pull OnHold -> Active + Active launch")
    _, log_lines, attempts, pulls, launches = _run_evaluate(
        onhold=["s1"], onhold_trigger=("Active", "s1"))
    check("pull performed (OnHold -> Active)",
          pulls == [("s1", "OnHold", "Active")], f"pulls={pulls}")
    check("launch trigger is Active (no scan worker)",
          launches == [("Active", "s1")], f"launches={launches}")
    check("pull logged",
          any("pull:" in l and "s1" in l for l in log_lines),
          f"log={log_lines!r}")


def test_all_blocked_skips_and_logs_once():
    print("13. All canonical unsatisfied -> no launch, log once")
    state, log_lines, attempts, pulls, launches = _run_evaluate(
        onhold=["s1", "s2"], onhold_trigger=None)
    check("NO launch", launches == [], f"launches={launches}")
    check("no pull", attempts == 0 and pulls == [], f"pulls={pulls}")
    check("pre-check logged",
          any("pre-check" in l for l in log_lines), f"log={log_lines!r}")
    # Second tick with the same state: no repeat announcement.
    _, log_lines2, attempts2, pulls2, launches2 = _run_evaluate(
        onhold=["s1", "s2"], onhold_trigger=None, state=state)
    check("2nd tick: no launch", launches2 == [], f"launches={launches2}")
    check("2nd tick: announcement not repeated",
          not any("pre-check" in l for l in log_lines2), f"log={log_lines2!r}")
    check("blocked flag set", state.get("onhold_blocked_announced") is True)


def test_non_canonical_scan_worker():
    print("14. Non-canonical -> scan worker launch, no pull")
    _, log_lines, attempts, pulls, launches = _run_evaluate(
        onhold=["s1"], onhold_trigger=("OnHold", "s1"))
    check("no pull", attempts == 0 and pulls == [], f"pulls={pulls}")
    check("launch with OnHold trigger (scan worker)",
          launches == [("OnHold", "s1")], f"launches={launches}")


def test_pull_failure_skips_launch():
    print("15. Pull failure — anomaly logged, no launch (retry next tick)")
    _, log_lines, attempts, pulls, launches = _run_evaluate(
        onhold=["s1"], onhold_trigger=("Active", "s1"), pull_raises=True)
    check("pull attempted (then raised)", attempts == 1 and pulls == [],
          f"attempts={attempts} pulls={pulls}")
    check("NO launch", launches == [], f"launches={launches}")
    check("anomaly logged",
          any("anomaly" in l and "OnHold pre-launch pull" in l for l in log_lines),
          f"log={log_lines!r}")


def test_cooldown_still_gates():
    print("16. Cooldown — no pull, no launch while in cooldown")
    _, log_lines, attempts, pulls, launches = _run_evaluate(
        onhold=["s1"], onhold_trigger=("Active", "s1"),
        last_exit_at=2_000_000.0 - 10)  # 10 s ago < 300 s OnHold cooldown
    check("no pull (cooldown before pull)", attempts == 0 and pulls == [],
          f"attempts={attempts} pulls={pulls}")
    check("no launch", launches == [], f"launches={launches}")
    check("cooldown logged",
          any("cooldown" in l for l in log_lines), f"log={log_lines!r}")


def test_egpu_down_no_pull():
    print("17. eGPU down — no pull, no launch")
    _, log_lines, attempts, pulls, launches = _run_evaluate(
        onhold=["s1"], onhold_trigger=("Active", "s1"), egpu=False)
    check("no pull", attempts == 0 and pulls == [], f"pulls={pulls}")
    check("no launch", launches == [], f"launches={launches}")


def test_review_preempts_onhold():
    print("18. Review trigger preempts the OnHold trigger")
    _, log_lines, attempts, pulls, launches = _run_evaluate(
        onhold=["s1"], onhold_trigger=("Active", "s1"),
        review_trigger="rev-card")
    check("Review preempts OnHold",
          launches == [("Review", "rev-card")], f"launches={launches}")
    check("no OnHold pull for a Review trigger",
          attempts == 0 and pulls == [], f"attempts={attempts} pulls={pulls}")


def main():
    tests = [
        test_satisfied_review,
        test_satisfied_done,
        test_unsatisfied_ready_lane,
        test_unsatisfied_no_tag,
        test_unsatisfied_pred_missing,
        test_legacy_condition_scan_worker,
        test_no_condition_section_scan_worker,
        test_mixed_canonical_and_legacy,
        test_first_satisfied_wins,
        test_empty_onhold,
        test_template_style_format,
        test_satisfied_pulls_and_launches_active,
        test_all_blocked_skips_and_logs_once,
        test_non_canonical_scan_worker,
        test_pull_failure_skips_launch,
        test_cooldown_still_gates,
        test_egpu_down_no_pull,
        test_review_preempts_onhold,
    ]
    for t in tests:
        t()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED:", *FAIL, sep="\n  - ")
        sys.exit(1)


if __name__ == "__main__":
    main()
