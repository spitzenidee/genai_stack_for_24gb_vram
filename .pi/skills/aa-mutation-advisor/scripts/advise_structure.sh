#!/usr/bin/env bash
#
# advise_structure.sh — structure-aware AA substitution advisor (wrapper).
#
# Orchestrates, on the HOST (standard bash + coreutils only), two transient
# `docker run --rm` containers:
#   1. gromacs-hip-gfx1100 : `gmx dssp` (CPU-only, no GPU)  -> .dat
#   2. md-prep:latest      : python3 advise.py (reads data + PDB + .dat)
#
# Guarantees:
#   - NO `make gromacs` / work-mode switch (never calls switch-mode.sh / compose up)
#   - NO `docker build` / `docker pull` (only `docker run --rm` on existing images)
#   - NO GPU devices, NO service disruption (llamacpp-egpu / open-webui keep running)
#   - All intermediates live in a `mktemp -d` dir, removed on exit (trap)
#
# Secondary structure is assigned CONSERVATIVELY inside advise.py: a residue is
# treated as helix/strand if EITHER the PDB's HELIX/SHEET records OR the DSSP
# .dat says so (the two sources genuinely disagree; over-warning is cheaper than
# missing a helix/strand breaker). The output shows the per-residue basis.
#
# Usage: advise_structure.sh <pdb> <residue> [goal]
#   <pdb>       path to a PDB file
#   <residue>   residue number (e.g. 15) or 1/3-letter AA code (e.g. R / Arg)
#   [goal]      specificity | binding-anion | remove-interaction | catalytic
#               (default: specificity)
#
set -euo pipefail

# --- args ---
if [ $# -lt 2 ]; then
  echo "Usage: $(basename "$0") <pdb> <residue> [goal]" >&2
  exit 2
fi
PDB="$1"; RES="$2"; GOAL="${3:-specificity}"

case "$GOAL" in
  specificity|binding-anion|remove-interaction|catalytic) ;;
  *) echo "error: unknown goal '$GOAL' (use specificity|binding-anion|remove-interaction|catalytic)" >&2; exit 2 ;;
esac

# --- validate PDB ---
if [ ! -f "$PDB" ]; then
  echo "error: PDB not found: $PDB" >&2
  exit 1
fi
PDB="$(cd "$(dirname "$PDB")" && pwd)/$(basename "$PDB")"   # absolute path
PDB_DIR="$(dirname "$PDB")"
PDB_BASE="$(basename "$PDB")"

# --- locate the skill assets root (this script lives in <skill_dir>/scripts/) ---
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AK_DIR="$(dirname "$SCRIPT_DIR")"

GROMACS_IMAGE="gromacs-hip-gfx1100"
MDPREP_IMAGE="md-prep:latest"

# --- temp workspace (cleaned on exit) ---
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# --- step 1: protein-only PDB (standard-AA ATOM records) for DSSP input ---
awk 'BEGIN{
  n=split("ALA ARG ASN ASP CYS GLN GLU GLY HIS ILE LEU LYS MET PHE PRO SER THR TRP TYR VAL", a, " ")
  for(i=1;i<=n;i++) aa[a[i]]=1
} $1=="ATOM" && ($4 in aa) { print } END{ print "END" }' "$PDB" > "$TMP/protein.pdb"

# --- step 2: gmx dssp (transient gromacs container, CPU-only, no GPU) ---
HAVE_DSSP=0
if command -v docker >/dev/null 2>&1 && docker image inspect "$GROMACS_IMAGE" >/dev/null 2>&1; then
  if docker run --rm -v "$TMP:/input" "$GROMACS_IMAGE" \
       gmx dssp -s /input/protein.pdb -f /input/protein.pdb \
                -o /input/protein.dssp.dat -hmode dssp \
       >"$TMP/dssp.log" 2>&1; then
    HAVE_DSSP=1
  else
    echo "warning: gmx dssp failed; falling back to PDB records only" >&2
    sed 's/^/    /' "$TMP/dssp.log" >&2
  fi
else
  echo "warning: docker / $GROMACS_IMAGE unavailable; using PDB records only" >&2
fi

# --- step 3: advise.py (transient md-prep container) ---
if ! docker image inspect "$MDPREP_IMAGE" >/dev/null 2>&1; then
  echo "error: $MDPREP_IMAGE not found. Build it:  docker build -t md-prep:latest -f gromacs/Dockerfile.mdprep gromacs/" >&2
  exit 1
fi

if [ "$HAVE_DSSP" -eq 1 ]; then
  MOUNTS=(-v "$PDB_DIR":/pdb:ro -v "$TMP":/dssp:ro)
  DSSP_ARGS=(--dssp /dssp/protein.dssp.dat)
else
  MOUNTS=(-v "$PDB_DIR":/pdb:ro)
  DSSP_ARGS=()
fi

docker run --rm \
  -v "$AK_DIR:/ak:ro" \
  "${MOUNTS[@]}" \
  "$MDPREP_IMAGE" \
  python3 /ak/scripts/advise.py \
  --pdb "/pdb/$PDB_BASE" --residue "$RES" --goal "$GOAL" \
  "${DSSP_ARGS[@]}"
