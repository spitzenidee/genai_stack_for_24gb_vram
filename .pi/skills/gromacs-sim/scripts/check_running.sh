#!/usr/bin/env bash
# check_running.sh — guard against launching a duplicate/orphaned mdrun.
#
# MANDATORY before ANY mdrun launch (issues_agent_run B1: a 300 s tool timeout
# killed the `docker run` client but the container kept running, so the agent
# launched 3 more mdruns -> #file# rename collisions + ~2 h wasted CPU).
#
# Usage: check_running.sh [sim_dir]
#   sim_dir optional; accepted for catalog uniformity (the guard is global:
#   this skill runs one mdrun at a time, so any running mdrun blocks a launch).
# Checks:
#   (1) no mdrun process in the live gromacs-rocm container (pgrep)
#   (2) no orphaned gromacs containers left by a timed-out tool call (docker ps)
# Output: one PASS|FAIL|<check>|<detail> line per check.
# Exit:   0 = safe to launch (nothing running), 1 = mdrun already running /
#          orphan present (do NOT launch — a timed-out tool call does NOT kill
#          the container), 2 = environment error.
set -euo pipefail

SIM="${1:-}"
STACK_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
IMAGE="gromacs-hip-gfx1100:latest"
fail=0
pass() { echo "PASS|$1|$2"; }
failc() { echo "FAIL|$1|$2"; fail=1; }

# --- (1) mdrun in the live container (only meaningful if the container runs) ---
# Compose v5.5.1 does NOT support `ps --services --running` (the flag fatales
# and the 2>/dev/null hid it -> false "not running" report, RCA issue 7).
# Use docker ps directly; the compose service has container_name gromacs-rocm.
if docker ps --filter "name=gromacs-rocm" --filter "status=running" \
  --format '{{.Names}}' 2>/dev/null | grep -qx "gromacs-rocm"; then
  # [m]drun: the bracket keeps pgrep from matching its own bash -lc command
  # line (which contains the literal pattern text) -> no false n>=1.
  n="$(docker exec gromacs-rocm bash -lc 'pgrep -fc [m]drun 2>/dev/null || true' | tr -d '[:space:]')"
  if [ "${n:-0}" -gt 0 ]; then
    failc running "mdrun already running in gromacs-rocm (n=$n) — do NOT launch a duplicate"
  else
    pass running "no mdrun in gromacs-rocm"
  fi
else
  pass running "gromacs-rocm not running (nothing to collide with)"
fi

# --- (2) orphaned gromacs containers (timed-out tool call left them behind) ---
# Standalone `docker run` containers from the image, excluding the compose-managed
# gromacs-rocm service (a timed-out client does not stop the container).
orphans="$(docker ps --filter "ancestor=$IMAGE" --format '{{.ID}} {{.Names}} {{.Status}}' 2>/dev/null \
  | grep -vE '(^| )gromacs-rocm( |$)' || true)"
if [ -n "$orphans" ]; then
  failc orphan "orphaned gromacs container(s) from a timed-out call: $(echo "$orphans" | tr '\n' '; ')"
else
  pass orphan "no orphaned gromacs containers"
fi

exit "$fail"
