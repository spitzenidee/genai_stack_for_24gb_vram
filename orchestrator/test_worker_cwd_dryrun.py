#!/usr/bin/env python3
"""Dry-run validation for the per-repo worker cwd (per-repo Hindsight banks).

Imports orchestrator.py and exercises _card_repo_name() (pure),
_resolve_worker_cwd() (pure + filesystem + anomaly log), launch_worker()
cwd/flag behavior (Popen monkeypatched — no real worker is launched), and
evaluate_launch() threading (launch_worker monkeypatched). No eGPU is
probed, no real board is mutated.

Covers:
  Pure _card_repo_name():
  1.  No `## Repo` section -> None (the common case).
  2.  `## Repo` with a `- Name:` line -> the name.
  3.  `## Repo` section without a `- Name:` line -> None.
  4.  Suffixed heading (`## Repo (note)`) is recognized.
  5.  Backticked name -> backticks stripped.
  6.  `- Name:` line in a LATER section is not picked up (section
      boundary honored).
  Pure _resolve_worker_cwd():
  7.  resource is None -> STACK_ROOT (no crash).
  8.  Card without a `## Repo` section -> STACK_ROOT.
  9.  `## Repo` + checkout present -> the checkout.
  10. `## Repo` + checkout missing -> STACK_ROOT + anomaly.
  11. `Name` = the stack repo's own basename -> STACK_ROOT (no anomaly).
  12. `Name` with a path separator -> STACK_ROOT + anomaly.
  13. Card absent from the board -> STACK_ROOT.
  launch_worker() cwd/flags (Popen captured):
  14. cwd = STACK_ROOT -> no --skill / --approve flags, cwd=STACK_ROOT.
  15. cwd = checkout -> --skill <stack>/.pi/skills + --approve,
      cwd=checkout.
  16. Entry prompt notes the checkout cwd (repo cards only).
  evaluate_launch() threading:
  17. Ready trigger with a repo card + checkout -> launch_worker gets the
      checkout.
  18. Ready trigger without a `## Repo` -> launch_worker gets STACK_ROOT.

Run:  python3 orchestrator/test_worker_cwd_dryrun.py
"""
import os
import shutil
import sys
import tempfile

ORCH_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ORCH_DIR)
import orchestrator as o  # noqa: E402

PASS = []
FAIL = []

FAKE_ROOT = None  # temp dir with basename "genai_stack" (set in main)


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}"
          + (f" — {detail}" if detail and not cond else ""))


def _card_with_repo(name):
    """A card carrying a `## Repo` section with a `- Name:` line."""
    return ("# Card\n\n## Story\n\nbody\n\n## Repo\n\n- Name: "
            f"{name}\n- Remote: http://example/repo.git\n"
            "- Base branch: dev\n\n## Log\n\n"
            "- 12.11.2026 12:00 **Created** — test.\n")


def _card_plain():
    """A card without a `## Repo` section."""
    return ("# Card\n\n## Story\n\nbody\n\n## Log\n\n"
            "- 12.11.2026 12:00 **Created** — test.\n")


def _resource(lanes):
    """Build a board resource tree from {lane: {card: content}}."""
    return [{"name": lane,
             "files": [{"name": c, "content": content}
                       for c, content in cards.items()]}
            for lane, cards in lanes.items()]


def _capture_log(fn, *args, **kwargs):
    """Run fn with o.log captured; return (result, log_lines)."""
    log_lines = []
    orig_log = o.log
    o.log = lambda msg, *a: log_lines.append(msg % a if a else msg)
    try:
        return fn(*args, **kwargs), log_lines
    finally:
        o.log = orig_log


# --------------------------------------------------------------------------
# Pure _card_repo_name()
# --------------------------------------------------------------------------
def test_no_section():
    print("1. No `## Repo` section -> None")
    check("absent section -> None",
          o._card_repo_name(_card_plain()) is None)


def test_valid_section():
    print("2. `## Repo` with `- Name:` line -> the name")
    check("valid section -> name",
          o._card_repo_name(_card_with_repo("homelab-docs")) == "homelab-docs")


def test_section_without_name_line():
    print("3. `## Repo` section without a `- Name:` line -> None")
    content = ("# Card\n\n## Repo\n\n- Remote: http://example/x.git\n"
               "\n## Log\n\n- x\n")
    check("no Name line -> None", o._card_repo_name(content) is None)


def test_suffixed_heading():
    print("4. Suffixed heading is recognized")
    content = ("# Card\n\n## Repo (design note)\n\n- Name: "
               "homelab-docs\n\n## Log\n\n- x\n")
    check("suffixed heading -> name",
          o._card_repo_name(content) == "homelab-docs",
          f"got {o._card_repo_name(content)!r}")


def test_backticked_name():
    print("5. Backticked name -> backticks stripped")
    content = ("# Card\n\n## Repo\n\n- Name: `homelab-docs`\n\n"
               "## Log\n\n- x\n")
    check("backticks stripped",
          o._card_repo_name(content) == "homelab-docs",
          f"got {o._card_repo_name(content)!r}")


def test_section_boundary_later_name_line():
    print("6. `- Name:` line in a LATER section is not picked up")
    content = ("# Card\n\n## Repo\n\n\n## Notes\n\n- Name: "
               "homelab-docs\n\n## Log\n\n- x\n")
    check("later section's line ignored",
          o._card_repo_name(content) is None,
          f"got {o._card_repo_name(content)!r}")


# --------------------------------------------------------------------------
# Pure _resolve_worker_cwd()
# --------------------------------------------------------------------------
def test_resolve_resource_none():
    print("7. resource is None -> STACK_ROOT (no crash)")
    check("None resource -> STACK_ROOT",
          o._resolve_worker_cwd(None, "c1") == o.STACK_ROOT)


def test_resolve_no_section():
    print("8. Card without a `## Repo` section -> STACK_ROOT")
    res = _resource({"Ready": {"c1": _card_plain()}})
    check("no section -> STACK_ROOT",
          o._resolve_worker_cwd(res, "c1") == o.STACK_ROOT)


def test_resolve_checkout_present():
    print("9. `## Repo` + checkout present -> the checkout")
    checkout = os.path.join(o.STACK_ROOT, "work", "orchestrator",
                            "homelab-docs")
    os.makedirs(checkout, exist_ok=True)
    try:
        res = _resource({"Ready": {"c1": _card_with_repo("homelab-docs")}})
        got = o._resolve_worker_cwd(res, "c1")
        check("checkout present -> checkout", got == checkout,
              f"got {got!r}")
    finally:
        shutil.rmtree(checkout, ignore_errors=True)


def test_resolve_checkout_missing():
    print("10. `## Repo` + checkout missing -> STACK_ROOT + anomaly")
    res = _resource({"Ready": {"c1": _card_with_repo("no-such-repo")}})
    got, log_lines = _capture_log(o._resolve_worker_cwd, res, "c1")
    check("missing checkout -> STACK_ROOT", got == o.STACK_ROOT,
          f"got {got!r}")
    check("anomaly logged",
          any("anomaly" in l and "no-such-repo" in l for l in log_lines),
          f"log={log_lines!r}")


def test_resolve_stack_own_repo():
    print("11. `Name` = the stack repo's own basename -> STACK_ROOT")
    res = _resource({"Ready": {"c1": _card_with_repo("genai_stack")}})
    got, log_lines = _capture_log(o._resolve_worker_cwd, res, "c1")
    check("stack-own repo -> STACK_ROOT", got == o.STACK_ROOT,
          f"got {got!r}")
    check("no anomaly for the stack-own repo",
          not any("anomaly" in l for l in log_lines),
          f"log={log_lines!r}")


def test_resolve_path_separator():
    print("12. `Name` with a path separator -> STACK_ROOT + anomaly")
    res = _resource({"Ready": {"c1": _card_with_repo("a/b")}})
    got, log_lines = _capture_log(o._resolve_worker_cwd, res, "c1")
    check("path separator -> STACK_ROOT", got == o.STACK_ROOT,
          f"got {got!r}")
    check("anomaly logged",
          any("anomaly" in l and "a/b" in l for l in log_lines),
          f"log={log_lines!r}")


def test_resolve_card_absent():
    print("13. Card absent from the board -> STACK_ROOT")
    res = _resource({"Ready": {"other": _card_with_repo("homelab-docs")}})
    check("absent card -> STACK_ROOT",
          o._resolve_worker_cwd(res, "c1") == o.STACK_ROOT)


# --------------------------------------------------------------------------
# launch_worker() cwd/flags (Popen captured — no real worker)
# --------------------------------------------------------------------------
class _FakeProc:
    pid = 999999


def _launch_capture(worker_cwd=None):
    """Run launch_worker() with Popen/save_state/log/pid_start_time
    monkeypatched; return the captured (cmd, kwargs) (or (None, None))."""
    captured = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return _FakeProc()

    orig_popen = o.subprocess.Popen
    orig_save = o.save_state
    orig_log = o.log
    orig_pid_start = o.pid_start_time
    o.subprocess.Popen = fake_popen
    o.save_state = lambda state: None
    o.log = lambda msg, *args: None
    o.pid_start_time = lambda pid: 0
    state = o.empty_state()
    try:
        o.launch_worker(state, 2_000_000.0, ("Active", "c1"),
                        None, worker_cwd)
    finally:
        o.subprocess.Popen = orig_popen
        o.save_state = orig_save
        o.log = orig_log
        o.pid_start_time = orig_pid_start
    return captured.get("cmd"), captured.get("kwargs")


def test_launch_stack_root_no_flags():
    print("14. cwd = STACK_ROOT -> no --skill / --approve flags")
    cmd, kwargs = _launch_capture(worker_cwd=None)
    check("cmd captured", cmd is not None, "no cmd captured")
    check("no --skill flag", cmd is not None and "--skill" not in cmd,
          f"cmd={cmd!r}")
    check("no --approve flag", cmd is not None and "--approve" not in cmd,
          f"cmd={cmd!r}")
    check("cwd=STACK_ROOT",
          kwargs is not None and kwargs.get("cwd") == o.STACK_ROOT,
          f"kwargs={kwargs!r}")


def test_launch_checkout_flags():
    print("15. cwd = checkout -> --skill + --approve, cwd=checkout")
    checkout = os.path.join(o.STACK_ROOT, "work", "orchestrator",
                            "homelab-docs")
    os.makedirs(checkout, exist_ok=True)
    try:
        cmd, kwargs = _launch_capture(worker_cwd=checkout)
        check("cmd captured", cmd is not None, "no cmd captured")
        check("--skill <stack>/.pi/skills present",
              cmd is not None
              and cmd.count("--skill") == 1
              and cmd[cmd.index("--skill") + 1]
              == os.path.join(o.STACK_ROOT, ".pi", "skills"),
              f"cmd={cmd!r}")
        check("--approve present", cmd is not None and "--approve" in cmd,
              f"cmd={cmd!r}")
        check("cwd=checkout",
              kwargs is not None and kwargs.get("cwd") == checkout,
              f"kwargs={kwargs!r}")
    finally:
        shutil.rmtree(checkout, ignore_errors=True)


def test_entry_prompt_note():
    print("16. Entry prompt notes the checkout cwd (repo cards only)")
    checkout = os.path.join(o.STACK_ROOT, "work", "orchestrator",
                            "homelab-docs")
    os.makedirs(checkout, exist_ok=True)
    try:
        cmd_repo, _ = _launch_capture(worker_cwd=checkout)
        prompt_repo = cmd_repo[cmd_repo.index("-p") + 1] \
            if cmd_repo else ""
        check("repo prompt names the checkout",
              checkout in prompt_repo, f"prompt={prompt_repo!r}")
        check("repo prompt says to operate on `.`",
              "clone into a subpath" in prompt_repo,
              f"prompt={prompt_repo!r}")
        cmd_plain, _ = _launch_capture(worker_cwd=None)
        prompt_plain = cmd_plain[cmd_plain.index("-p") + 1] \
            if cmd_plain else ""
        check("non-repo prompt has no cwd note",
              "session cwd is the repo checkout" not in prompt_plain,
              f"prompt={prompt_plain!r}")
    finally:
        shutil.rmtree(checkout, ignore_errors=True)


# --------------------------------------------------------------------------
# evaluate_launch() threading
# --------------------------------------------------------------------------
def _run_evaluate(ready=(), resource=None, egpu=True):
    """One evaluate_launch() with everything monkeypatched. Returns
    (log_lines, launches) where launches is a list of
    (trigger, card_model, worker_cwd)."""
    log_lines = []
    launches = []

    o.board_move_card = lambda card, src_lane, dst_lane: None
    o.egpu_up = lambda: egpu
    o.egpu_busy_avg = lambda: 0
    o.launch_worker = (lambda state, now, trigger, card_model=None,
                       worker_cwd=None:
                       launches.append((trigger, card_model, worker_cwd)))
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


def test_evaluate_repo_card_threaded():
    print("17. Ready trigger with a repo card + checkout -> checkout threaded")
    checkout = os.path.join(o.STACK_ROOT, "work", "orchestrator",
                            "homelab-docs")
    os.makedirs(checkout, exist_ok=True)
    try:
        res = _resource({"Ready": {"c1": _card_with_repo("homelab-docs")}})
        _, launches = _run_evaluate(ready=["c1"], resource=res)
        check("launch happened", len(launches) == 1, f"launches={launches!r}")
        check("worker_cwd threaded to launch_worker",
              launches and launches[0][2] == checkout,
              f"launches={launches!r}")
    finally:
        shutil.rmtree(checkout, ignore_errors=True)


def test_evaluate_no_repo_section():
    print("18. Ready trigger without a `## Repo` -> STACK_ROOT threaded")
    res = _resource({"Ready": {"c1": _card_plain()}})
    _, launches = _run_evaluate(ready=["c1"], resource=res)
    check("worker_cwd is STACK_ROOT",
          launches and launches[0][2] == o.STACK_ROOT,
          f"launches={launches!r}")


def main():
    global FAKE_ROOT
    # A temp stack root with the real basename ("genai_stack") so the
    # stack-own-repo rule and the checkout paths behave like production.
    parent = tempfile.mkdtemp(prefix="worker-cwd-dryrun-")
    FAKE_ROOT = os.path.join(parent, "genai_stack")
    os.makedirs(FAKE_ROOT)
    orig_root = o.STACK_ROOT
    o.STACK_ROOT = FAKE_ROOT
    try:
        tests = [
            test_no_section,
            test_valid_section,
            test_section_without_name_line,
            test_suffixed_heading,
            test_backticked_name,
            test_section_boundary_later_name_line,
            test_resolve_resource_none,
            test_resolve_no_section,
            test_resolve_checkout_present,
            test_resolve_checkout_missing,
            test_resolve_stack_own_repo,
            test_resolve_path_separator,
            test_resolve_card_absent,
            test_launch_stack_root_no_flags,
            test_launch_checkout_flags,
            test_entry_prompt_note,
            test_evaluate_repo_card_threaded,
            test_evaluate_no_repo_section,
        ]
        for t in tests:
            t()
    finally:
        o.STACK_ROOT = orig_root
        shutil.rmtree(parent, ignore_errors=True)
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED:", *FAIL, sep="\n  - ")
        sys.exit(1)


if __name__ == "__main__":
    main()
