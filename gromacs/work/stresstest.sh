#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# stresstest.sh — GROMACS GPU stress test using the MPI-NAT benchmark set
#
# Downloads one of the official GROMACS developer benchmark systems
# (Kutzner/Grubmuller/Paell, https://www.mpinat.mpg.de/grubmueller/bench,
# CC-BY 4.0) and runs it for a fixed wall-clock time budget with GPU offload,
# reporting the resulting performance (ns/day).
#
# Duration is controlled via GROMACS's own -maxh flag (the standard mechanism
# for HPC queue-time-limited runs) rather than a step count, since step time
# varies wildly across the four systems (82k vs 12M atoms) — this way the
# actual run length is predictable no matter which benchmark you pick.
#
# Unlike smoketest.sh (synthetic water box, no network, verifies the build),
# this downloads real biomolecular systems and is meant to exercise sustained
# GPU/VRAM load — opt-in, requires network access.
#
# Usage (from inside the gromacs-rocm container):
#   bash /work/stresstest.sh [benchMEM|benchRIB|benchPEP|benchPEP-h] [minutes]
#   (with no args, prompts interactively; minutes defaults to 15)
# ---------------------------------------------------------------------------
set -euo pipefail

declare -A BENCH_INFO=(
  [benchMEM]="82k atoms, protein in membrane + water, 2 fs step — update: CPU"
  [benchRIB]="2M atoms, ribosome in water, 4 fs step — update: CPU"
  [benchPEP]="12M atoms, peptides in water, all-bonds constrained — update: CPU"
  [benchPEP-h]="12M atoms, peptides in water, h-bonds constrained — update: GPU-capable"
)
# Order matters for the interactive menu (bash 4+ associative arrays are unordered)
BENCH_ORDER=(benchMEM benchRIB benchPEP benchPEP-h)

BENCH="${1:-}"
MINUTES="${2:-15}"

if [[ -z "$BENCH" ]]; then
  echo "Available GROMACS GPU stress-test systems:"
  echo
  for name in "${BENCH_ORDER[@]}"; do
    echo "  $name — ${BENCH_INFO[$name]}"
  done
  echo
  select choice in "${BENCH_ORDER[@]}"; do
    if [[ -n "$choice" ]]; then
      BENCH="$choice"
      break
    fi
    echo "Invalid choice, try again."
  done
fi

if [[ -z "${BENCH_INFO[$BENCH]:-}" ]]; then
  echo "Unknown benchmark: $BENCH" >&2
  echo "Valid options: ${BENCH_ORDER[*]}" >&2
  exit 1
fi

echo
echo "=== Selected: $BENCH — ${BENCH_INFO[$BENCH]} ==="
echo "=== Time budget: ${MINUTES} min (override with: stresstest.sh $BENCH <minutes>) ==="

TESTDIR="/work/_stresstest/$BENCH"
mkdir -p "$TESTDIR"
cd "$TESTDIR"

if ! ls ./*.tpr >/dev/null 2>&1; then
  echo
  echo "=== Downloading $BENCH.zip (mpinat.mpg.de, CC-BY 4.0) ==="
  curl -fL -o bench.zip "https://www.mpinat.mpg.de/${BENCH}"
  unzip -o bench.zip
  rm -f bench.zip
else
  echo
  echo "=== Reusing already-downloaded $BENCH files in $TESTDIR ==="
fi

TPR="$(find . -maxdepth 2 -name '*.tpr' | head -1)"
if [[ -z "$TPR" ]]; then
  echo "FAIL: no .tpr file found after extracting $BENCH.zip" >&2
  exit 1
fi
echo "Using tpr: $TPR"

# Only benchPEP-h uses h-bonds-only constraints, which is what allows the
# integrator update step to be offloaded to the GPU too (see the benchmark
# set description: full offload needs "-pme gpu -update gpu -bonded gpu").
# The other three constrain all bonds, forcing the update step onto the CPU.
GPU_FLAGS=(-ntmpi 1 -nb gpu -pme gpu -bonded gpu)
if [[ "$BENCH" == "benchPEP-h" ]]; then
  GPU_FLAGS+=(-update gpu)
fi

HOURS=$(awk "BEGIN { printf \"%.4f\", $MINUTES / 60 }")

echo
echo "=== Running for ~${MINUTES} min (-maxh $HOURS) with: gmx mdrun ${GPU_FLAGS[*]} ==="
# -maxh: GROMACS stops cleanly once this much wall-clock time has elapsed,
#   regardless of system size — the actual duration control for this script.
# -nsteps: set far higher than any of these benchmarks would reach in the
#   time budget, so -maxh (not running out of steps) is what stops the run.
# -notunepme: disable PME auto-tuning so it can't interfere with a clean
#   -maxh stop (previously caused "PME tuning was still active" with -resetstep).
gmx mdrun -s "$TPR" -deffnm run -maxh "$HOURS" -nsteps 100000000 \
  -notunepme -noconfout "${GPU_FLAGS[@]}"

echo
echo "=== Performance report ==="
grep -A2 "^Performance:" run.log || true
echo
echo "PASS — see $TESTDIR/run.log for full details."
