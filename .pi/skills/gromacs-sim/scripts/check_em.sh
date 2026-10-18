#!/usr/bin/env bash
# check_em.sh — phase-4 (energy minimization) gate.
#
# Usage: check_em.sh <sim_dir>
# Expects: 04_em/em.log (or em_cg.log if the D10 CG fallback ran) + matching .mdp
# Checks:  Fmax < emtol (final table row); Epot in -1e6..-1e4 kJ/mol band
#          (solvated biomolecule, KB 01.4); no LINCS/SHAKE warnings;
#          no "exceeded"/"Panic"/"not finite" lines.
# Exit:   0 pass, 1 fail, 2 environment error.
set -euo pipefail

SIM="${1:?usage: $0 <sim_dir>}"
EM="$SIM/04_em"
fail=0
pass() { echo "PASS|$1|$2"; }
failc() { echo "FAIL|$1|$2"; fail=1; }
env() { echo "ENV|$1|$2"; exit 2; }

[ -d "$EM" ] || env em "04_em/ missing in $SIM"
# SD first, CG fallback second (D10)
if [ -f "$EM/em.log" ]; then LOG="$EM/em.log"; MDP="$EM/em.mdp"; ALGO="sd"
elif [ -f "$EM/em_cg.log" ]; then LOG="$EM/em_cg.log"; MDP="$EM/em_cg.mdp"; ALGO="cg"
else
  env log "no em.log or em_cg.log in $EM"
fi
[ -f "$MDP" ] || env mdp "missing $MDP"

# --- final Fmax / Epot (from the EM summary block, not the step table) ---------
# The last numeric log row is the step counter (e.g. "1000  1000.00000"), NOT the
# energy table — parse the authoritative summary lines instead:
#   "Maximum force     =  2.0003099e+02 on atom 545"
#   "Potential Energy  = -6.8498025e+05"
fmax="$(grep -E '^Maximum force' "$LOG" | head -1 | awk '{print $4}')"
epot="$(grep -E '^Potential Energy' "$LOG" | head -1 | awk '{print $4}')"
emtol="$(sed -n 's/^[[:space:]]*emtol[[:space:]]*=[[:space:]]*\([0-9.eE+-]*\).*/\1/p' "$MDP" | head -1)"
# Acceptance (KB 01.4): clean convergence (Fmax < emtol), OR "converged to
# machine precision" with Fmax in 10..1000 (a practical minimum, fine start).
# Anything else (Fmax > 1000, or no convergence message) is a FAIL.
mp_conv=false
grep -q "machine precision" "$LOG" && mp_conv=true
if [ -n "$fmax" ] && [ -n "$emtol" ] && awk -v a="$fmax" -v b="$emtol" 'BEGIN{exit !(a < b)}'; then
  pass fmax "Fmax=$fmax < emtol=$emtol ($ALGO)"
elif $mp_conv && awk -v a="$fmax" 'BEGIN{exit !(a >= 10 && a < 1000)}'; then
  pass fmax "Fmax=$fmax in 10..1000 with machine-precision convergence (KB 01.4: acceptable start, $ALGO)"
else
  failc fmax "Fmax=${fmax:-?} not < emtol=${emtol:-?} and no acceptable machine-precision convergence ($ALGO)"
fi

# --- Epot band: -1e6 .. -1e4 kJ/mol (KB 01.4) -----------------------------------
if [ -n "$epot" ] && awk -v e="$epot" 'BEGIN{exit !(e < -1e4 && e > -1e6)}'; then
  pass epot "Epot=$epot kJ/mol in solvated-biomolecule band (-1e6..-1e4)"
else
  failc epot "Epot=${epot:-?} kJ/mol outside band (-1e6..-1e4)"
fi

# --- no constraint / non-finite / panic lines ------------------------------------
# Case-sensitive + specific: must NOT match the MDP echo ("Shake-SOR", "shake-tol")
# or the SETTLE citation ("SHAKE and RATTLE"). Real GROMACS failures are:
#   "Lincs warning: ...", "SHAKE ERROR"/"SHAKE WARNING", "Panic in ...",
#   "values are not finite", "... exceeded ..."
if grep -qE "Lincs warning|SHAKE (ERROR|WARNING)|Panic|not finite|exceeded" "$LOG"; then
  failc log_clean "constraint/panic lines: $(grep -cE 'Lincs warning|SHAKE (ERROR|WARNING)|Panic|not finite|exceeded' "$LOG")"
else
  pass log_clean "no LINCS/SHAKE-error/panic lines"
fi

exit "$fail"
