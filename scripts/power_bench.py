#!/usr/bin/env python3
"""
power_bench.py — Benchmark llama.cpp tokens/s across GPU power limit settings.

Sweeps power limit high → low via lact CLI (no config.yaml changes).
Writes one CSV row per run; datetime is embedded in the output filename.

Usage examples:
  python3 power_bench.py
  python3 power_bench.py --min-watts 260 --max-watts 303 --step-watts 5 --runs 7
  python3 power_bench.py --output /tmp/my_bench.csv --settle 10
"""

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

LACT_CONTAINER  = "lact"
LACT_GPU_ID     = "0"

DEFAULT_SERVER_URL = "http://localhost:8092/v1/chat/completions"
DEFAULT_MODEL      = "Gemma-4-31B-it-The-DECKARD-HERETIC-UNCENSORED-Thinking.Q4_K_M"
DEFAULT_PROMPT     = (
    "Explain the history of mathematics in exhaustive detail covering every major "
    "development, mathematician, and theorem from ancient times to today."
)
DEFAULT_MAX_TOKENS = 2048

# ---------------------------------------------------------------------------
# lact helpers
# ---------------------------------------------------------------------------

def _lact(*args):
    """Run a lact CLI command inside the lact container. Returns stdout string."""
    cmd = ["docker", "exec", LACT_CONTAINER, "lact", "cli", "-g", LACT_GPU_ID] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"lact command failed: {' '.join(cmd)}\nstderr: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def get_power_limit_info() -> tuple[int, int, int]:
    """
    Return (current_watts, hw_min_watts, hw_max_watts) as reported by lact.
    e.g. "Current power limit: 303W (Configurable Range: 272W to 402W)"
    """
    output = _lact("power-limit", "get")
    m = re.search(
        r"Current power limit:\s*(\d+)W.*?(\d+)W to (\d+)W", output
    )
    if not m:
        raise RuntimeError(f"Could not parse power limit info from: {output}")
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def get_power_limit_watts() -> int:
    """Return only the current power limit in watts."""
    current, _, _ = get_power_limit_info()
    return current


def set_power_limit_watts(watts: int):
    """Set the power limit to the given wattage via lact."""
    output = _lact("power-limit", "set", str(watts))
    # Confirm it was accepted (lact prints "Updated power limit to NW")
    if str(watts) not in output:
        raise RuntimeError(f"Unexpected response from lact power-limit set: {output}")


# ---------------------------------------------------------------------------
# Inference helper
# ---------------------------------------------------------------------------

def run_inference(server_url: str, model: str, prompt: str, max_tokens: int,
                  timeout: int = 600) -> tuple[float, int]:
    """
    Send one chat completion request and return (tokens_per_second, n_tokens).
    Raises urllib.error.URLError / ValueError on failure.
    """
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "stream": False,
    }).encode()

    req = urllib.request.Request(
        server_url,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())

    timings = data.get("timings", {})
    tps = timings.get("predicted_per_second")
    n   = timings.get("predicted_n")

    if tps is None or n is None:
        raise ValueError(f"Missing timings in response: {data}")

    return float(tps), int(n)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_sweep(min_w: int, max_w: int, step_w: int) -> list[int]:
    """Return a list of power levels from high to low, inclusive of both endpoints."""
    levels = list(range(max_w, min_w - 1, -step_w))
    # Ensure min_w is included if it wasn't hit exactly by the step
    if levels[-1] != min_w:
        levels.append(min_w)
    return levels


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))

    parser = argparse.ArgumentParser(
        description="Sweep GPU power limit and record llama.cpp tokens/s to CSV.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--min-watts",  type=int, default=272,
                        help="Lowest power limit to test (W)")
    parser.add_argument("--max-watts",  type=int, default=303,
                        help="Highest power limit to test (W)")
    parser.add_argument("--step-watts", type=int, default=10,
                        help="Step size between levels (W)")
    parser.add_argument("--runs",       type=int, default=5,
                        help="Timed runs per power level")
    parser.add_argument("--warmup",     type=int, default=1,
                        help="Warm-up requests before timed runs (not recorded)")
    parser.add_argument("--settle",     type=int, default=5,
                        help="Seconds to wait after changing power limit")
    parser.add_argument("--server-url", default=DEFAULT_SERVER_URL,
                        help="llama-server chat completions endpoint")
    parser.add_argument("--model",      default=DEFAULT_MODEL,
                        help="Model name as registered in llama-server")
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS,
                        help="max_tokens for each completion request")
    parser.add_argument("--output",     default=None,
                        help="CSV output path (default: scripts/power_bench_<datetime>.csv)")
    args = parser.parse_args()

    # Validate arguments
    if args.min_watts >= args.max_watts:
        parser.error("--min-watts must be less than --max-watts")
    if args.step_watts <= 0:
        parser.error("--step-watts must be > 0")

    # Output path
    if args.output is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        args.output = os.path.join(script_dir, f"power_bench_{ts}.csv")

    # Build sweep
    levels = build_sweep(args.min_watts, args.max_watts, args.step_watts)
    total_runs = len(levels) * (args.warmup + args.runs)

    print(f"power_bench — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Sweep: {args.max_watts}W → {args.min_watts}W, step {args.step_watts}W "
          f"({len(levels)} levels)")
    print(f"  Runs per level: {args.runs} timed + {args.warmup} warm-up = "
          f"{args.warmup + args.runs} requests per level ({total_runs} total)")
    print(f"  Settle time: {args.settle}s  |  max_tokens: {args.max_tokens}")
    print(f"  Output: {args.output}")
    print()

    # Read and save original power limit; also validate against the hardware range
    try:
        original_watts, hw_min, hw_max = get_power_limit_info()
        print(f"Current power limit: {original_watts}W  "
              f"(hardware range: {hw_min}W – {hw_max}W)")
    except RuntimeError as e:
        print(f"ERROR: Could not read current power limit — is the lact container running?\n{e}",
              file=sys.stderr)
        sys.exit(1)

    if args.min_watts < hw_min:
        parser.error(f"--min-watts {args.min_watts} is below the hardware minimum of {hw_min}W")
    if args.max_watts > hw_max:
        parser.error(f"--max-watts {args.max_watts} exceeds the hardware maximum of {hw_max}W")

    # -----------------------------------------------------------------------
    # Run the sweep
    # -----------------------------------------------------------------------
    try:
        with open(args.output, "w", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["power_limit_w", "run", "tokens_per_sec", "num_tokens"])
            csvfile.flush()

            for level_idx, watts in enumerate(levels, start=1):
                print(f"[{level_idx}/{len(levels)}] Setting power limit to {watts}W …", end=" ")
                try:
                    set_power_limit_watts(watts)
                    print("OK")
                except RuntimeError as e:
                    print(f"FAILED — skipping level\n  {e}", file=sys.stderr)
                    continue

                if args.settle > 0:
                    print(f"  Settling {args.settle}s …")
                    time.sleep(args.settle)

                # Warm-up runs
                for w in range(1, args.warmup + 1):
                    print(f"  Warm-up {w}/{args.warmup} … ", end="", flush=True)
                    try:
                        tps, n = run_inference(
                            args.server_url, args.model, DEFAULT_PROMPT, args.max_tokens
                        )
                        print(f"t/s={tps:.1f} (not recorded)")
                    except Exception as e:
                        print(f"FAILED (ignored): {e}", file=sys.stderr)

                # Timed runs
                for run in range(1, args.runs + 1):
                    print(f"  Run {run}/{args.runs} … ", end="", flush=True)
                    try:
                        tps, n = run_inference(
                            args.server_url, args.model, DEFAULT_PROMPT, args.max_tokens
                        )
                        print(f"t/s={tps:.2f}, tokens={n}")
                        writer.writerow([watts, run, f"{tps:.4f}", n])
                        csvfile.flush()
                    except Exception as e:
                        print(f"FAILED — skipping run: {e}", file=sys.stderr)
                        # Write a sentinel so the run number stays trackable in the CSV
                        writer.writerow([watts, run, "ERROR", ""])
                        csvfile.flush()

    finally:
        # Always restore the original power limit, even on Ctrl+C or exception
        print(f"\nRestoring power limit to {original_watts}W … ", end="", flush=True)
        try:
            set_power_limit_watts(original_watts)
            print("OK")
        except RuntimeError as e:
            print(f"FAILED — please restore manually:\n  docker exec lact lact cli -g 0 power-limit set {original_watts}",
                  file=sys.stderr)

    print(f"\nDone. Results written to:\n  {args.output}")


if __name__ == "__main__":
    main()
