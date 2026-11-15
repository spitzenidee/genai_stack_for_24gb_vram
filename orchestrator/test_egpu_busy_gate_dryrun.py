#!/usr/bin/env python3
"""Dry-run validation for the eGPU busy gate in evaluate_launch().

Imports orchestrator.py and exercises evaluate_launch() in isolation — no
worker is launched, no eGPU is probed, no real sysfs is read, no board is
mutated. egpu_busy_avg / board_move_card / launch_worker / egpu_up /
save_state / log are monkeypatched (the sampling function is faked, so there
are no real sysfs reads and no 10 s sleeps in tests).

Covers:
  1. Idle (avg < 5)      -> launch proceeds, state["egpu_busy"] stays False.
  2. Busy (avg >= 10)    -> NO launch, state["egpu_busy"] set, "eGPU busy"
     logged once on transition; last_exit_at / cooldown_announced untouched
     (no cooldown reset).
  3. Hysteresis          -> state busy + avg in the 5-10 band -> stays
     blocked (no recovery log, no launch).
  4. Recovery            -> state busy + avg < 5 -> state cleared, "back to
     idle" logged, launch proceeds.
  5. Read failure (None) -> fail closed: busy, anomaly logged, no launch.
  6. No trigger          -> sampling function NOT called (no overhead on
     idle ticks).
  7. Env-var overrides   -> EGPU_BUSY_BLOCK_PCT / RESUME_PCT /
     WINDOW_SAMPLES / SAMPLE_INTERVAL_S are read per call (no orchestrator
     restart needed).

Run:  python3 orchestrator/test_egpu_busy_gate_dryrun.py
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


def _run_evaluate(busy_avg, active=(), onhold=(), ready=(),
                  review_trigger=None, state_busy=False, last_exit_at=None):
    """Run one evaluate_launch() with everything monkeypatched.

    busy_avg: value returned by the faked egpu_busy_avg() (None = read
    failure). Returns (state, log_lines, samples_taken, launches).
    """
    log_lines = []
    launches = []
    samples = [0]

    o.board_move_card = lambda card, src, dst: None
    o.egpu_up = lambda: True
    o.launch_worker = (lambda state, now, trigger, card_model=None, worker_cwd=None:
                       launches.append(trigger))
    o.save_state = lambda state: None
    orig_busy_avg = o.egpu_busy_avg
    o.egpu_busy_avg = lambda: (samples.__setitem__(0, samples[0] + 1),
                               busy_avg)[1]
    orig_log = o.log
    o.log = lambda msg, *args: log_lines.append(msg % args if args else msg)

    state = o.empty_state()
    state["egpu_busy"] = state_busy
    state["last_exit_at"] = last_exit_at
    now = 2_000_000.0
    try:
        o.evaluate_launch(state, now, list(active), list(onhold),
                          list(ready), review_trigger)
    finally:
        o.log = orig_log
        o.egpu_busy_avg = orig_busy_avg
    return state, log_lines, samples[0], launches


def test_idle_launch_proceeds():
    print("1. Idle (avg < 5) — launch proceeds")
    state, log_lines, samples, launches = _run_evaluate(
        0, ready=["ready-card"])
    check("launch proceeds", launches == [("Active", "ready-card")],
          f"launches={launches}")
    check("state['egpu_busy'] stays False", state.get("egpu_busy") is False,
          f"egpu_busy={state.get('egpu_busy')!r}")
    check("no busy log line",
          not any("eGPU busy" in l for l in log_lines), f"log={log_lines!r}")
    check("sampling taken exactly once (only when a trigger was selected)",
          samples == 1, f"samples={samples}")


def test_busy_blocks_launch():
    print("2. Busy (avg >= 10) — no launch, state set, logged once")
    state, log_lines, samples, launches = _run_evaluate(
        87, ready=["ready-card"])
    check("NO launch", launches == [], f"launches={launches}")
    check("state['egpu_busy'] set", state.get("egpu_busy") is True,
          f"egpu_busy={state.get('egpu_busy')!r}")
    check("'eGPU busy' logged with measured %",
          any("eGPU busy (87%)" in l for l in log_lines), f"log={log_lines!r}")
    check("last_exit_at untouched (no cooldown reset)",
          state.get("last_exit_at") is None,
          f"last_exit_at={state.get('last_exit_at')!r}")
    check("cooldown_announced untouched (no cooldown reset)",
          state.get("cooldown_announced") is False,
          f"cooldown_announced={state.get('cooldown_announced')!r}")

    # Second tick while still busy: no duplicate transition log.
    state2, log_lines2, _, launches2 = _run_evaluate(
        90, ready=["ready-card"], state_busy=True)
    check("still blocked on next tick", launches2 == [], f"launches={launches2}")
    check("no duplicate 'eGPU busy' transition log",
          not any("eGPU busy" in l for l in log_lines2), f"log={log_lines2!r}")


def test_hysteresis_band_stays_blocked():
    print("3. Hysteresis — state busy + avg in the 5-10 band -> stays blocked")
    state, log_lines, samples, launches = _run_evaluate(
        7, ready=["ready-card"], state_busy=True)
    check("NO launch (band does not clear the state)", launches == [],
          f"launches={launches}")
    check("state['egpu_busy'] stays True", state.get("egpu_busy") is True,
          f"egpu_busy={state.get('egpu_busy')!r}")
    check("no recovery log",
          not any("back to idle" in l for l in log_lines), f"log={log_lines!r}")

    # Symmetric: state idle + avg in the band -> stays idle (launch proceeds).
    state2, log_lines2, _, launches2 = _run_evaluate(
        7, ready=["ready-card"])
    check("state idle + band -> launch proceeds (band does not block)",
          launches2 == [("Active", "ready-card")], f"launches={launches2}")
    check("state['egpu_busy'] stays False",
          state2.get("egpu_busy") is False,
          f"egpu_busy={state2.get('egpu_busy')!r}")
    check("no busy log",
          not any("eGPU busy" in l for l in log_lines2), f"log={log_lines2!r}")


def test_recovery_clears_state():
    print("4. Recovery — state busy + avg < 5 -> cleared, launch proceeds")
    state, log_lines, samples, launches = _run_evaluate(
        0, ready=["ready-card"], state_busy=True)
    check("launch proceeds after recovery",
          launches == [("Active", "ready-card")], f"launches={launches}")
    check("state['egpu_busy'] cleared", state.get("egpu_busy") is False,
          f"egpu_busy={state.get('egpu_busy')!r}")
    check("'back to idle' logged with measured %",
          any("eGPU back to idle (0%)" in l for l in log_lines),
          f"log={log_lines!r}")


def test_read_failure_fails_closed():
    print("5. Read failure (None) — fail closed: busy, anomaly, no launch")
    state, log_lines, samples, launches = _run_evaluate(
        None, ready=["ready-card"])
    check("NO launch", launches == [], f"launches={launches}")
    check("state['egpu_busy'] set (fail closed)",
          state.get("egpu_busy") is True,
          f"egpu_busy={state.get('egpu_busy')!r}")
    check("anomaly logged",
          any("anomaly" in l and "eGPU busy read failed" in l
              for l in log_lines), f"log={log_lines!r}")

    # Already busy + read failure again: no duplicate anomaly log.
    state2, log_lines2, _, launches2 = _run_evaluate(
        None, ready=["ready-card"], state_busy=True)
    check("still blocked", launches2 == [], f"launches={launches2}")
    check("no duplicate anomaly",
          not any("anomaly" in l for l in log_lines2), f"log={log_lines2!r}")


def test_no_trigger_no_sampling():
    print("6. No trigger (idle_no_work) — sampling function NOT called")
    state, log_lines, samples, launches = _run_evaluate(0)
    check("no launch", launches == [], f"launches={launches}")
    check("sampling function NOT called (no overhead on idle ticks)",
          samples == 0, f"samples={samples}")
    check("idle_no_work set", state.get("idle_no_work") is True,
          f"idle_no_work={state.get('idle_no_work')!r}")


def _env_overrides():
    print("7. Env-var overrides — read per call (no restart needed)")
    reads = []
    orig_read = o._read_gpu_busy
    o._read_gpu_busy = lambda: (reads.append(1), 50)[1]
    orig_sleep = o.time.sleep  # no real sleeps in tests
    o.time.sleep = lambda s: None
    saved_env = {k: os.environ.get(k) for k in
                 ("EGPU_BUSY_BLOCK_PCT", "EGPU_BUSY_RESUME_PCT",
                  "EGPU_BUSY_WINDOW_SAMPLES", "EGPU_BUSY_SAMPLE_INTERVAL_S")}
    try:
        # Window params: EGPU_BUSY_WINDOW_SAMPLES=2, interval 0 -> exactly
        # 2 reads, avg 50.
        os.environ["EGPU_BUSY_WINDOW_SAMPLES"] = "2"
        os.environ["EGPU_BUSY_SAMPLE_INTERVAL_S"] = "0"
        avg = o.egpu_busy_avg()
        check("EGPU_BUSY_WINDOW_SAMPLES=2 -> exactly 2 reads",
              len(reads) == 2 and avg == 50, f"reads={len(reads)} avg={avg}")

        # Invalid env values fall back to the measured defaults.
        os.environ["EGPU_BUSY_WINDOW_SAMPLES"] = "not-a-number"
        os.environ["EGPU_BUSY_SAMPLE_INTERVAL_S"] = ""
        reads.clear()
        avg = o.egpu_busy_avg()
        check("invalid env values -> measured defaults (5 reads)",
              len(reads) == 5 and avg == 50, f"reads={len(reads)} avg={avg}")

        # Thresholds: default BLOCK=10 -> avg 7 does not block;
        # EGPU_BUSY_BLOCK_PCT=5 -> avg 7 blocks.
        _, log_lines, _, launches = _run_evaluate(7, ready=["ready-card"])
        check("default BLOCK_PCT=10: avg 7 (band) -> no block",
              launches == [("Active", "ready-card")], f"launches={launches}")
        os.environ["EGPU_BUSY_BLOCK_PCT"] = "5"
        state, log_lines, _, launches = _run_evaluate(7, ready=["ready-card"])
        check("EGPU_BUSY_BLOCK_PCT=5: avg 7 -> blocks",
              launches == [] and state.get("egpu_busy") is True,
              f"launches={launches} egpu_busy={state.get('egpu_busy')!r}")
        os.environ.pop("EGPU_BUSY_BLOCK_PCT")

        # Resume threshold: state busy + avg 7; default RESUME=5 -> stays
        # blocked; EGPU_BUSY_RESUME_PCT=8 -> recovers.
        state, log_lines, _, launches = _run_evaluate(
            7, ready=["ready-card"], state_busy=True)
        check("default RESUME_PCT=5: avg 7 -> stays blocked",
              launches == [] and state.get("egpu_busy") is True,
              f"launches={launches}")
        os.environ["EGPU_BUSY_RESUME_PCT"] = "8"
        state, log_lines, _, launches = _run_evaluate(
            7, ready=["ready-card"], state_busy=True)
        check("EGPU_BUSY_RESUME_PCT=8: avg 7 -> recovers, launch proceeds",
              launches == [("Active", "ready-card")]
              and state.get("egpu_busy") is False,
              f"launches={launches} egpu_busy={state.get('egpu_busy')!r}")
    finally:
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        o._read_gpu_busy = orig_read
        o.time.sleep = orig_sleep


def main():
    tests = [
        test_idle_launch_proceeds,
        test_busy_blocks_launch,
        test_hysteresis_band_stays_blocked,
        test_recovery_clears_state,
        test_read_failure_fails_closed,
        test_no_trigger_no_sampling,
        _env_overrides,
    ]
    for t in tests:
        t()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED:", *FAIL, sep="\n  - ")
        sys.exit(1)


if __name__ == "__main__":
    main()
