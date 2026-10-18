#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# smoketest.sh — GROMACS HIP/GPU integration smoke test
#
# Builds a tiny synthetic water box (using GROMACS's built-in spc216.gro +
# oplsaa force field — no external downloads needed), runs energy
# minimization + a short NVT MD run with full GPU offload, and checks that
# both complete successfully and actually dispatched work to the GPU.
#
# Usage (from inside the gromacs-rocm container):
#   bash /work/smoketest.sh
# ---------------------------------------------------------------------------
set -euo pipefail

TESTDIR="/work/_smoketest"
rm -rf "$TESTDIR"
mkdir -p "$TESTDIR"
cd "$TESTDIR"

echo "=== 1/5: gmx --version (sanity check) ==="
gmx --version | grep -E "GROMACS version|GPU support"

echo
echo "=== 2/5: build topology + solvate a 3nm water box ==="
cat > topol.top <<'EOF'
#include "oplsaa.ff/forcefield.itp"
#include "oplsaa.ff/spc.itp"

[ system ]
GPU smoke test — water box

[ molecules ]
EOF
gmx solvate -cs spc216.gro -o conf.gro -box 3 3 3 -p topol.top

echo
echo "=== 3/5: energy minimization (GPU non-bonded) ==="
cat > em.mdp <<'EOF'
integrator    = steep
emtol         = 1000.0
emstep        = 0.01
nsteps        = 500
nstlist       = 10
cutoff-scheme = Verlet
coulombtype   = PME
rcoulomb      = 1.0
rvdw          = 1.0
pbc           = xyz
EOF
gmx grompp -f em.mdp -c conf.gro -p topol.top -o em.tpr -maxwarn 5
gmx mdrun -deffnm em -ntmpi 1 -nb gpu

echo
echo "=== 4/5: short NVT run, full GPU offload (nb+pme+update) ==="
cat > nvt.mdp <<'EOF'
integrator    = md
nsteps        = 5000
dt            = 0.002
nstlist       = 20
cutoff-scheme = Verlet
coulombtype   = PME
rcoulomb      = 1.0
rvdw          = 1.0
tcoupl        = V-rescale
tc-grps       = System
tau_t         = 0.1
ref_t         = 300
pbc           = xyz
constraints   = h-bonds
EOF
gmx grompp -f nvt.mdp -c em.gro -p topol.top -o nvt.tpr -maxwarn 5
gmx mdrun -deffnm nvt -ntmpi 1 -nb gpu -pme gpu -update gpu

echo
echo "=== 5/5: verify GPU was actually used + run finished cleanly ==="
if ! grep -q "Finished mdrun" nvt.log; then
  echo "FAIL: nvt.log does not report a finished mdrun run" >&2
  exit 1
fi
if ! grep -qi "gfx1100\|Radeon\|GPU info" nvt.log; then
  echo "FAIL: nvt.log shows no evidence of GPU device usage" >&2
  exit 1
fi
echo
echo "PASS — GROMACS HIP build completed a full GPU-offloaded MD run."
echo "See $TESTDIR/nvt.log for the performance report (ns/day, GPU kernel timings)."
