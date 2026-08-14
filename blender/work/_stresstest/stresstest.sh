#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# stresstest.sh — Blender Cycles/HIP eGPU stress test
#
# Renders frame 1 of the Barbershop Interior scene with the blender-render
# wrapper (HIP backend, GPU compute forced). This scene is heavier than
# BMW27 or Classroom and exercises sustained GPU/VRAM load.
#
# Usage (from inside the blender-rocm container):
#   bash /work/_stresstest/stresstest.sh
# ---------------------------------------------------------------------------
set -euo pipefail

TESTDIR="/work/_stresstest"
SCENE="$TESTDIR/barbershop_interior.blend"
OUTDIR="$TESTDIR/output"
OUTFILE="$OUTDIR/barbershop_stress_0001.png"

if [[ ! -r "$SCENE" ]]; then
    echo "FAIL: scene not found: $SCENE" >&2
    echo "Download barbershop_interior.blend into $TESTDIR first." >&2
    exit 1
fi

rm -rf "$OUTDIR"
mkdir -p "$OUTDIR"

echo "=== Blender version / HIP device check ==="
blender --version

echo
echo "=== Rendering frame 1 of Barbershop Interior (HIP/GPU) ==="
time blender-render "$SCENE" \
    -f 1 \
    -o "$OUTDIR/barbershop_stress_" \
    -F PNG

echo
echo "=== Verifying output image exists ==="
if [[ ! -f "$OUTFILE" ]]; then
    echo "FAIL: expected output image missing: $OUTFILE" >&2
    exit 1
fi

ls -lh "$OUTFILE"
echo
echo "PASS: Barbershop Interior HIP/GPU stress test completed successfully."
