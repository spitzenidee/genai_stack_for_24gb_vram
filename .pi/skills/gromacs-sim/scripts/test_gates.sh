#!/usr/bin/env bash
# test_gates.sh — unit tests for the gate scripts (CPU-testable subset).
#
# Builds a throwaway fixture project (pdb2gmx + solvation, ~1 min, transient
# containers, any stack mode) and checks each gate's exit code against the
# expected value — including negative cases (tampered fixtures must FAIL).
#
# Usage: test_gates.sh
# Exit:   0 all tests pass, 1 any test fails.
set -uo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STACK_ROOT="$(cd "$SKILL_DIR/../../.." && pwd)"
IMAGE="gromacs-hip-gfx1100:latest"
PDB="$STACK_ROOT/gromacs/work/gmx_tutorials_livecoms/tutorial-files/01_lysozyme/lysozyme.pdb"
FIX="$(mktemp -d)"
SIM="$STACK_ROOT/gromacs/work/projects/_gatestest"
cleanup() {
  rm -rf "$FIX"
  # fixture files are root-owned (docker run) — remove via container if needed
  rm -rf "$SIM" 2>/dev/null || docker run --rm -v "$STACK_ROOT/gromacs/work":/work \
    "$IMAGE" rm -rf /work/projects/_gatestest 2>/dev/null
}
trap cleanup EXIT

passed=0; failed=0
ok()   { echo "TEST PASS  $1"; passed=$((passed+1)); }
bad()  { echo "TEST FAIL  $1"; failed=$((failed+1)); }
# expect <name> <expected_rc> <actual_rc>
expect() {
  if [ "$2" = "$3" ]; then ok "$1 (rc=$3)"; else bad "$1 (expected rc=$2, got rc=$3)"; fi
}

[ -f "$PDB" ] || { echo "ENV|no conformance PDB at $PDB"; exit 1; }
docker image inspect "$IMAGE" >/dev/null 2>&1 || { echo "ENV|$IMAGE missing"; exit 1; }

echo "=== building fixture (this takes ~1 min) ==="
rm -rf "$SIM" 2>/dev/null || docker run --rm -v "$STACK_ROOT/gromacs/work":/work \
  "$IMAGE" rm -rf /work/projects/_gatestest 2>/dev/null
mkdir -p "$SIM/input" "$SIM/01_prep" "$SIM/03_solvation"
cp "$PDB" "$SIM/input/"
sed -E 's/<<<[A-Za-z0-9_]+:([^>]*)>>>/\1/g' "$SKILL_DIR/assets/em.mdp" > "$SIM/03_solvation/em.mdp"
cp "$SKILL_DIR/assets/ions.mdp" "$SIM/03_solvation/"

docker run --rm -v "$STACK_ROOT/gromacs/work":/work "$IMAGE" bash -c "
set -e
cd /work/projects/_gatestest
grep -v '^HETATM' input/lysozyme.pdb > 01_prep/clean.pdb
gmx pdb2gmx -f 01_prep/clean.pdb -ff amber14sb -water opc \
    -i 01_prep/posre.itp -o 01_prep/protein.gro -p 01_prep/protein.top \
    > 01_prep/pdb2gmx.log 2>&1
cp 01_prep/protein.gro 01_prep/protein.top 01_prep/posre.itp 03_solvation/
cd 03_solvation
gmx editconf -f protein.gro -c -bt cubic -d 1.0 -o newbox.gro > /dev/null 2>&1
gmx solvate -cp newbox.gro -cs tip4p.gro -o solv.gro -p protein.top > /dev/null 2>&1
gmx grompp -f ions.mdp -c solv.gro -p protein.top -o solv.tpr > /dev/null 2>&1
printf '13\n' | gmx genion -s solv.tpr -p protein.top -o ions.gro -neutral -conc 0.15 > /dev/null 2>&1
mv protein.top topol.top
" || { echo "ENV|fixture build failed"; exit 1; }
# fixture 01_prep topology must be pre-solvation (protein only)
sed -i '/^SOL /d;/^NA /d;/^CL /d' "$SIM/01_prep/protein.top"
echo "=== fixture ready ==="

# --- preflight --cpu -----------------------------------------------------------
"$SKILL_DIR/scripts/preflight.sh" "$SIM" --cpu > "$FIX/pf.out" 2>&1
expect "preflight --cpu" 0 $?
grep -q "FAIL" "$FIX/pf.out" && bad "preflight has FAIL lines" || ok "preflight no FAIL lines"

# --- check_prep: positive --------------------------------------------------------
"$SKILL_DIR/scripts/check_prep.sh" "$SIM" > "$FIX/cp.out" 2>&1
expect "check_prep (clean)" 0 $?

# --- check_prep: negative — non-integer residue charge ---------------------------
# (fixture files are root-owned from docker run — tamper inside the container)
top="$SIM/01_prep/protein.top"
cp "$top" "$FIX/top.bak"
docker run --rm -v "$STACK_ROOT/gromacs/work":/work "$IMAGE" bash -c "
  awk 'BEGIN{done=0} !done && \$1 ~ /^[0-9]+$/ && NF>=7 && \$7 ~ /^-?[0-9]/{ \$7=\$7+0.3; done=1 } {print}' \
    /work/projects/_gatestest/01_prep/protein.top > /tmp/t.t
  mv /tmp/t.t /work/projects/_gatestest/01_prep/protein.top"
"$SKILL_DIR/scripts/check_prep.sh" "$SIM" > "$FIX/cp2.out" 2>&1
rc=$?
expect "check_prep (tampered charge)" 1 $rc
grep -q "FAIL|residue_charge" "$FIX/cp2.out" && ok "failure named residue_charge" || bad "no residue_charge FAIL line"
rm "$top" && cp "$FIX/top.bak" "$top"

# --- check_prep: negative — gro/top atom count mismatch ---------------------------
sed -i '2s/.*/1965/' "$SIM/01_prep/protein.gro"
"$SKILL_DIR/scripts/check_prep.sh" "$SIM" > "$FIX/cp3.out" 2>&1
expect "check_prep (atom count mismatch)" 1 $?
# restore
docker run --rm -v "$STACK_ROOT/gromacs/work":/work "$IMAGE" bash -c "
gmx pdb2gmx -f /work/projects/_gatestest/01_prep/clean.pdb -ff amber14sb -water opc \
    -i /work/projects/_gatestest/01_prep/posre.itp -o /work/projects/_gatestest/01_prep/protein.gro \
    -p /work/projects/_gatestest/01_prep/protein.top > /dev/null 2>&1
sed -i '/^SOL /d;/^NA /d;/^CL /d' /work/projects/_gatestest/01_prep/protein.top"
"$SKILL_DIR/scripts/check_prep.sh" "$SIM" > /dev/null 2>&1
expect "check_prep (restored)" 0 $?

# --- check_solvation: positive ------------------------------------------------------
"$SKILL_DIR/scripts/check_solvation.sh" "$SIM" > "$FIX/cs.out" 2>&1
expect "check_solvation (clean)" 0 $?

# --- check_solvation: negative — no ions --------------------------------------------
cp "$SIM/03_solvation/topol.top" "$FIX/topol.bak"
sed -i '/^NA /d;/^CL /d' "$SIM/03_solvation/topol.top"
"$SKILL_DIR/scripts/check_solvation.sh" "$SIM" > "$FIX/cs2.out" 2>&1
expect "check_solvation (no ions)" 1 $?
grep -q "FAIL|ions" "$FIX/cs2.out" && ok "failure named ions" || bad "no ions FAIL line"
rm "$SIM/03_solvation/topol.top" && cp "$FIX/topol.bak" "$SIM/03_solvation/topol.top"

# --- check_templates ------------------------------------------------------------------
"$SKILL_DIR/scripts/check_templates.sh" > "$FIX/ct.out" 2>&1
expect "check_templates" 0 $?

# --- check_prod drift awk: header-line regression (I-9) ------------------------------
# xvg files start with ~20-30 header lines; the drift awk must count DATA points
# (dp++), never NR (file line count) — the NR bug read a real 0.05% drift as
# 5.07% and failed a passing production run (lysozym 2026-09-25, RCA issue 2).
# Extract the awk program from check_prod.sh so the test tracks the script.
drift_awk="$(python3 - "$SKILL_DIR/scripts/check_prod.sh" <<'PYEOF'
import re, sys
src = open(sys.argv[1]).read()
m = re.search(r'drift="\$\(awk \'(.*?)\' "\$work/e\.xvg"\)"', src, re.S)
sys.exit(1) if m is None else print(m.group(1), end="")
PYEOF
)"
if [ -n "$drift_awk" ]; then
  # 24 header lines (12 @ + 12 #) + 100 data points.
  # pass file: value = 100 + 0.001*i -> first/last-10% drift ~0.09% (< 5%)
  # fail file: value = 100 + 0.1111*i -> drift ~9.9% (>= 5%)
  for which in pass fail; do
    c="0.001"; [ "$which" = fail ] && c="0.1111"
    { for h in $(seq 12); do echo '@ xlab "time (ps)"'; done
      for h in $(seq 12); do echo "# comment line $h"; done
      awk -v c="$c" 'BEGIN{for(i=1;i<=100;i++) printf "%d %.4f\n", i, 100 + i*c}'
    } > "$FIX/drift_$which.xvg"
  done
  got="$(awk "$drift_awk" "$FIX/drift_pass.xvg")"
  awk -v g="$got" 'BEGIN{exit !(g > 0.0001 && g < 0.002)}' \
    && ok "drift awk w/ headers (0.09% -> $got)" \
    || bad "drift awk w/ headers (0.09% -> $got, expected ~0.0009)"
  got="$(awk "$drift_awk" "$FIX/drift_fail.xvg")"
  awk -v g="$got" 'BEGIN{exit !(g >= 0.05)}' \
    && ok "drift awk w/ headers (9.9% -> $got)" \
    || bad "drift awk w/ headers (9.9% -> $got, expected >= 0.05)"
else
  bad "drift awk extraction from check_prod.sh (pattern changed?)"
fi

# --- cleanup: fixtures (fake files — cleanup.sh only checks existence) -----------
rm -rf "$FIX/negsim"; mkdir -p "$FIX/negsim/07_analysis"
mkdir -p "$SIM/05_equil" "$SIM/06_production" "$SIM/07_analysis"
touch "$SIM/06_production/md.xtc" "$SIM/06_production/md.cpt" "$SIM/06_production/md_prev.cpt"
touch "$SIM/05_equil/nvt.cpt" "$SIM/05_equil/npt.cpt"
touch "$SIM/07_analysis/REPORT.md" "$SIM/07_analysis/clean.xtc" \
      "$SIM/07_analysis/step1.xtc" "$SIM/07_analysis/msd_unwrapped.xtc"
touch "$SIM/07_analysis/#clean.xtc.1#" "$SIM/07_analysis/#step1.xtc.1#" \
      "$SIM/07_analysis/#rmsf.xvg.1#" "$SIM/01_prep/#protein.top.1#"
printf '{"phase": 7, "phase_status": "completed"}\n' > "$SIM/state.json"

# --- cleanup: negative — no REPORT.md (analysis not complete) ----------------------
"$SKILL_DIR/scripts/cleanup.sh" "$FIX/negsim" --apply > "$FIX/cl0.out" 2>&1
expect "cleanup (no REPORT.md)" 2 $?

# --- cleanup: dry-run deletes nothing -------------------------------------------------
"$SKILL_DIR/scripts/cleanup.sh" "$SIM" > "$FIX/cl1.out" 2>&1
expect "cleanup (dry-run)" 0 $?
[ -f "$SIM/07_analysis/#clean.xtc.1#" ] && ok "dry-run left #clean.xtc.1#" \
  || bad "dry-run deleted #clean.xtc.1#"
[ -f "$SIM/06_production/md.cpt" ] && ok "dry-run left md.cpt" \
  || bad "dry-run deleted md.cpt"
[ -f "$SIM/cleanup_report.txt" ] && grep -q "mode: dry-run" "$SIM/cleanup_report.txt" \
  && ok "cleanup_report.txt written (dry-run)" || bad "cleanup_report.txt missing/wrong"

# --- cleanup: apply ----------------------------------------------------------------------
"$SKILL_DIR/scripts/cleanup.sh" "$SIM" --apply > "$FIX/cl2.out" 2>&1
expect "cleanup (--apply)" 0 $?
leftover=""
for f in "$SIM/07_analysis/#clean.xtc.1#" "$SIM/07_analysis/#step1.xtc.1#" \
         "$SIM/07_analysis/#rmsf.xvg.1#" "$SIM/01_prep/#protein.top.1#" \
         "$SIM/06_production/md.cpt" "$SIM/06_production/md_prev.cpt" \
         "$SIM/05_equil/nvt.cpt" "$SIM/05_equil/npt.cpt" \
         "$SIM/07_analysis/step1.xtc" "$SIM/07_analysis/msd_unwrapped.xtc"; do
  [ -e "$f" ] && leftover="$leftover $(basename "$f")"
done
[ -z "$leftover" ] && ok "all transient artifacts deleted" || bad "leftover:$leftover"
kept=""
for f in "$SIM/06_production/md.xtc" "$SIM/07_analysis/clean.xtc" \
         "$SIM/07_analysis/REPORT.md"; do
  [ -f "$f" ] || kept="$kept $(basename "$f")"
done
[ -z "$kept" ] && ok "permanent artifacts intact" || bad "missing permanent:$kept"

# --- cleanup: idempotent -------------------------------------------------------------------
"$SKILL_DIR/scripts/cleanup.sh" "$SIM" --apply > "$FIX/cl3.out" 2>&1
expect "cleanup (idempotent re-apply)" 0 $?
grep -q "0 files" "$FIX/cl3.out" && ok "re-apply freed 0 files" || bad "re-apply not a no-op"

echo "=== $passed passed, $failed failed ==="
[ "$failed" = 0 ]
