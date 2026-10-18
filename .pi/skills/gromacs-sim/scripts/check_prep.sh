#!/usr/bin/env bash
# check_prep.sh — phase-1 (prep) gate.
#
# Usage: check_prep.sh <sim_dir>
# Expects: input/*.pdb, 01_prep/{protein.gro,protein.top,pdb2gmx.log,posre.itp}
#          (topology may be named topol.top — first *.top in 01_prep/ wins)
# Checks:  pdb2gmx exit 0 (log); no missing/WARNING: atom lines; cumulative
#          charge integer at every residue (parse .top); atom count consistent
#          between .gro and .top [ atoms ]; posre.itp present.
# Exit:   0 pass, 1 fail, 2 environment error.
set -euo pipefail

SIM="${1:?usage: $0 <sim_dir>}"
PREP="$SIM/01_prep"
fail=0
pass() { echo "PASS|$1|$2"; }
failc() { echo "FAIL|$1|$2"; fail=1; }
env() { echo "ENV|$1|$2"; exit 2; }

[ -d "$PREP" ] || env prep "01_prep/ missing in $SIM"
TOP="$(find "$PREP" -maxdepth 1 -name '*.top' | head -1)"
GRO="$PREP/protein.gro"
[ -n "$TOP" ] || env top "no .top in $PREP"
[ -f "$GRO" ] || env gro "missing $GRO"

# --- pdb2gmx log: exit 0, no missing atoms -----------------------------------
LOG="$PREP/pdb2gmx.log"
[ -f "$LOG" ] || LOG="$SIM/pdb2gmx.log"   # fall back to project root (I-3)
if [ -f "$LOG" ]; then
  if grep -qiE "missing residue|WARNING: atom|cannot find" "$LOG"; then
    failc pdb2gmx_log "missing-atom/warning lines: $(grep -icE 'missing residue|WARNING: atom|cannot find' "$LOG")"
  else
    pass pdb2gmx_log "no missing-atom/warning lines"
  fi
  if grep -q "Fatal error" "$LOG"; then
    failc pdb2gmx_exit "Fatal error in pdb2gmx.log"
  else
    pass pdb2gmx_exit "no fatal error in log"
  fi
else
  failc pdb2gmx_log "pdb2gmx.log missing (save the log: > 01_prep/pdb2gmx.log 2>&1)"
fi

# --- cumulative charge integer at every residue -------------------------------
# NOTE 2026.3: pdb2gmx output has no [ moleculetype ] / [ atoms ] section
# headers — the atom block sits between the name line and [ bonds ]. Parse
# by content: numeric atom nr, >=7 fields, numeric charge (column 7).
charge_report="$(awk '
  $1 ~ /^[0-9]+$/ && NF >= 7 && $7 ~ /^-?[0-9]/ {
    key = $3 "-" $4
    q[key] += $7
    n[key]++
  }
  END {
    bad = 0
    for (k in q) {
      r = int(q[k] + (q[k] < 0 ? -0.5 : 0.5))
      if (q[k] - r > 0.001 || r - q[k] > 0.001) {
        printf "residue %s charge %.4f\n", k, q[k]
        bad++
      }
    }
    if (bad == 0) print "OK"
    else print "BAD " bad
  }' "$TOP")"
case "$charge_report" in
  OK) pass residue_charge "all residues integer-charged" ;;
  BAD*) failc residue_charge "$charge_report" ;;
  *) failc residue_charge "non-integer residue charges: $charge_report" ;;
esac

# --- atom count: .gro line 2 == .top [ atoms ] rows ---------------------------
gro_n="$(sed -n '2p' "$GRO" | awk '{print $1}')"
top_n="$(awk '$1 ~ /^[0-9]+$/ && NF >= 7 && $7 ~ /^-?[0-9]/{n++} END{print n+0}' "$TOP")"
if [ "$gro_n" = "$top_n" ] && [ "$gro_n" -gt 0 ]; then
  pass atom_count "gro=$gro_n == top=$top_n"
else
  failc atom_count "gro=$gro_n != top=$top_n"
fi

# --- posre.itp present ---------------------------------------------------------
if [ -f "$PREP/posre.itp" ] && [ -s "$PREP/posre.itp" ]; then
  pass posre "posre.itp present ($(wc -l < "$PREP/posre.itp") lines)"
else
  failc posre "posre.itp missing or empty"
fi

exit "$fail"
