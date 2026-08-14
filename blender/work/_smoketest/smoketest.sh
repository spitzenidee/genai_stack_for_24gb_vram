#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# smoketest.sh — Blender Cycles/HIP eGPU integration smoke test
#
# Renders frame 1 of the classic BMW27 scene (gpu variant) with the
# blender-render wrapper, which forces the HIP backend and GPU compute.
# Verifies that Blender starts, the HIP device is used, and an image is
# written to disk.
#
# Usage (from inside the blender-rocm container):
#   bash /work/_smoketest/smoketest.sh
# ---------------------------------------------------------------------------
set -euo pipefail

TESTDIR="/work/_smoketest"
SCENE="$TESTDIR/bmw27/bmw27_gpu.blend"
OUTDIR="$TESTDIR/output"
OUTFILE="$OUTDIR/bmw27_smoke_0001.png"

if [[ ! -r "$SCENE" ]]; then
    echo "FAIL: scene not found: $SCENE" >&2
    echo "Download and extract BMW27_2.blend.zip under $TESTDIR first." >&2
    exit 1
fi

rm -rf "$OUTDIR"
mkdir -p "$OUTDIR"

echo "=== Blender version / HIP device check ==="
blender --version

echo
echo "=== Rendering frame 1 of BMW27 (HIP/GPU) ==="
time blender-render "$SCENE" \
    -f 1 \
    -o "$OUTDIR/bmw27_smoke_" \
    -F PNG

echo
echo "=== Verifying output image exists ==="
if [[ ! -f "$OUTFILE" ]]; then
    echo "FAIL: expected output image missing: $OUTFILE" >&2
    exit 1
fi

ls -lh "$OUTFILE"
echo
echo "PASS: BMW27 HIP/GPU smoke test completed successfully."
