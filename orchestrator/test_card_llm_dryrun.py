#!/usr/bin/env python3
"""Dry-run validation for the card `## LLM` model choice.

Imports orchestrator.py and exercises _card_llm_model() (pure),
_resolve_card_model() (pure + anomaly log), launch_worker() model
precedence (Popen monkeypatched — no real worker is launched), and
evaluate_launch() threading (launch_worker monkeypatched). No eGPU is
probed, no real board is mutated.

Covers:
  Pure _card_llm_model():
  1.  No `## LLM` section -> None (the common case).
  2.  `## LLM` with a `- Model:` line -> the model ID.
  3.  `## LLM` section without a `- Model:` line -> None.
  4.  Suffixed heading (`## LLM (note)`) is recognized.
  5.  Backticked model ID -> backticks stripped.
  6.  `- Model:` line in a LATER section is not picked up (section
      boundary honored).
  7.  Empty `## LLM` followed by a later section's `- Model:` line -> None.
  Pure _resolve_card_model():
  8.  resource is None -> None (no crash).
  9.  Card without a section -> None.
  10. Card with a valid ID -> the ID.
  11. Card with an invalid ID -> None + anomaly log.
  12. Card absent from the board -> None.
  launch_worker() precedence (Popen captured):
  13. card_model + WORKER_MODEL both set -> card_model wins.
  14. card_model None + WORKER_MODEL set -> WORKER_MODEL used.
  15. Both None -> no --model flag (pi default).
  evaluate_launch() threading:
  16. Ready trigger with a valid `## LLM` card -> launch_worker gets the ID.
  17. Ready trigger without a section -> launch_worker gets None.
  18. Ready trigger with an invalid ID -> launch_worker gets None + anomaly.
  19. resource is None -> launch_worker gets None (no crash).

Run:  python3 orchestrator/test_card_llm_dryrun.py
"""
import os
import sys

ORCH_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ORCH_DIR)
import orchestrator as o  # noqa: E402

PASS = []
FAIL = []

VALID_ID = "egpu-SWIFT-1.5-Uncensored"
DEFAULT_ID = "egpu-SWIFT-1.5"


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}"
          + (f" — {detail}" if detail and not cond else ""))


def _card_with_llm(model):
    """A card carrying a `## LLM` section with a `- Model:` line."""
    return ("# Card\n\n## Story\n\nbody\n\n## LLM\n\n- Model: "
            f"{model}\n\n## Log\n\n- 08.11.2026 09:00 **Created** — test.\n")


def _card_plain():
    """A card without a `## LLM` section."""
    return ("# Card\n\n## Story\n\nbody\n\n## Log\n\n"
            "- 08.11.2026 09:00 **Created** — test.\n")


def _resource(lanes):
    """Build a board resource tree from {lane: {card: content}}."""
    return [{"name": lane,
             "files": [{"name": c, "content": content}
                       for c, content in cards.items()]}
            for lane, cards in lanes.items()]


# --------------------------------------------------------------------------
# Pure _card_llm_model()
# --------------------------------------------------------------------------
def test_no_section():
    print("1. No `## LLM` section -> None")
    check("absent section -> None", o._card_llm_model(_card_plain()) is None)


def test_valid_section():
    print("2. `## LLM` with `- Model:` line -> the model ID")
    check("valid section -> ID",
          o._card_llm_model(_card_with_llm(VALID_ID)) == VALID_ID)


def test_section_without_model_line():
    print("3. `## LLM` section without a `- Model:` line -> None")
    content = "# Card\n\n## LLM\n\n(nothing here)\n\n## Log\n\n- x\n"
    check("empty section -> None", o._card_llm_model(content) is None)


def test_suffixed_heading():
    print("4. Suffixed heading is recognized")
    content = ("# Card\n\n## LLM (design note)\n\n- Model: "
               f"{DEFAULT_ID}\n\n## Log\n\n- x\n")
    check("suffixed heading -> ID",
          o._card_llm_model(content) == DEFAULT_ID,
          f"got {o._card_llm_model(content)!r}")


def test_backticked_id():
    print("5. Backticked model ID -> backticks stripped")
    content = ("# Card\n\n## LLM\n\n- Model: `"
               f"{VALID_ID}`\n\n## Log\n\n- x\n")
    check("backticks stripped",
          o._card_llm_model(content) == VALID_ID,
          f"got {o._card_llm_model(content)!r}")


def test_section_boundary_later_model_line():
    print("6. `- Model:` line in a LATER section is not picked up")
    content = ("# Card\n\n## LLM\n\n\n## Notes\n\n- Model: "
               f"{VALID_ID}\n\n## Log\n\n- x\n")
    check("later section's line ignored",
          o._card_llm_model(content) is None,
          f"got {o._card_llm_model(content)!r}")


def test_empty_section_then_later_section():
    print("7. Empty `## LLM` followed by a later `- Model:` line -> None")
    content = ("# Card\n\n## LLM\n\n## Repo\n\n- Model: "
               f"{VALID_ID}\n\n## Log\n\n- x\n")
    check("empty section -> None", o._card_llm_model(content) is None,
          f"got {o._card_llm_model(content)!r}")


# --------------------------------------------------------------------------
# Pure _resolve_card_model()
# --------------------------------------------------------------------------
def test_resolve_resource_none():
    print("8. resource is None -> None (no crash)")
    check("None resource -> None",
          o._resolve_card_model(None, "c1") is None)


def test_resolve_no_section():
    print("9. Card without a section -> None")
    res = _resource({"Ready": {"c1": _card_plain()}})
    check("no section -> None", o._resolve_card_model(res, "c1") is None)


def test_resolve_valid():
    print("10. Card with a valid ID -> the ID")
    res = _resource({"Ready": {"c1": _card_with_llm(VALID_ID)}})
    check("valid ID -> ID", o._resolve_card_model(res, "c1") == VALID_ID)


def test_resolve_invalid():
    print("11. Card with an invalid ID -> None + anomaly log")
    log_lines = []
    orig_log = o.log
    o.log = lambda msg, *args: log_lines.append(msg % args if args else msg)
    try:
        res = _resource({"Ready": {"c1": _card_with_llm("bogus-model")}})
        got = o._resolve_card_model(res, "c1")
    finally:
        o.log = orig_log
    check("invalid ID -> None", got is None, f"got {got!r}")
    check("anomaly logged",
          any("anomaly" in l and "bogus-model" in l for l in log_lines),
          f"log={log_lines!r}")


def test_resolve_card_absent():
    print("12. Card absent from the board -> None")
    res = _resource({"Ready": {"other": _card_with_llm(VALID_ID)}})
    check("absent card -> None", o._resolve_card_model(res, "c1") is None)


# --------------------------------------------------------------------------
# launch_worker() model precedence (Popen captured — no real worker)
# --------------------------------------------------------------------------
class _FakeProc:
    pid = 999999


def _launch_cmd(card_model=None, worker_model=None):
    """Run launch_worker() with Popen/save_state/log/pid_start_time
    monkeypatched; return the captured command list (or None on error)."""
    captured = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        return _FakeProc()

    orig_popen = o.subprocess.Popen
    orig_save = o.save_state
    orig_log = o.log
    orig_pid_start = o.pid_start_time
    orig_worker_model = dict(o.WORKER_MODEL)
    o.subprocess.Popen = fake_popen
    o.save_state = lambda state: None
    o.log = lambda msg, *args: None
    o.pid_start_time = lambda pid: 0
    if worker_model is not None:
        o.WORKER_MODEL["implement"] = worker_model
    state = o.empty_state()
    try:
        o.launch_worker(state, 2_000_000.0, ("Active", "c1"), card_model)
    finally:
        o.subprocess.Popen = orig_popen
        o.save_state = orig_save
        o.log = orig_log
        o.pid_start_time = orig_pid_start
        o.WORKER_MODEL.update(orig_worker_model)
    return captured.get("cmd")


def test_precedence_card_wins():
    print("13. card_model + WORKER_MODEL both set -> card_model wins")
    cmd = _launch_cmd(card_model=VALID_ID, worker_model="mode-model")
    check("cmd carries the card's model",
          cmd is not None and cmd[-2:] == ["--model", VALID_ID],
          f"cmd={cmd!r}")


def test_precedence_worker_model_fallback():
    print("14. card_model None + WORKER_MODEL set -> WORKER_MODEL used")
    cmd = _launch_cmd(card_model=None, worker_model="mode-model")
    check("cmd carries the mode model",
          cmd is not None and cmd[-2:] == ["--model", "mode-model"],
          f"cmd={cmd!r}")


def test_precedence_no_model_flag():
    print("15. Both None -> no --model flag (pi default)")
    cmd = _launch_cmd(card_model=None, worker_model=None)
    check("no --model in cmd",
          cmd is not None and "--model" not in cmd, f"cmd={cmd!r}")


# --------------------------------------------------------------------------
# evaluate_launch() threading
# --------------------------------------------------------------------------
def _run_evaluate(ready=(), resource=None, egpu=True):
    """One evaluate_launch() with everything monkeypatched. Returns
    (log_lines, launches) where launches is a list of (trigger, card_model)."""
    log_lines = []
    launches = []

    o.board_move_card = lambda card, src_lane, dst_lane: None
    o.egpu_up = lambda: egpu
    o.egpu_busy_avg = lambda: 0
    o.launch_worker = (lambda state, now, trigger, card_model=None, worker_cwd=None:
                       launches.append((trigger, card_model)))
    o.save_state = lambda state: None
    orig_log = o.log
    o.log = lambda msg, *args: log_lines.append(msg % args if args else msg)
    state = o.empty_state()
    try:
        o.evaluate_launch(state, 2_000_000.0, [], [], list(ready), None,
                          None, None, resource)
    finally:
        o.log = orig_log
    return log_lines, launches


def test_evaluate_valid_llm_threaded():
    print("16. Ready trigger with a valid `## LLM` card -> ID threaded")
    res = _resource({"Ready": {"c1": _card_with_llm(VALID_ID)}})
    log_lines, launches = _run_evaluate(ready=["c1"], resource=res)
    check("launch happened", len(launches) == 1, f"launches={launches!r}")
    check("card_model threaded to launch_worker",
          launches and launches[0][1] == VALID_ID, f"launches={launches!r}")


def test_evaluate_no_section():
    print("17. Ready trigger without a section -> None threaded")
    res = _resource({"Ready": {"c1": _card_plain()}})
    _, launches = _run_evaluate(ready=["c1"], resource=res)
    check("card_model is None (pi default)",
          launches and launches[0][1] is None, f"launches={launches!r}")


def test_evaluate_invalid_fallback():
    print("18. Ready trigger with an invalid ID -> None + anomaly")
    res = _resource({"Ready": {"c1": _card_with_llm("bogus-model")}})
    log_lines, launches = _run_evaluate(ready=["c1"], resource=res)
    check("launch still happens (never fails)",
          len(launches) == 1, f"launches={launches!r}")
    check("card_model falls back to None",
          launches and launches[0][1] is None, f"launches={launches!r}")
    check("anomaly logged",
          any("anomaly" in l and "bogus-model" in l for l in log_lines),
          f"log={log_lines!r}")


def test_evaluate_resource_none():
    print("19. resource is None -> None threaded (no crash)")
    _, launches = _run_evaluate(ready=["c1"], resource=None)
    check("card_model is None",
          launches and launches[0][1] is None, f"launches={launches!r}")


def main():
    tests = [
        test_no_section,
        test_valid_section,
        test_section_without_model_line,
        test_suffixed_heading,
        test_backticked_id,
        test_section_boundary_later_model_line,
        test_empty_section_then_later_section,
        test_resolve_resource_none,
        test_resolve_no_section,
        test_resolve_valid,
        test_resolve_invalid,
        test_resolve_card_absent,
        test_precedence_card_wins,
        test_precedence_worker_model_fallback,
        test_precedence_no_model_flag,
        test_evaluate_valid_llm_threaded,
        test_evaluate_no_section,
        test_evaluate_invalid_fallback,
        test_evaluate_resource_none,
    ]
    for t in tests:
        t()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED:", *FAIL, sep="\n  - ")
        sys.exit(1)


if __name__ == "__main__":
    main()
