#!/usr/bin/env python3
"""Dry-run validation for the pre-launch pull (fix A) + card-specific prompts.

Imports orchestrator.py and exercises evaluate_launch() in isolation — no
worker is launched, no eGPU is probed, no real board is mutated.
board_move_card / launch_worker / egpu_up / save_state / log are
monkeypatched.

Covers:
  1. Ready trigger  -> board_move_card(card, Ready, Active) + launch with
     ("Active", card) — the card is in Active before the worker boots.
  2. Pull failure   -> anomaly logged, NO launch (retried next tick).
  3. Active trigger -> no pull (card already in Active), card-specific prompt.
  4. OnHold trigger -> no pull (condition check is worker-side judgment),
     OnHold prompt instructs `tmd claim`.
  5. Review trigger -> reviewer prompt names the card.
  6. Cooldown       -> no pull, no launch (cooldown gate intact).
  7. eGPU down      -> no pull, no launch.
  8. Prompt builders (pure functions): implementer Active/OnHold, reviewer.

Run:  python3 orchestrator/test_prelaunch_pull_dryrun.py
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
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}"
          + (f" — {detail}" if detail and not cond else ""))


def _run_evaluate(active=(), onhold=(), ready=(), review_trigger=None,
                  pull_raises=False, egpu=True, last_exit_at=None):
    """Run one evaluate_launch() with everything monkeypatched.

    Returns (state, log_lines, pull_attempts, pulls, launches) where pulls is
    a list of (card, src, dst) and launches a list of (lane, card) triggers.
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
    o.launch_worker = lambda state, now, trigger: launches.append(trigger)
    o.save_state = lambda state: None
    orig_log = o.log
    o.log = lambda msg, *args: log_lines.append(msg % args if args else msg)

    state = o.empty_state()
    state["last_exit_at"] = last_exit_at
    now = 2_000_000.0
    try:
        o.evaluate_launch(state, now, list(active), list(onhold),
                          list(ready), review_trigger)
    finally:
        o.log = orig_log
    return state, log_lines, attempts[0], pulls, launches


def test_ready_trigger_pulls():
    print("1. Ready trigger — pulled into Active before launch")
    _, log_lines, attempts, pulls, launches = _run_evaluate(ready=["ready-card"])
    check("pull performed (Ready -> Active)",
          pulls == [("ready-card", "Ready", "Active")], f"pulls={pulls}")
    check("launch trigger re-assigned to Active",
          launches == [("Active", "ready-card")], f"launches={launches}")
    check("pull logged",
          any("pull:" in l and "ready-card" in l for l in log_lines),
          f"log={log_lines!r}")


def test_pull_failure_skips_launch():
    print("2. Pull failure — anomaly logged, no launch (retry next tick)")
    _, log_lines, attempts, pulls, launches = _run_evaluate(
        ready=["ready-card"], pull_raises=True)
    check("pull attempted (then raised)", attempts == 1 and pulls == [],
          f"attempts={attempts} pulls={pulls}")
    check("NO launch", launches == [], f"launches={launches}")
    check("anomaly logged",
          any("anomaly" in l and "pre-launch pull" in l for l in log_lines),
          f"log={log_lines!r}")


def test_active_trigger_no_pull():
    print("3. Active trigger — no pull (card already in Active)")
    _, log_lines, attempts, pulls, launches = _run_evaluate(active=["active-card"])
    check("no pull", attempts == 0 and pulls == [],
          f"attempts={attempts} pulls={pulls}")
    check("launch with Active trigger",
          launches == [("Active", "active-card")], f"launches={launches}")
    check("no pull log line",
          not any("pull:" in l for l in log_lines), f"log={log_lines!r}")


def test_onhold_trigger_no_pull():
    print("4. OnHold trigger — no pull (condition check is worker-side)")
    _, log_lines, attempts, pulls, launches = _run_evaluate(onhold=["onhold-card"])
    check("no pull", attempts == 0 and pulls == [],
          f"attempts={attempts} pulls={pulls}")
    check("launch with OnHold trigger",
          launches == [("OnHold", "onhold-card")], f"launches={launches}")


def test_review_trigger():
    print("5. Review trigger — reviewer launch, no pull")
    _, log_lines, attempts, pulls, launches = _run_evaluate(
        review_trigger="rev-card")
    check("no pull", attempts == 0 and pulls == [],
          f"attempts={attempts} pulls={pulls}")
    check("launch with Review trigger",
          launches == [("Review", "rev-card")], f"launches={launches}")


def test_cooldown_still_gates():
    print("6. Cooldown — no pull, no launch while in cooldown")
    _, log_lines, attempts, pulls, launches = _run_evaluate(
        ready=["ready-card"], last_exit_at=2_000_000.0 - 10)  # 10 s ago < 60 s
    check("no pull (cooldown before pull)", attempts == 0 and pulls == [],
          f"attempts={attempts} pulls={pulls}")
    check("no launch", launches == [], f"launches={launches}")
    check("cooldown logged",
          any("cooldown" in l for l in log_lines), f"log={log_lines!r}")


def test_egpu_down_no_pull():
    print("7. eGPU down — no pull, no launch")
    _, log_lines, attempts, pulls, launches = _run_evaluate(
        ready=["ready-card"], egpu=False)
    check("no pull", attempts == 0 and pulls == [],
          f"attempts={attempts} pulls={pulls}")
    check("no launch", launches == [], f"launches={launches}")


def test_prompts():
    print("8. Prompt builders — card-specific entry prompts")
    p = o.implementer_entry_prompt("Active", "my card")
    check("implementer/Active names the card in Active",
          "work card `Active/my card`" in p and "board-worker-v1" in p, p)
    p = o.implementer_entry_prompt("Ready", "my card")
    check("implementer/Ready (post-pull) treated as Active",
          "work card `Active/my card`" in p, p)
    p = o.implementer_entry_prompt("OnHold", None)
    check("implementer/OnHold instructs scan + tmd claim",
          "OnHold" in p and "tmd claim" in p and "board-worker-v1" in p, p)
    p = o.reviewer_entry_prompt("rev card")
    check("reviewer names the card in Review",
          "review card `Review/rev card`" in p and "board-reviewer-v1" in p, p)


def main():
    tests = [
        test_ready_trigger_pulls,
        test_pull_failure_skips_launch,
        test_active_trigger_no_pull,
        test_onhold_trigger_no_pull,
        test_review_trigger,
        test_cooldown_still_gates,
        test_egpu_down_no_pull,
        test_prompts,
    ]
    for t in tests:
        t()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED:", *FAIL, sep="\n  - ")
        sys.exit(1)


if __name__ == "__main__":
    main()
