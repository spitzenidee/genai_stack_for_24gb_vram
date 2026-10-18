#!/usr/bin/env bash
# check_templates.sh — drift check: assets/*.mdp vs KB 03.2 (D13, R2)
#
# Single source of truth = knowledge/03-playbooks/03.2-mdp-templates.md (this skill's KB)
# assets/ = derived executable copies with <<<KEY:default>>> placeholders.
#
# Usage: check_templates.sh [sim_dir]
#   sim_dir optional: when given with a state.json, also verifies the
#   rendered REF_T/REF_P assets match state.json (Tier A, RCA issue 10).
# Output: one PASS|FAIL|<detail> line per template.
# Exit:   0 = in sync, 1 = drift, 2 = environment error.
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ASSETS="$SKILL_DIR/assets"
KB="$SKILL_DIR/knowledge/03-playbooks/03.2-mdp-templates.md"

[ -f "$KB" ] || { echo "FAIL|kb|KB 03.2 not found: $KB"; exit 2; }
[ -d "$ASSETS" ] || { echo "FAIL|assets|assets dir not found: $ASSETS"; exit 2; }

# Extract the first ```ini block of KB section N (headings: "## 1. ...", "## 2. ...")
extract_kb_block() {
  local n="$1"
  awk -v n="$n" '
    $0 ~ "^## " n "\\." { insec = 1; next }
    insec && /^## /     { exit }
    insec && /^```ini/  { inblock = 1; next }
    inblock && /^```/   { exit }
    inblock             { print }
  ' "$KB"
}

# Render placeholders to their defaults, strip comments, trim, drop blank lines
normalize() {
  sed -E 's/<<<[A-Za-z0-9_]+:([^>]*)>>>/\1/g' \
    | sed -E 's/;.*$//' \
    | sed -E 's/[[:space:]]+$//' \
    | grep -v '^[[:space:]]*$' || true
}

rc=0
# $1 = asset name, $2 = KB block number, $3 = optional sed script applied to the
# KB block before comparison (cg.mdp = em block with integrator swapped, D10)
check() {
  local name="$1" kb_block="$2" sed_script="${3:-s/^$//}"
  local a b
  a="$(normalize < "$ASSETS/$name")"
  b="$(extract_kb_block "$kb_block" | sed -E "$sed_script" | normalize)"
  if [ "$a" = "$b" ]; then
    echo "PASS|$name|in sync with KB 03.2 block $kb_block"
  else
    echo "FAIL|$name|drift vs KB 03.2 block $kb_block:"
    diff <(echo "$b") <(echo "$a") | sed 's/^/    /' || true
    rc=1
  fi
}

check "em.mdp"  1
check "cg.mdp"  1 's/^(integrator[[:space:]]*=[[:space:]]*)steep/\1cg/'
check "nvt.mdp" 2
check "npt.mdp" 3
check "md.mdp"  4

# --- rendered MDP vs state.json (Tier A, RCA issue 10) ----------------------------
# When a sim_dir with state.json is given, render the REF_T/REF_P-carrying
# assets through render_mdp.sh and verify the rendered values match state.json
# (not the template defaults). A run rendered with the 300 K default while
# state.json says 310 K is a Tier A violation (lysozym 2026-09-25, F1).
SIM="${1:-}"
if [ -n "$SIM" ] && [ -f "$SIM/state.json" ]; then
  rwork="$(mktemp -d)"
  for name in nvt npt md; do
    if "$SKILL_DIR/scripts/render_mdp.sh" "$ASSETS/$name.mdp" "$SIM/state.json" 1 \
        "$rwork/$name.mdp" > "$rwork/$name.log" 2>&1; then
      echo "PASS|rendered_$name|ref_t/ref_p match state.json"
    else
      echo "FAIL|rendered_$name|render vs state.json failed: $(tail -1 "$rwork/$name.log")"
      rc=1
    fi
  done
  rm -rf "$rwork"
else
  echo "SKIP|rendered|no sim_dir/state.json; skipping rendered-MDP vs state.json check"
fi

# --- grompp smoke test (G4): render each asset, grompp vs protein+water -------
# Catches bugs the drift check cannot (both asset and KB share the same bug, e.g.
# the T-coupling count mismatch, I-85). Needs a system with BOTH Protein and
# Non-Protein groups so the T-coupling count check fires. Uses the kb-audit probe
# asset when present; skips (not fails) if the probe or image is unavailable.
IMAGE="gromacs-hip-gfx1100:latest"
PROBE_GRO="$SKILL_DIR/../gromacs-kb-audit/assets/probe.gro"
PROBE_TOP="$SKILL_DIR/../gromacs-kb-audit/assets/probe.top"
if [ -f "$PROBE_GRO" ] && [ -f "$PROBE_TOP" ] && docker image inspect "$IMAGE" >/dev/null 2>&1; then
  work="$(mktemp -d)"
  trap 'rm -rf "$work"' EXIT
  cp "$PROBE_GRO" "$work/probe.gro"; cp "$PROBE_TOP" "$work/probe.top"
  for name in em cg nvt npt md; do
    sed -E 's/<<<[A-Za-z0-9_]+:([^>]*)>>>/\1/g' "$ASSETS/$name.mdp" > "$work/$name.mdp"
    if docker run --rm -w /w -v "$work":/w "$IMAGE" \
        gmx grompp -f "$name.mdp" -c probe.gro -p probe.top -o /dev/null -maxwarn 5 >/dev/null 2>&1; then
      echo "PASS|smoke_$name|grompp OK vs protein+water"
    else
      echo "FAIL|smoke_$name|grompp failed vs protein+water:"
      docker run --rm -w /w -v "$work":/w "$IMAGE" \
        gmx grompp -f "$name.mdp" -c probe.gro -p probe.top -o /dev/null -maxwarn 5 2>&1 \
        | grep -iE 'Fatal|ERROR|Invalid' | head -2 | sed 's/^/    /'
      rc=1
    fi
  done
else
  echo "SKIP|smoke|no probe asset ($PROBE_GRO) or image; skipping grompp smoke test"
fi

# --- 2026.3 analysis interface check (RCA cross-cutting #1: catch gmx CLI drift) ---
# analyze.sh depends on 2026.3-specific flags/extensions: dssp -o .dat,
# hbond -o .ndx, msd -trestart (no -com), trjconv -pbc nojump. A build
# upgrade that renames/removes them breaks phase 7 silently — verify against
# the live image (-h only, cheap).
if docker image inspect "$IMAGE" >/dev/null 2>&1; then
  h_dssp="$(docker run --rm "$IMAGE" gmx dssp -h 2>&1 || true)"
  h_hbond="$(docker run --rm "$IMAGE" gmx hbond -h 2>&1 || true)"
  h_msd="$(docker run --rm "$IMAGE" gmx msd -h 2>&1 || true)"
  h_trj="$(docker run --rm "$IMAGE" gmx trjconv -h 2>&1 || true)"
  if echo "$h_dssp" | grep -q -- '-o[[:space:]]*\[<\.dat>\]' && \
     echo "$h_hbond" | grep -q -- '-o[[:space:]]*\[<\.ndx>\]' && \
     echo "$h_msd" | grep -q -- '-trestart' && \
     ! echo "$h_msd" | grep -qE '(^|[[:space:]])-com([[:space:]]|$)' && \
     echo "$h_trj" | grep -q 'nojump'; then
    echo "PASS|iface_2026_3|dssp .dat / hbond .ndx / msd -trestart (no -com) / trjconv nojump"
  else
    echo "FAIL|iface_2026_3|analysis interface drift vs 2026.3 — re-verify dssp/hbond/msd/trjconv -h before phase 7"
    rc=1
  fi
else
  echo "SKIP|iface_2026_3|no image; skipping analysis interface check"
fi

exit "$rc"
