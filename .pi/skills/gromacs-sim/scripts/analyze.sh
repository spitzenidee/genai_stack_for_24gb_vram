#!/usr/bin/env bash
# analyze.sh — phase-7 (analysis) gate. Runs the spec §11 suite.
#
# Usage: analyze.sh <sim_dir> [prod_time_ps]
# Expects: 06_production/{md.tpr, md.xtc, md.edr}
# Does:    gromacs container (any mode): make_ndx + trjconv + 8-item suite ->
#          07_analysis/*.xvg; md-prep container: *.png + REPORT.md.
#          If md-prep image is missing: all .xvg + a minimal REPORT.md are
#          still produced, plots flagged skipped (NOT a gate failure).
# Exit:   0 pass, 1 fail, 2 environment error.
set -euo pipefail

SIM="$(realpath "${1:?usage: $0 <sim_dir>}")"
PROD_PS="${2:-}"
AN="$SIM/07_analysis"
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STACK_ROOT="$(cd "$SKILL_DIR/../../.." && pwd)"
IMAGE="gromacs-hip-gfx1100:latest"
PIMAGE="md-prep:latest"
fail=0
pass() { echo "PASS|$1|$2"; }
failc() { echo "FAIL|$1|$2"; fail=1; }
env() { echo "ENV|$1|$2"; exit 2; }

[ -d "$AN" ] || mkdir -p "$AN"
for f in md.tpr md.xtc md.edr; do
  [ -f "$SIM/06_production/$f" ] || env input "missing 06_production/$f"
done

case "$SIM" in
  "$STACK_ROOT"/gromacs/work/*) CPATH="/work/${SIM#$STACK_ROOT/gromacs/work/}" ;;
  *) env mount "sim dir not under $STACK_ROOT/gromacs/work: $SIM" ;;
esac

# --- gromacs suite (one transient container, E3) --------------------------------
cat > "$AN/_suite.sh" <<'GSUITE'
#!/usr/bin/env bash
set -uo pipefail
AN_DIR="__AN_DIR__"
cd "$AN_DIR"
TPR=../06_production/md.tpr
XTC=../06_production/md.xtc
EDR=../06_production/md.edr

# --- index groups: discover numbers by name -------------------------------------
echo "q" | gmx make_ndx -f "$TPR" -o index.ndx > ndx_list.txt 2>&1 || true
# Exact-name match (name followed by the ':' that starts the atom count) so
# "Protein" doesn't also hit Protein-H/non-Protein and "Water" doesn't hit
# non-Water — the old \b pattern relied on head -1 luck of group ordering (I-7).
gnum() { grep -E "^[[:space:]]*[0-9]+[[:space:]]+$1[[:space:]]*:" ndx_list.txt | head -1 | grep -o '^[[:space:]]*[0-9]*' | tr -d ' '; }
G_PROT="$(gnum Protein)"
G_CA="$(gnum 'C-alpha')"
G_BACK="$(gnum Backbone)"
G_WAT="$(gnum Water)"
for v in G_PROT G_CA G_BACK G_WAT; do
  [ -n "${!v}" ] || { echo "SUITE_FAIL|ndx|missing group $v"; exit 1; }
done
echo "SUITE_OK|ndx|Protein=$G_PROT CA=$G_CA Backbone=$G_BACK Water=$G_WAT"

# --- clean trajectory -------------------------------------------------------------
# 2026.3: -fitgroup/-centergroup are removed (groups via stdin, order
# fit -> center -> output) and -pbc mol is incompatible with -fit rot+trans
# in one call — so two steps. Output group = System (0) so water/ions stay.
gmx trjconv -s "$TPR" -f "$XTC" -n index.ndx -pbc mol -o step1.xtc <<EOF > trjconv.log 2>&1
0
EOF
gmx trjconv -s "$TPR" -f step1.xtc -n index.ndx -fit rot+trans -center -o clean.xtc <<EOF >> trjconv.log 2>&1
$G_BACK
$G_PROT
0
EOF
[ -s clean.xtc ] || { echo "SUITE_FAIL|trjconv|clean.xtc empty"; exit 1; }
echo "SUITE_OK|trjconv|clean.xtc $(du -h clean.xtc | cut -f1)"

# --- energy terms: discover numbers by name ---------------------------------------
gmx energy -f "$EDR" < /dev/null > energy_list.txt 2>&1 || true
# 2026.3 energy list is multi-term per line with no colons — unanchored match.
enum() { grep -oE "[0-9]+[[:space:]]+$1" energy_list.txt | head -1 | grep -oE '^[0-9]+'; }
E_TOT="$(enum 'Total-Energy')"
E_POT="$(enum 'Potential')"
E_KIN="$(enum 'Kinetic-En.')"
E_T="$(enum 'Temperature')"
E_P="$(enum 'Pressure')"
E_V="$(enum 'Volume')"
E_D="$(enum 'Density')"
sel=""
for n in "$E_TOT" "$E_POT" "$E_KIN" "$E_T" "$E_P" "$E_V" "$E_D"; do
  [ -n "$n" ] && sel="$sel $n"
done
sel="$(echo "$sel" | tr ' ' '\n' | sort -un | tr '\n' ' ')"
[ -n "$sel" ] || { echo "SUITE_FAIL|energy|no terms found"; exit 1; }
echo "$sel" | gmx energy -f "$EDR" -o energies.xvg > /dev/null 2>&1 \
  || { echo "SUITE_FAIL|energy|gmx energy failed"; exit 1; }
[ -s energies.xvg ] || { echo "SUITE_FAIL|energy|energies.xvg empty"; exit 1; }
echo "SUITE_OK|energy|energies.xvg terms: $sel"

# --- 2. RMSD (backbone fit -> backbone & CA) --------------------------------------
gmx rms -s "$TPR" -f clean.xtc -n index.ndx -o rmsd_backbone.xvg <<EOF > /dev/null 2>&1
$G_BACK
$G_BACK
EOF
gmx rms -s "$TPR" -f clean.xtc -n index.ndx -o rmsd_ca.xvg <<EOF > /dev/null 2>&1
$G_BACK
$G_CA
EOF
[ -s rmsd_backbone.xvg ] && [ -s rmsd_ca.xvg ] || { echo "SUITE_FAIL|rms|rmsd xvg empty"; exit 1; }
echo "SUITE_OK|rms|rmsd_backbone.xvg + rmsd_ca.xvg"

# --- 3. RMSF per residue -------------------------------------------------------------
gmx rmsf -s "$TPR" -f clean.xtc -n index.ndx -res -o rmsf.xvg <<EOF > /dev/null 2>&1
$G_BACK
EOF
[ -s rmsf.xvg ] || { echo "SUITE_FAIL|rmsf|rmsf.xvg empty"; exit 1; }
echo "SUITE_OK|rmsf|rmsf.xvg"

# --- 4. Radius of gyration -------------------------------------------------------------
gmx gyrate -s "$TPR" -f clean.xtc -n index.ndx -o gyrate.xvg <<EOF > /dev/null 2>&1
$G_PROT
EOF
[ -s gyrate.xvg ] || { echo "SUITE_FAIL|gyrate|gyrate.xvg empty"; exit 1; }
echo "SUITE_OK|gyrate|gyrate.xvg"

# --- 5. Secondary structure fractions ---------------------------------------------------
# 2026.3: -o requires the .dat extension (a .xvg target fatales); -num writes
# the numerical output to a SEPARATE generic file num.xvg (the -o target
# dssp.dat holds the per-frame SS string). Copy num.xvg to the expected name
# in the same run (a second dssp run in this dir would overwrite num.xvg).
gmx dssp -s "$TPR" -f clean.xtc -n index.ndx -num -o dssp.dat <<EOF > /dev/null 2>&1
$G_PROT
EOF
cp num.xvg dssp.xvg
[ -s dssp.xvg ] || { echo "SUITE_FAIL|dssp|dssp.xvg empty"; exit 1; }
echo "SUITE_OK|dssp|dssp.xvg"

# --- 6. H-bond count over time ---------------------------------------------------------
# 2026.3: -o requires the .ndx extension (a .xvg target fatales); -num writes
# the count series to a SEPARATE generic file hbnum.xvg. Two group selections
# via stdin (reference then target — Protein/Protein here; -r/-t select
# specific groups). Copy hbnum.xvg to the expected name in the same run.
gmx hbond -s "$TPR" -f clean.xtc -n index.ndx -num -o hbond.ndx <<EOF > /dev/null 2>&1
$G_PROT
$G_PROT
EOF
cp hbnum.xvg hbond.xvg
[ -s hbond.xvg ] || { echo "SUITE_FAIL|hbond|hbond.xvg empty"; exit 1; }
echo "SUITE_OK|hbond|hbond.xvg"

# --- 7. MSD -> diffusion (water + protein, collective) ------------------------------------
# 2026.3: -com removed; -mol OOMs (Killed) on the full trajectory even with
# -trestart 100, and on a subsampled file the -dt <= -trestart constraint makes
# per-molecule fits non-independent (D scatters, incl. negative entries).
# Use the COLLECTIVE MSD (no -mol); D is fitted from the curve (plot_report.py).
# Unwrap DIRECTLY from md.xtc (NOT clean.xtc — a per-frame-fit trajectory
# contaminates water MSD: verified D 2.87e-5 -> 8.9e-5 cm2/s, 3x inflation;
# the fit also removes protein COM diffusion). 2026.3: unwrap = `-pbc nojump`
# (old `-pbc no -ur` gone; `-ur` is now the unit-cell enum).
gmx trjconv -s "$TPR" -f "$XTC" -pbc nojump -o msd_unwrapped.xtc <<EOF > /dev/null 2>&1
0
0
EOF
[ -s msd_unwrapped.xtc ] || { echo "SUITE_FAIL|msd|msd_unwrapped.xtc empty"; exit 1; }
# -trestart 100 >= dt 2: bounds memory (50 frames between restarts).
gmx msd -s "$TPR" -f msd_unwrapped.xtc -n index.ndx -o msd_water.xvg -trestart 100 <<EOF > /dev/null 2>&1
$G_WAT
EOF
gmx msd -s "$TPR" -f msd_unwrapped.xtc -n index.ndx -o msd_protein.xvg -trestart 100 <<EOF > /dev/null 2>&1
$G_PROT
EOF
[ -s msd_water.xvg ] || { echo "SUITE_FAIL|msd|msd_water.xvg empty"; exit 1; }
[ -s msd_protein.xvg ] || { echo "SUITE_FAIL|msd|msd_protein.xvg empty"; exit 1; }
echo "SUITE_OK|msd|msd_water.xvg + msd_protein.xvg (unwrapped-unfit, collective, -trestart 100)"

# --- 8. Density profile (z) -----------------------------------------------------------------
gmx density -s "$TPR" -f clean.xtc -n index.ndx -o density.xvg <<EOF > /dev/null 2>&1
$G_WAT
EOF
[ -s density.xvg ] || { echo "SUITE_FAIL|density|density.xvg empty"; exit 1; }
echo "SUITE_OK|density|density.xvg"
GSUITE
# AN_DIR must be the CONTAINER path (the suite runs inside the container,
# where gromacs/work is mounted at /work) — not the host path (issues: suite
# cd failure). $CPATH is the container-side prefix for $SIM.
sed -i "s|__AN_DIR__|$CPATH/07_analysis|" "$AN/_suite.sh"

docker run --rm -v "$STACK_ROOT/gromacs/work":/work "$IMAGE" bash "$CPATH/07_analysis/_suite.sh" > "$AN/suite.log" 2>&1 \
  || { failc suite "gromacs suite failed: $(grep -m1 SUITE_FAIL "$AN/suite.log" || tail -3 "$AN/suite.log" | tr '\n' ' ')"; }

# --- verify .xvg artifacts ---------------------------------------------------------------
expected_xvg="energies.xvg rmsd_backbone.xvg rmsd_ca.xvg rmsf.xvg gyrate.xvg dssp.xvg hbond.xvg msd_water.xvg msd_protein.xvg density.xvg"
missing=""
for f in $expected_xvg; do
  [ -s "$AN/$f" ] || missing="$missing $f"
done
if [ -z "$missing" ]; then
  pass xvg "all 10 .xvg artifacts present & non-empty"
else
  failc xvg "missing/empty:$missing"
fi
[ -s "$AN/clean.xtc" ] && pass clean_xtc "clean.xtc present" || failc clean_xtc "clean.xtc missing"

# --- md-prep: plots + REPORT.md -----------------------------------------------------------
if docker image inspect "$PIMAGE" >/dev/null 2>&1; then
  # -i is REQUIRED so the host's stdin (plot_report.py) reaches the container;
  # without it `python3 -` reads empty stdin and exits 0 silently (false PASS).
  # The python arg must be the CONTAINER path ($CPATH/...), not the host $AN.
  if docker run --rm -i -v "$STACK_ROOT/gromacs/work":/work "$PIMAGE" \
      python3 - "$CPATH/07_analysis" "${PROD_PS:-0}" < "$SKILL_DIR/scripts/plot_report.py" > "$AN/plot.log" 2>&1; then
    pass plots "png + REPORT.md via md-prep"
  else
    failc plots "md-prep plotting failed: $(tail -3 "$AN/plot.log" | tr '\n' ' ')"
  fi
else
  echo "SKIP|plots|md-prep image missing; .xvg + suite.log only (not a gate failure per spec §11)"
  { echo "# Analysis report"; echo ""; echo "Plots skipped (md-prep image missing). See suite.log."; } > "$AN/REPORT.md"
fi

exit "$fail"
