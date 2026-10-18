#!/usr/bin/env bash
# cleanup.sh — phase-8 (cleanup) gate. Deterministic disposal of transient
# artifacts AFTER the analysis gate passed. Mandatory last phase: a sim is
# not "done" until this gate passes.
#
# Usage: cleanup.sh <sim_dir> [--apply]
#   default  = dry-run: report what WOULD be deleted + bytes, delete nothing
#   --apply  = execute the deletion
#
# Pre-gates (exit 2, nothing deleted):
#   (1) analysis complete: 07_analysis/REPORT.md exists AND state.json
#       phase >= 7 (when state.json present)
#   (2) no live mdrun / no orphaned gromacs container (check_running.sh)
#
# Deletion whitelist (ONLY these patterns are ever removed):
#   T1: #*.N# files anywhere in the sim dir — GROMACS auto-backups created
#       when a tool re-writes an existing output (stale copies from re-runs)
#   T2: *.cpt in 05_equil/ and 06_production/ — checkpoints, only useful for
#       resuming an interrupted run
#   T3: 07_analysis/step1.xtc, 07_analysis/msd_unwrapped.xtc,
#       07_analysis/{dssp.dat,hbond.ndx,num.xvg,hbnum.xvg} — derived
#       intermediates, regenerable from 06_production/md.xtc (see KB 01.10)
#
# NEVER deleted: 06_production/md.xtc (source trajectory), 07_analysis/
# clean.xtc (kept per policy — avoids re-running trjconv on re-analysis),
# all .mdp/.top/.tpr/.gro, .xvg/.png/REPORT.md, index files, logs,
# state.json, RUNLOG.md, input/.
#
# Idempotent: re-running on a clean project is a PASS (0 bytes freed).
# After any re-analysis (which re-creates #*.N# files), re-run --apply.
#
# Host-side only — no container needed.
# Exit: 0 pass, 1 fail, 2 environment error.
set -euo pipefail

SIM="$(realpath "${1:?usage: $0 <sim_dir> [--apply]}")"
APPLY=0
[ "${2:-}" = "--apply" ] && APPLY=1

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fail=0
pass() { echo "PASS|$1|$2"; }
failc() { echo "FAIL|$1|$2"; fail=1; }
env() { echo "ENV|$1|$2"; exit 2; }

[ -d "$SIM" ] || env sim "missing sim dir: $SIM"

# --- pre-gate 1: analysis complete -------------------------------------------------
[ -f "$SIM/07_analysis/REPORT.md" ] || \
  env analysis "07_analysis/REPORT.md missing — phase 7 not complete, refuse cleanup"
phase="$(sed -n 's/.*"phase"[[:space:]]*:[[:space:]]*\([0-9]*\).*/\1/p' "$SIM/state.json" 2>/dev/null | head -1)"
if [ -n "$phase" ] && [ "$phase" -lt 7 ]; then
  env analysis "state.json phase=$phase < 7 — analysis not complete, refuse cleanup"
fi

# --- pre-gate 2: nothing running -----------------------------------------------------
"$SKILL_DIR/scripts/check_running.sh" "$SIM" > /dev/null 2>&1 \
  || env running "mdrun in progress or orphaned gromacs container — refuse cleanup"

# --- build deletion list (whitelist only) --------------------------------------------
targets=()
while IFS= read -r f; do targets+=("$f"); done < <(find "$SIM" -type f -name '#*#')
for d in 05_equil 06_production; do
  [ -d "$SIM/$d" ] || continue
  while IFS= read -r f; do targets+=("$f"); done < <(find "$SIM/$d" -maxdepth 1 -type f -name '*.cpt')
done
for f in 07_analysis/step1.xtc 07_analysis/msd_unwrapped.xtc 07_analysis/dssp.dat \
         07_analysis/hbond.ndx 07_analysis/num.xvg 07_analysis/hbnum.xvg; do
  [ -f "$SIM/$f" ] && targets+=("$SIM/$f")
done

# Defensive guard: the whitelist must never contain a permanent artifact.
for t in ${targets[@]+"${targets[@]}"}; do
  case "$(basename "$t")" in
    md.xtc|clean.xtc|REPORT.md|state.json|RUNLOG.md)
      env guard "whitelist violation (permanent artifact in deletion list): $t" ;;
  esac
done

total_bytes=0
for t in ${targets[@]+"${targets[@]}"}; do
  total_bytes=$(( total_bytes + $(stat -c %s "$t") ))
done
total_gb="$(awk -v b="$total_bytes" 'BEGIN{printf "%.2f", b/1073741824}')"
before_gb="$(du -sh "$SIM" | cut -f1)"

# --- dry-run report -------------------------------------------------------------------
REPORT="$SIM/cleanup_report.txt"
{
  echo "# cleanup report — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "mode: $([ "$APPLY" = 1 ] && echo apply || echo dry-run)"
  echo "files: ${#targets[@]}, bytes: $total_bytes ($total_gb GB)"
  for t in ${targets[@]+"${targets[@]}"}; do
    echo "  $(stat -c %s "$t")  ${t#$SIM/}"
  done
} > "$REPORT"

if [ "$APPLY" = 0 ]; then
  pass dry_run "would delete ${#targets[@]} files ($total_gb GB) — re-run with --apply to execute"
  pass report "dry-run list written to cleanup_report.txt"
  exit "$fail"
fi

# --- apply -----------------------------------------------------------------------------
for t in ${targets[@]+"${targets[@]}"}; do rm -f "$t"; done

# --- post-verification -------------------------------------------------------------------
stale="$(find "$SIM" -type f -name '#*#' | wc -l)"
if [ "$stale" = 0 ]; then
  pass verify "no #*.N# backup files remain"
else
  failc verify "$stale #*.N# files remain after deletion"
fi
for f in 06_production/md.xtc 07_analysis/clean.xtc 07_analysis/REPORT.md; do
  if [ -f "$SIM/$f" ]; then
    pass kept "$f intact"
  else
    failc kept "$f missing (must never be deleted)"
  fi
done
after_gb="$(du -sh "$SIM" | cut -f1)"
pass freed "project ${before_gb} -> ${after_gb} (${#targets[@]} files, ${total_gb} GB freed)"
{ echo "result: applied, ${#targets[@]} files deleted, $total_gb GB freed"
  echo "project size: $before_gb -> $after_gb"
} >> "$REPORT"

exit "$fail"
