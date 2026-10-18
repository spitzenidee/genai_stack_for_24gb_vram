#!/usr/bin/env bash
# check_equil.sh — phase-5 (equilibration) gate.
#
# Usage: check_equil.sh <sim_dir> [nvt|npt]   (default: npt)
# Expects: 05_equil/<run>.edr + <run>.mdp (run = nvt or npt)
# Checks:  last-20% mean T within ±5 K of ref; last-20% mean P within ±15 bar
#          of ref (NPT only); density STABLE over last 20% (std < 1% of mean)
#          inside a loose 950-1050 kg/m3 band; no energy spike > 3x median in
#          last 10%.
# P/density criteria per KB 01.5: pressure is a wildly fluctuating microscopic
# quantity (an average of -3 ± 11 bar vs target 1 bar is statistically
# indistinguishable — do NOT chase the exact value), and a solvated protein+ion
# density runs slightly ABOVE bulk water (repo: 1025 ± 0.5 vs 986 for TIP3P);
# a constant density over the NPT phase ⇒ adequately equilibrated. The old
# ±30%-of-ref / 2%-of-997 criteria contradicted the KB and caused a 43-min
# NPT-extension dead end (issues_agent_run, lysozym 2026-09-25).
# Runs gmx energy in a transient container (any stack mode).
# Exit:   0 pass, 1 fail, 2 environment error.
set -euo pipefail

SIM="$(realpath "${1:?usage: $0 <sim_dir>}")"
RUN="${2:-npt}"
EQ="$SIM/05_equil"
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STACK_ROOT="$(cd "$SKILL_DIR/../../.." && pwd)"
IMAGE="gromacs-hip-gfx1100:latest"
fail=0
pass() { echo "PASS|$1|$2"; }
failc() { echo "FAIL|$1|$2"; fail=1; }
env() { echo "ENV|$1|$2"; exit 2; }

[ -d "$EQ" ] || env equil "05_equil/ missing in $SIM"
EDR="$EQ/$RUN.edr"
MDP="$EQ/$RUN.mdp"
[ -f "$EDR" ] || env edr "missing $EDR"
[ -f "$MDP" ] || env mdp "missing $MDP"

# --- GPU-offload gate (phases 5-6 must run on GPU, not CPU) -------------------
# A CPU mdrun log contains "GPU detection failed"; a GPU run does not. This stops
# a silently-CPU equilibration from passing the phase-5 gate (issues_agent_run G3).
LOG="$EQ/$RUN.log"
if [ -f "$LOG" ]; then
  if grep -q "GPU detection failed" "$LOG"; then
    failc gpu "no GPU offload: '$RUN.log' shows 'GPU detection failed' (CPU run); phases 5-6 require GPU"
  else
    pass gpu "GPU offload: no 'GPU detection failed' in $RUN.log"
  fi
else
  failc gpu "missing $LOG (cannot verify GPU offload)"
fi

case "$SIM" in
  "$STACK_ROOT"/gromacs/work/*) CPATH="/work/${SIM#$STACK_ROOT/gromacs/work/}" ;;
  *) env mount "sim dir not under $STACK_ROOT/gromacs/work: $SIM" ;;
esac

ref_t="$(sed -n -E 's/^[[:space:]]*ref(-t)?[[:space:]]*=[[:space:]]*([0-9.]+).*/\2/p' "$MDP" | head -1)"
ref_p="$(sed -n -E 's/^[[:space:]]*ref(-p)?[[:space:]]*=[[:space:]]*([0-9.]+).*/\2/p' "$MDP" | head -1)"

# --- gmx energy: discover term numbers, then extract series --------------------
# Stage 1: run with /dev/null stdin; the numbered term list is printed before
# the selection prompt aborts.
list="$(docker run --rm -w "$CPATH/05_equil" -v "$STACK_ROOT/gromacs/work":/work \
  "$IMAGE" gmx energy -f "$RUN.edr" < /dev/null 2>&1 || true)"
# 2026.3 energy list is multi-term per line with no colons (e.g. "14  Temperature"),
# so the term number is discovered by an unanchored match, not a line anchor.
# `|| true`: a legitimately-absent term (e.g. Density in an NVT .edr) must not
# trip set -e on the assignment n_x="$(num ...)".
num() { echo "$list" | grep -oE "[0-9]+[[:space:]]+$1" | head -1 | grep -oE '^[0-9]+' || true; }
n_t="$(num 'Temperature')"
n_p="$(num 'Pressure')"
n_d="$(num 'Density')"
n_e="$(num 'Total-Energy')"
[ -n "$n_t" ] || env energy "could not find Temperature term in energy list"
# No trailing 'q': gmx energy terminates on EOF, and a stray 'q' in $sel would
# shift every col_of() index by one (it sorts to the front under sort -un).
sel="$(printf '%s\n%s\n%s\n%s\n' "${n_t:-0}" "${n_p:-0}" "${n_d:-0}" "${n_e:-0}" | awk '$0!="0"' | sort -un)"

# Stage 2: real run; outputs one .xvg per selected term (order = selection).
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
docker run --rm -w "$CPATH/05_equil" -v "$STACK_ROOT/gromacs/work":/work \
  -v "$work":/gate "$IMAGE" bash -c "echo '$sel' | gmx energy -f $RUN.edr -o /gate/eq.xvg" > "$work/run.log" 2>&1 \
  || { env energy "gmx energy failed: $(tail -3 "$work/run.log" | tr '\n' ' ')"; }

# .xvg columns: time, then one column per selected term (in selection order)
col_of() { # $1 = term number -> column index in xvg (data col = position + 1)
  awk -v n="$1" -v s="$sel" 'BEGIN{m=split(s, a, " "); for(i=1;i<=m;i++) if(a[i]==n){print i+1; exit}}'
}
series() { # $1 = column index -> "time value" lines
  awk '$1!="" && $1!~/^@/ && $1!~/^#/' "$work/eq.xvg" | awk -v c="$1" '{print $1, $c}'
}
last20() { # stdin "time value" -> mean of last 20%
  awk '{t[NR]=$1; v[NR]=$2} END{if(NR<5){print "NA"; exit} s=0; n=0; for(i=int(NR*0.8)+1;i<=NR;i++){s+=v[i];n++} printf "%.3f", s/n}'
}
last20_std() { # stdin "time value" -> std dev of last 20%
  awk '{t[NR]=$1; v[NR]=$2} END{if(NR<5){print "NA"; exit}
    s=0; n=0; for(i=int(NR*0.8)+1;i<=NR;i++){s+=v[i];n++}
    m=s/n; ss=0; for(i=int(NR*0.8)+1;i<=NR;i++){d=v[i]-m; ss+=d*d}
    printf "%.3f", sqrt(ss/n)}'
}
last10_median() { # stdin "time value" -> median of last 10%
  awk '{v[NR]=$2} END{
    n=0; for(i=int(NR*0.9)+1;i<=NR;i++){a[++n]=v[i]}
    if(n==0){print "NA"; exit}
    for(i=1;i<n;i++)for(j=i+1;j<=n;j++)if(a[i]>a[j]){t=a[i];a[i]=a[j];a[j]=t}
    printf "%.3f", a[int((n+1)/2)]}'
}

t_series="$(series "$(col_of "$n_t")")"
t_mean="$(echo "$t_series" | last20)"
if [ "$t_mean" != "NA" ] && [ -n "$ref_t" ] && awk -v a="$t_mean" -v b="$ref_t" 'BEGIN{d=a-b; if(d<0)d=-d; exit !(d<=5)}'; then
  pass temp "last-20% mean T=$t_mean K within ±5 K of ref $ref_t"
else
  failc temp "last-20% mean T=${t_mean:-?} K vs ref ${ref_t:-?} (±5 K)"
fi

if [ "$RUN" = "npt" ]; then
  p_series="$(series "$(col_of "$n_p")")"
  p_mean="$(echo "$p_series" | last20)"
  # KB 01.5: absolute ±15 bar band (not relative %). Pressure is noisy;
  # chasing the exact ref value is explicitly discouraged.
  if [ "$p_mean" != "NA" ] && [ -n "$ref_p" ] && awk -v a="$p_mean" -v b="$ref_p" 'BEGIN{d=a-b; if(d<0)d=-d; exit !(d<=15)}'; then
    pass pres "last-20% mean P=$p_mean bar within ±15 bar of ref $ref_p (KB 01.5: noisy; do not chase exact value)"
  else
    failc pres "last-20% mean P=${p_mean:-?} bar > 15 bar from ref ${ref_p:-?} (KB 01.5 band)"
  fi
fi

if [ -n "$n_d" ]; then
  d_series="$(series "$(col_of "$n_d")")"
  d_mean="$(echo "$d_series" | last20)"
  d_std="$(echo "$d_series" | last20_std)"
  # gmx energy reports Density in kg/m3 (~997 for pure water). A solvated
  # protein+ion system runs slightly above bulk water (KB 01.5: repo 1025±0.5
  # for TIP3P), so gate on STABILITY (std < 1% of mean, last 20%) plus a loose
  # absolute band 950-1050 kg/m3 — not closeness to 997. Constant density ⇒
  # adequately equilibrated (KB 01.5).
  if [ "$d_mean" != "NA" ] && [ "$d_std" != "NA" ] && awk -v a="$d_mean" -v s="$d_std" 'BEGIN{exit !((a>=950 && a<=1050) && (s < 0.01*a))}'; then
    pass density "last-20% density=$d_mean±$d_std kg/m3 stable (band 950-1050, std<1%; KB 01.5)"
  else
    failc density "last-20% density=${d_mean:-?}±${d_std:-?} kg/m3 not stable (need 950-1050 & std<1%; KB 01.5)"
  fi
fi

# --- no energy spike > 3x median in last 10% ------------------------------------
if [ -n "$n_e" ]; then
  e_series="$(series "$(col_of "$n_e")")"
  med="$(echo "$e_series" | last10_median)"
  spike="$(echo "$e_series" | awk -v m="$med" 'NR>0{v=$2; if(v<0)v=-v; if(mv==""||v>mv)mv=v} END{printf "%.3f", mv}')"
  # Total energy is negative; compare max |E| against 3x |median| (not 3x median).
  if [ "$med" != "NA" ] && awk -v s="$spike" -v m="$med" 'BEGIN{am=m; if(am<0)am=-am; exit !(s <= 3*am)}'; then
    pass stability "max |E| in last 10% = $spike <= 3x |median| ($med)"
  else
    failc stability "energy spike: max |E|=$spike > 3x |median| ($med) in last 10%"
  fi
fi

exit "$fail"
