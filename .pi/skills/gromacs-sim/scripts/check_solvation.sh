#!/usr/bin/env bash
# check_solvation.sh — phase-3 (solvation) gate.
#
# Usage: check_solvation.sh <sim_dir>
# Expects: 03_solvation/{ions.gro, <top>.top, em.mdp}
# Checks:  grompp test with assets/em.mdp succeeds (transient container);
#          rcutoff < 1/2 min(box vectors); net charge integer and ~0;
#          ion counts > 0; [ molecules ] atom total == .gro atom count.
# Exit:   0 pass, 1 fail, 2 environment error.
set -euo pipefail

SIM="$(realpath "${1:?usage: $0 <sim_dir>}")"
SOLV="$SIM/03_solvation"
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STACK_ROOT="$(cd "$SKILL_DIR/../../.." && pwd)"
IMAGE="gromacs-hip-gfx1100:latest"
fail=0
pass() { echo "PASS|$1|$2"; }
failc() { echo "FAIL|$1|$2"; fail=1; }
env() { echo "ENV|$1|$2"; exit 2; }

[ -d "$SOLV" ] || env solv "03_solvation/ missing in $SIM"
GRO="$SOLV/ions.gro"
TOP="$(find "$SOLV" -maxdepth 1 -name '*.top' | head -1)"
MDP="$SOLV/em.mdp"
[ -f "$GRO" ] || env gro "missing $GRO"
[ -n "$TOP" ] || env top "no .top in $SOLV"
[ -f "$MDP" ] || env mdp "missing $MDP (render assets/em.mdp into the phase dir first)"

# container-side path (mount: $STACK_ROOT/gromacs/work -> /work)
case "$SIM" in
  "$STACK_ROOT"/gromacs/work/*) CPATH="/work/${SIM#$STACK_ROOT/gromacs/work/}" ;;
  *) env mount "sim dir not under $STACK_ROOT/gromacs/work: $SIM" ;;
esac

# --- (1) grompp test with em.mdp ----------------------------------------------
# grompp also proves top<->gro atom-count consistency (it fails on mismatch),
# so the molecules/gro check below is a structural sanity check only.
if out="$(docker run --rm -w "$CPATH/03_solvation" -v "$STACK_ROOT/gromacs/work":/work \
      "$IMAGE" gmx grompp -f em.mdp -c ions.gro -p "$(basename "$TOP")" -o _gate.tpr 2>&1)"; then
  pass grompp "em.mdp test grompp succeeded (top<->gro consistent)"
else
  failc grompp "em.mdp test grompp failed: $(echo "$out" | grep -m1 -A2 'Fatal error' | tr '\n' ' ' | cut -c1-120)"
fi

# --- (2) cutoffs < 1/2 min(box) -------------------------------------------------
# 2026.3: rcutoff split into rvdw + rcoulomb; accept legacy rcutoff too.
cuts=""
for key in rvdw rcoulomb rcutoff; do
  v="$(sed -n "s/^[[:space:]]*$key[[:space:]]*=[[:space:]]*\([0-9.]*\).*/\1/p" "$MDP" | head -1)"
  [ -n "$v" ] && cuts="$cuts $v"
done
box="$(tail -1 "$GRO")"
min_half="$(echo "$box" | awk '{m=$1< $2?$1:$2; m=$3<m?$3:m; printf "%.4f", m/2}')"
if [ -n "$cuts" ] && echo "$cuts" | tr ' ' '\n' | grep -E '^[0-9]' | awk -v m="$min_half" '{if($1>=m)bad++} END{exit bad+0}'; then
  pass cutoff "cutoffs($(echo $cuts | tr ' ' '/')) < 1/2 min(box)=$min_half"
else
  failc cutoff "cutoffs(${cuts:-?}) not all < 1/2 min(box)=$min_half (box: $box)"
fi

# --- (3) net charge integer and ~0 (via grompp warnings) -------------------------
if echo "$out" | grep -qE "non-zero total charge|Total charge should normally be an integer"; then
  failc net_charge "grompp reports non-integer/non-zero net charge: $(echo "$out" | grep -m1 -A1 'total charge' | tr '\n' ' ' | cut -c1-100)"
else
  pass net_charge "grompp reports no net-charge problem"
fi

# --- (4) ion counts > 0 ----------------------------------------------------------
ions="$(sed -n '/^\[ molecules \]/,$p' "$TOP" | awk 'NF && $1 !~ /^[;#]/ && $1 !~ /^SOL/ && $1 !~ /^Protein/ && $1 !~ /^WAT/ {n+=$2} END{print n+0}')"
if [ "$ions" -gt 0 ]; then
  pass ions "$ions ion molecules in [ molecules ]"
else
  failc ions "no ion molecules in [ molecules ] (run genion -neutral)"
fi

# --- (5) [ molecules ] structural sanity -----------------------------------------
mol_lines="$(sed -n '/^\[ molecules \]/,$p' "$TOP" | grep -cE '^[A-Za-z]')"
gro_n="$(sed -n '2p' "$GRO" | awk '{print $1}')"
if [ "$mol_lines" -ge 2 ] && [ "$gro_n" -gt 0 ]; then
  pass molecules "[ molecules ] has $mol_lines entries; gro has $gro_n atoms (consistency proven by grompp)"
else
  failc molecules "[ molecules ] has $mol_lines entries (gro: $gro_n atoms)"
fi

exit "$fail"
