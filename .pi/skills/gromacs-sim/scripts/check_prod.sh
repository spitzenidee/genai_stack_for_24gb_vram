#!/usr/bin/env bash
# check_prod.sh — phase-6 (production) gate.
#
# Usage: check_prod.sh <sim_dir>
# Expects: 06_production/{md.log, md.xtc, state.cpt, md.mdp}
# Checks:  final step in log == nsteps; no constraint/range-check warnings;
#          checkpoint present; total-energy drift sanity (first-10% vs
#          last-10% mean < 5% apart, via gmx energy); xtc frame count ==
#          expected (from state.json prod_time_ps + mdp dt/nstxout).
# Exit:   0 pass, 1 fail, 2 environment error.
set -euo pipefail

SIM="$(realpath "${1:?usage: $0 <sim_dir>}")"
PROD="$SIM/06_production"
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STACK_ROOT="$(cd "$SKILL_DIR/../../.." && pwd)"
IMAGE="gromacs-hip-gfx1100:latest"
fail=0
pass() { echo "PASS|$1|$2"; }
failc() { echo "FAIL|$1|$2"; fail=1; }
env() { echo "ENV|$1|$2"; exit 2; }

[ -d "$PROD" ] || env prod "06_production/ missing in $SIM"
LOG="$PROD/md.log"
MDP="$PROD/md.mdp"
[ -f "$LOG" ] || env log "missing $LOG"
[ -f "$MDP" ] || env mdp "missing $MDP"

# --- container path (needed by gmx dump below and later checks) ----------------
case "$SIM" in
  "$STACK_ROOT"/gromacs/work/*) CPATH="/work/${SIM#$STACK_ROOT/gromacs/work/}" ;;
  *) env mount "sim dir not under $STACK_ROOT/gromacs/work: $SIM" ;;
esac

# --- final step == nsteps (read from the .tpr that actually ran) -----------------
# The .tpr is the artifact mdrun consumed; reading nsteps from it (not the MDP)
# catches a stale .tpr (MDP edited, grompp not re-run). gmx dump 2026.3 prints
# indented "nsteps = N" inside the inputrec: section (see 01.7).
TPR="$PROD/md.tpr"
[ -f "$TPR" ] || env tpr "missing $TPR"
dump_out="$(docker run --rm -w "$CPATH/06_production" -v "$STACK_ROOT/gromacs/work":/work \
  "$IMAGE" gmx dump -s md.tpr 2>&1 || true)"
nsteps="$(echo "$dump_out" | grep -E '^[[:space:]]*nsteps[[:space:]]*=' | head -1 | grep -oE '[0-9]+' | head -1)"
mdp_nsteps="$(sed -n 's/^[[:space:]]*nsteps[[:space:]]*=[[:space:]]*\([0-9]*\).*/\1/p' "$MDP" | head -1)"
if [ -n "$mdp_nsteps" ] && [ -n "$nsteps" ] && [ "$nsteps" != "$mdp_nsteps" ]; then
  failc tpr_fresh "md.tpr nsteps $nsteps != md.mdp nsteps $mdp_nsteps (stale .tpr?)"
else
  pass tpr_fresh "md.tpr nsteps ${nsteps:-?} matches md.mdp ${mdp_nsteps:-?}"
fi
last="$(grep -E '^[[:space:]]+[0-9]+[[:space:]]' "$LOG" | tail -1 | awk '{print $1}')"
if [ -n "$nsteps" ] && [ "$last" = "$nsteps" ]; then
  pass completion "final step $last == nsteps $nsteps (from md.tpr)"
else
  failc completion "final step ${last:-?} != nsteps ${nsteps:-?}"
fi

# --- no constraint / range-check warnings ----------------------------------------
# Only real warnings: bare "constraint" is too broad — it matches benign
# mdrun info lines (constraint-algorithm, LINCS solver banner, constraint RMSD,
# timing rows), so it is deliberately excluded here (issues I-5).
if grep -qiE "lincs warning|range check|exceeded" "$LOG"; then
  failc log_clean "warning lines: $(grep -icE 'lincs warning|range check|exceeded' "$LOG")"
else
  pass log_clean "no constraint/range-check warnings"
fi

# --- checkpoint present -------------------------------------------------------------
# 2026.3 names the checkpoint <deffnm>.cpt (md.cpt), not state.cpt (issues I-6).
cpt=""
for c in "$PROD/md.cpt" "$PROD/state.cpt"; do
  [ -s "$c" ] && { cpt="$c"; break; }
done
if [ -n "$cpt" ]; then
  pass checkpoint "$(basename "$cpt") present ($(du -h "$cpt" | cut -f1))"
else
  failc checkpoint "checkpoint missing or empty (md.cpt/state.cpt)"
fi

# --- xtc frame count == expected ------------------------------------------------------
xtc="$PROD/md.xtc"
[ -f "$xtc" ] || env xtc "missing $xtc"
check_out="$(docker run --rm -w "$CPATH/06_production" -v "$STACK_ROOT/gromacs/work":/work \
  "$IMAGE" gmx check -f md.xtc 2>&1 || true)"
# 2026.3 gmx check prints a summary table ("Time  5001  2"), not "Number of frames: N".
frames="$(echo "$check_out" | grep -oE 'Number of frames: [0-9]+' | grep -oE '[0-9]+' || true)"
[ -z "$frames" ] && frames="$(echo "$check_out" | grep -E '^Time[[:space:]]+[0-9]+' | awk '{print $2}' | head -1)"
dt_ps="$(sed -n 's/^[[:space:]]*dt[[:space:]]*=[[:space:]]*\([0-9.]*\).*/\1/p' "$MDP" | head -1)"
# xtc cadence: nstxout, or nstxout-compressed when the run writes compressed xtc.
nstxout="$(sed -n 's/^[[:space:]]*nstxout[[:space:]]*=[[:space:]]*\([0-9]*\).*/\1/p' "$MDP" | head -1)"
[ -z "$nstxout" ] && nstxout="$(sed -n 's/^[[:space:]]*nstxout-compressed[[:space:]]*=[[:space:]]*\([0-9]*\).*/\1/p' "$MDP" | head -1)"
prod_ps="$(sed -n 's/.*"prod_time_ps"[[:space:]]*:[[:space:]]*\([0-9.]*\).*/\1/p' "$SIM/state.json" 2>/dev/null | head -1)"
if [ -n "$frames" ] && [ -n "$dt_ps" ] && [ -n "$nstxout" ] && [ -n "$prod_ps" ]; then
  # frames = prod_time_ps / (dt_ps * nstxout_steps)  [the xtc cadence in ps]
  expected="$(awk -v p="$prod_ps" -v d="$dt_ps" -v n="$nstxout" 'BEGIN{printf "%d", p/(d*n)}')"
  # mdrun writes floor + final frame; allow ±1
  if [ "$frames" -ge "$((expected-1))" ] && [ "$frames" -le "$((expected+1))" ]; then
    pass xtc_frames "frames=$frames == expected $expected (±1)"
  else
    failc xtc_frames "frames=$frames != expected $expected (±1)"
  fi
else
  failc xtc_frames "cannot compute expected frames (frames=${frames:-?} dt=${dt_ps:-?} nstxout=${nstxout:-?} prod_ps=${prod_ps:-?})"
fi

# --- drift sanity: total energy first-10% vs last-10% mean < 5% apart ---------------
edr="$PROD/md.edr"
if [ -f "$edr" ]; then
  work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
  list="$(docker run --rm -w "$CPATH/06_production" -v "$STACK_ROOT/gromacs/work":/work \
    "$IMAGE" gmx energy -f md.edr < /dev/null 2>&1 || true)"
  # 2026.3: multi-term-per-line list, no colons, term is "Total-Energy".
  n_e="$(echo "$list" | grep -oE '[0-9]+[[:space:]]+Total-Energy' | head -1 | grep -oE '^[0-9]+')"
  if [ -n "$n_e" ]; then
    docker run --rm -w "$CPATH/06_production" -v "$STACK_ROOT/gromacs/work":/work \
      -v "$work":/gate "$IMAGE" bash -c "echo '$n_e' | gmx energy -f md.edr -o /gate/e.xvg" > "$work/run.log" 2>&1 \
      || failc drift "gmx energy failed: $(tail -2 "$work/run.log" | tr '\n' ' ')"
    drift="$(awk '$1!="" && $1!~ /^@/ && $1!~/^#/{dp++;v[dp]=$2}
      END{
        if(dp<10){print "NA"; exit}
        s1=0;n1=0; for(i=1;i<=int(dp*0.1);i++){s1+=v[i];n1++}
        s2=0;n2=0; for(i=int(dp*0.9)+1;i<=dp;i++){s2+=v[i];n2++}
        m1=s1/n1; m2=s2/n2; d=(m2-m1)/m1; if(d<0)d=-d
        printf "%.4f", d}' "$work/e.xvg")"
    if [ "$drift" != "NA" ] && awk -v d="$drift" 'BEGIN{exit !(d < 0.05)}'; then
      pass drift "total-energy drift ${drift} (first-10% vs last-10% mean) < 5%"
    else
      failc drift "total-energy drift ${drift:-?} >= 5%"
    fi
  else
    failc drift "Total Energy term not found in energy list"
  fi
else
  failc drift "md.edr missing"
fi

exit "$fail"
