#!/usr/bin/env bash
# render_mdp.sh — render an MDP asset template with REF_T/REF_P from state.json.
#
# Eliminates the "forgot to set REF_T/REF_P in this bash invocation" class of
# bugs (POST_SIM_RCA issue 8): the values are ALWAYS read from state.json
# internally — never from the caller's shell environment.
#
# Usage: render_mdp.sh <asset.mdp> <state.json> <nsteps> <out.mdp>
#   asset.mdp  = skill asset template with <<<KEY:default>>> placeholders
#   state.json = sim state file (ref_t/ref_p required when the template
#                carries <<<REF_T:>>>/<<<REF_P:>>> — Tier A)
#   nsteps     = nsteps to render (Tier B plan)
#   out.mdp    = output path
# Output: PASS|render|<out.mdp> (ref_t=... ref_p=... nsteps=...)
# Exit:   0 ok, 1 state.json incomplete / rendered file wrong, 2 environment.
set -euo pipefail

ASSET="${1:?usage: $0 <asset.mdp> <state.json> <nsteps> <out.mdp>}"
STATE="${2:?usage: $0 <asset.mdp> <state.json> <nsteps> <out.mdp>}"
NSTEPS="${3:?usage: $0 <asset.mdp> <state.json> <nsteps> <out.mdp>}"
OUT="${4:?usage: $0 <asset.mdp> <state.json> <nsteps> <out.mdp>}"

[ -f "$ASSET" ] || { echo "ENV|asset|missing template: $ASSET"; exit 2; }
[ -f "$STATE" ] || { echo "ENV|state|missing state.json: $STATE"; exit 2; }
case "$NSTEPS" in ''|*[!0-9]*) echo "ENV|nsteps|not a non-negative integer: $NSTEPS"; exit 2;; esac
command -v jq >/dev/null 2>&1 || { echo "ENV|jq|jq not found on host"; exit 2; }

# Which placeholders does THIS template carry? (em/cg: nsteps only; nvt: +ref_t;
# npt/md: +ref_p; ions: none.)
NEEDS_T=0; grep -q '<<<REF_T:' "$ASSET" && NEEDS_T=1
NEEDS_P=0; grep -q '<<<REF_P:' "$ASSET" && NEEDS_P=1
NEEDS_N=0; grep -q '<<<NSTEPS:' "$ASSET" && NEEDS_N=1

# Tier A: REF_T/REF_P from state.json, always (the asset's 300 K / 1.0 bar
# are placeholders, NOT the plan).
REF_T=""; REF_P=""
if [ "$NEEDS_T" = 1 ]; then
  REF_T="$(jq -r '.ref_t // empty' "$STATE")"
  [ -n "$REF_T" ] || { echo "FAIL|ref_t|state.json missing ref_t (Tier A)"; exit 1; }
fi
if [ "$NEEDS_P" = 1 ]; then
  REF_P="$(jq -r '.ref_p // empty' "$STATE")"
  [ -n "$REF_P" ] || { echo "FAIL|ref_p|state.json missing ref_p (Tier A)"; exit 1; }
fi

sed -E "s/<<<REF_T:[^>]*>>>/${REF_T:-}/g; s/<<<REF_P:[^>]*>>>/${REF_P:-}/g; \
        s/<<<NSTEPS:[^>]*>>>/$(printf '%s' "$NSTEPS")/g; s/<<<[A-Za-z0-9_]+:([^>]*)>>>/\1/g" \
  "$ASSET" > "$OUT"

# Self-check: the rendered file must carry the state.json values (not the
# template defaults) and no unrendered placeholders.
if [ "$NEEDS_T" = 1 ]; then
  grep -qE "^ref-t[[:space:]]*=[[:space:]]*$REF_T([[:space:]]|$)" "$OUT" \
    || { echo "FAIL|ref_t|rendered MDP ref-t != $REF_T"; exit 1; }
fi
if [ "$NEEDS_P" = 1 ]; then
  grep -qE "^ref-p[[:space:]]*=[[:space:]]*$REF_P([[:space:]]|$)" "$OUT" \
    || { echo "FAIL|ref_p|rendered MDP ref-p != $REF_P"; exit 1; }
fi
if [ "$NEEDS_N" = 1 ]; then
  grep -qE "^nsteps[[:space:]]*=[[:space:]]*$NSTEPS([[:space:]]|$)" "$OUT" \
    || { echo "FAIL|nsteps|rendered MDP nsteps != $NSTEPS"; exit 1; }
fi
if grep -q '<<<' "$OUT"; then
  echo "FAIL|placeholder|unrendered <<<...>>> remains in $OUT"; exit 1
fi

echo "PASS|render|$OUT (ref_t=${REF_T:-n/a} ref_p=${REF_P:-n/a} nsteps=$NSTEPS)"
