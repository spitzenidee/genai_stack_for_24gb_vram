#!/usr/bin/env python3
"""Dry-run validation for the Spec-lane refiner scan (G4/G5/G8).

Imports orchestrator.py and exercises evaluate_launch() + the Spec-scan
helpers in isolation — no worker is launched, no eGPU is probed, no real
board is mutated. board_move_card / launch_worker / egpu_up / save_state /
log are monkeypatched.

Covers:
  1. first_spec_unrefined -> topmost Spec card WITHOUT the refined tag;
     refined cards are skipped (hot-loop guard, G5); None when none/absent.
  2. Spec trigger   -> "refine" mode + refiner prompt, NO pre-launch pull
     (the refiner works in place in Spec — the card never moves).
  3. Queue order    -> Active > Spec > Review > Ready > OnHold.
  4. Cooldown       -> no launch while in cooldown.
  5. eGPU down      -> no launch.
  6. Prompt builder (pure function): refiner names the card in Spec.

Run:  python3 orchestrator/test_spec_scan_dryrun.py
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


# A fake board resource tree (lanes -> files with content), mirroring the
# live /_api/resource shape. Spec order: refined card (top), unrefined card,
# unrefined card.
FAKE_RESOURCE = [
    {"name": "Active", "files": []},
    {"name": "Spec", "files": [
        {"name": "refined-top", "content": "[tag:refined]\n\n# refined\n"},
        {"name": "unrefined-first", "content": "\n# first\n"},
        {"name": "unrefined-second", "content": "[tag:spec]\n\n# second\n"},
    ]},
    {"name": "Review", "files": []},
    {"name": "Ready", "files": []},
    {"name": "OnHold", "files": []},
]


def test_first_spec_unrefined():
    print("1. first_spec_unrefined — topmost unrefined, refined skipped")
    check("returns topmost UNrefined (skips refined-top)",
          o.first_spec_unrefined(FAKE_RESOURCE) == "unrefined-first",
          f"got {o.first_spec_unrefined(FAKE_RESOURCE)!r}")
    # All refined -> None.
    all_refined = [dict(l, files=[dict(f, content="[tag:refined]\nx")
                                  for f in l["files"]])
                   if l["name"] == "Spec" else l for l in FAKE_RESOURCE]
    check("None when all Spec cards are refined",
          o.first_spec_unrefined(all_refined) is None)
    # Empty Spec -> None.
    no_spec = [l for l in FAKE_RESOURCE if l["name"] != "Spec"]
    check("None when Spec lane absent",
          o.first_spec_unrefined(no_spec) is None)
    # spec_on_disk reflects the file tree.
    check("spec_on_disk lists all three Spec cards",
          o.spec_on_disk(FAKE_RESOURCE)
          == {"refined-top", "unrefined-first", "unrefined-second"},
          f"got {o.spec_on_disk(FAKE_RESOURCE)!r}")


def _run_evaluate(active=(), onhold=(), ready=(), review_trigger=None,
                  spec_trigger=None, onhold_trigger=None, pull_raises=False,
                  egpu=True, last_exit_at=None):
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
    orig_busy_avg = o.egpu_busy_avg
    o.egpu_busy_avg = lambda: 0  # idle eGPU — no real sysfs reads/sleeps
    o.launch_worker = (lambda state, now, trigger, card_model=None, worker_cwd=None:
                       launches.append(trigger))
    o.save_state = lambda state: None
    orig_log = o.log
    o.log = lambda msg, *args: log_lines.append(msg % args if args else msg)

    state = o.empty_state()
    state["last_exit_at"] = last_exit_at
    now = 2_000_000.0
    try:
        o.evaluate_launch(state, now, list(active), list(onhold),
                          list(ready), review_trigger, spec_trigger,
                          onhold_trigger)
    finally:
        o.log = orig_log
        o.egpu_busy_avg = orig_busy_avg
    return state, log_lines, attempts[0], pulls, launches


def test_spec_trigger_refine_mode_no_pull():
    print("2. Spec trigger — refine mode, NO pre-launch pull")
    _, log_lines, attempts, pulls, launches = _run_evaluate(
        spec_trigger="unrefined-first")
    check("launch with Spec trigger",
          launches == [("Spec", "unrefined-first")], f"launches={launches}")
    check("NO pre-launch pull (refiner works in place)",
          attempts == 0 and pulls == [], f"attempts={attempts} pulls={pulls}")
    check("no pull log line",
          not any("pull:" in l for l in log_lines), f"log={log_lines!r}")


def test_queue_order():
    print("3. Queue order — Active > Spec > Review > Ready > OnHold")
    _, _, _, _, launches = _run_evaluate(active=["a"], spec_trigger="s")
    check("Active preempts Spec", launches == [("Active", "a")],
          f"launches={launches}")
    _, _, _, _, launches = _run_evaluate(spec_trigger="s", review_trigger="r")
    check("Spec preempts Review", launches == [("Spec", "s")],
          f"launches={launches}")
    _, _, _, _, launches = _run_evaluate(spec_trigger="s", ready=["y"])
    check("Spec preempts Ready", launches == [("Spec", "s")],
          f"launches={launches}")
    _, _, _, _, launches = _run_evaluate(spec_trigger="s", onhold=["h"],
                                         onhold_trigger=("OnHold", "h"))
    check("Spec preempts OnHold", launches == [("Spec", "s")],
          f"launches={launches}")
    # Unchanged relative order below Spec.
    _, _, _, _, launches = _run_evaluate(review_trigger="r", ready=["y"])
    check("Review preempts Ready", launches == [("Review", "r")],
          f"launches={launches}")
    _, _, _, _, launches = _run_evaluate(ready=["y"], onhold=["h"],
                                         onhold_trigger=("OnHold", "h"))
    check("Ready preempts OnHold (pulled to Active)",
          launches == [("Active", "y")], f"launches={launches}")


def test_cooldown():
    print("4. Cooldown — no launch while in cooldown")
    _, log_lines, attempts, pulls, launches = _run_evaluate(
        spec_trigger="s", last_exit_at=2_000_000.0 - 10)  # 10 s ago < 60 s
    check("no launch (cooldown)", launches == [], f"launches={launches}")
    check("no pull (cooldown before pull)", attempts == 0 and pulls == [])
    check("cooldown logged", any("cooldown" in l for l in log_lines),
          f"log={log_lines!r}")


def test_egpu_down():
    print("5. eGPU down — no launch")
    _, _, attempts, pulls, launches = _run_evaluate(spec_trigger="s",
                                                    egpu=False)
    check("no launch", launches == [], f"launches={launches}")
    check("no pull", attempts == 0 and pulls == [])


def test_refiner_prompt():
    print("6. Refiner prompt builder — names the card in Spec")
    p = o.refiner_entry_prompt("my card")
    check("refiner names the card in Spec",
          "Spec/my card" in p and "board-refiner-v1" in p, p)
    check("refiner prompt mentions AskUser + refined",
          "AskUser" in p and "refined" in p, p)


def main():
    tests = [
        test_first_spec_unrefined,
        test_spec_trigger_refine_mode_no_pull,
        test_queue_order,
        test_cooldown,
        test_egpu_down,
        test_refiner_prompt,
    ]
    for t in tests:
        t()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED:", *FAIL, sep="\n  - ")
        sys.exit(1)
    print("ALL PASS")


if __name__ == "__main__":
    main()
