#!/usr/bin/env bash
# preflight.sh — environment gate before a phase.
#
# Usage: preflight.sh <sim_dir> --cpu | --gpu
#   --cpu  any stack mode; used before phases 1-4 and 7
#   --gpu  requires gromacs mode (live gromacs-rocm container); used before
#          GPU phases (5-6, large-system EM). Detection only — never switches
#          mode. Exit 2 + MODE line if not in gromacs mode (agent applies
#          MS2/MS3).
# Output: one PASS|FAIL|<check>|<detail> line per check.
# Exit:   0 all pass, 1 any fail, 2 environment error (incl. wrong mode).
set -euo pipefail

SIM="$(realpath "${1:?usage: $0 <sim_dir>}")"
MODE="${2:?usage: $0 <sim_dir> --cpu|--gpu}"
IMAGE="gromacs-hip-gfx1100:latest"
STACK_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"

fail=0
pass() { echo "PASS|$1|$2"; }
failc() { echo "FAIL|$1|$2"; fail=1; }

# --- (1) image present ------------------------------------------------------
if docker image inspect "$IMAGE" >/dev/null 2>&1; then
  pass image "present: $IMAGE"
else
  failc image "missing: $IMAGE (build: docker build -f gromacs/Dockerfile.rocm gromacs/)"
fi

# --- (2) transient gmx --version works --------------------------------------
if out="$(docker run --rm "$IMAGE" gmx --version 2>&1)"; then
  pass gmx_version "$(echo "$out" | grep -m1 -o 'version [0-9][^,]*' || echo 'ok')"
else
  failc gmx_version "transient gmx --version failed"
fi

# --- (3) project dir exists & writable ---------------------------------------
if [ -d "$SIM" ] && [ -w "$SIM" ]; then
  pass simdir "exists & writable: $SIM"
else
  failc simdir "missing or not writable: $SIM"
fi

# --- (4) free disk >= 2x estimate --------------------------------------------
# Estimate (spec §15): .xtc ~2 MB/frame @2 ps, .edr ~0.1 GB/ns, .log ~100 MB/ns.
# Reads prod_time_ps (or the C2-variant production_time_ps) from state.json when
# present; default 10 ns. Accepting both keys stops the disk check from silently
# falling back to the 10 ns default on a key-name mismatch (issues_agent_run C2).
prod_ns=10
if [ -f "$SIM/state.json" ]; then
  ps="$(sed -n -E 's/.*"(production_time_ps|prod_time_ps)"[[:space:]]*:[[:space:]]*([0-9.]+).*/\2/p' "$SIM/state.json" | head -1)"
  [ -n "${ps:-}" ] && prod_ns="$(awk -v ps="$ps" 'BEGIN{printf "%.1f", ps/1000}')"
fi
est_gb="$(awk -v ns="$prod_ns" 'BEGIN{printf "%.1f", 2*(ns*0.1 + ns*0.1 + ns*20*2/1000)}')"
free_gb="$(df -BG --output=avail "$(dirname "$SIM")" 2>/dev/null | tail -1 | tr -dc '0-9')"
if [ -n "$free_gb" ] && [ "$free_gb" -ge "$(awk -v e="$est_gb" 'BEGIN{printf "%d", e+1}')" ]; then
  pass disk "free ${free_gb} GB >= 2x estimate ${est_gb} GB (prod ${prod_ns} ns)"
else
  failc disk "free ${free_gb:-?} GB < 2x estimate ${est_gb} GB (prod ${prod_ns} ns)"
fi

if [ "$MODE" = "--cpu" ]; then
  exit "$fail"
fi

# --- GPU checks (5+) ----------------------------------------------------------
# (5) gromacs-rocm container running (gromacs mode)
if docker compose -f "$STACK_ROOT/docker-compose.yml" --profile gromacs ps --services --status running 2>/dev/null | grep -qx "gromacs-rocm"; then
  pass mode "gromacs-rocm running (gromacs mode)"
else
  echo "MODE|not-gromacs|gromacs-rocm not running; agent must apply MS2/MS3 (self-check iGPU, then 'make gromacs' or escalate)"
  exit 2
fi

# (6) no foreign VRAM consumer — HARD: must be verifiable.
# rocm-smi --showmeminfo vram reports byte counts. If we cannot parse them we
# cannot verify the GPU is idle -> environment error (exit 2). No silent skip:
# an unverified GPU is exactly how a foreign consumer (e.g. an LLM server on
# the same device) OOM-kills a long run (issues_agent_run, lysozym 2026-09-25).
vram_out="$(docker compose -f "$STACK_ROOT/docker-compose.yml" --profile gromacs exec -T gromacs-rocm rocm-smi --showmeminfo vram 2>/dev/null || true)"
vram_used="$(echo "$vram_out" | grep -oE 'VRAM Total Used Memory \(B\): [0-9]+' | grep -oE '[0-9]+' | head -1 || true)"
vram_total="$(echo "$vram_out" | grep -oE 'VRAM Total Memory \(B\): [0-9]+' | grep -oE '[0-9]+' | head -1 || true)"
if [ -z "${vram_used:-}" ] || [ -z "${vram_total:-}" ]; then
  echo "ENV|vram|rocm-smi --showmeminfo vram unparseable (no 'VRAM Total Used Memory (B)'); cannot verify GPU is idle — refusing to launch"
  exit 2
fi
vram_mib=$((vram_used / 1048576))
vram_total_mib=$((vram_total / 1048576))
if [ "$vram_mib" -lt 512 ]; then
  pass vram "idle: ${vram_mib} MiB / ${vram_total_mib} MiB used"
else
  failc vram "foreign VRAM consumer: ${vram_mib} MiB / ${vram_total_mib} MiB used (>= 512 MiB)"
fi

# (7) HIP build with gfx1100 offload (gfx1100 appears on the compiler-flags line)
if hip="$(docker compose -f "$STACK_ROOT/docker-compose.yml" --profile gromacs exec -T gromacs-rocm gmx --version 2>&1 | grep -m1 -i 'gfx1100')"; then
  pass hip "HIP + gfx1100: $(echo "$hip" | tr '\n' ' ' | cut -c1-80)"
else
  failc hip "gmx --version in live container lacks gfx1100 offload"
fi

exit "$fail"
