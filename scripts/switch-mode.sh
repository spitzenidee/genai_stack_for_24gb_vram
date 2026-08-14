#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# switch-mode.sh — exclusive GPU work-mode switch for genai_stack
#
# The Radeon RX 7900 XTX has no VRAM isolation between contexts, so only one
# GPU-heavy mode runs at a time. Switching stops the other modes' services
# and starts the target mode, which then keeps running (restart: unless-
# stopped) until the next switch.
#
# Always-on regardless of mode: lact, gpu-exporter, otel-collector,
# llama-sd, llamacpp-igpu. The iGPU service runs on the Radeon 780M
# (independent hardware, own UMA carve-out, no VRAM contention with the
# eGPU), so it is intentionally NOT listed in MODE_SERVICES below — once
# started, `restart: unless-stopped` keeps it running across mode switches.
#
# Usage: switch-mode.sh llama|comfyui|gromacs|blender
# ---------------------------------------------------------------------------
set -euo pipefail

declare -A MODE_SERVICES=(
  [llama]="llamacpp-egpu open-webui"
  [comfyui]="comfyui-rocm"
  [gromacs]="gromacs-rocm"
  [blender]="blender-rocm"
)

MODE="${1:-}"
if [[ -z "${MODE}" || -z "${MODE_SERVICES[$MODE]:-}" ]]; then
  echo "Usage: $(basename "$0") llama|comfyui|gromacs|blender" >&2
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

for m in "${!MODE_SERVICES[@]}"; do
  [[ "$m" == "$MODE" ]] && continue
  # shellcheck disable=SC2086
  docker compose stop ${MODE_SERVICES[$m]} 2>/dev/null || true
done

# shellcheck disable=SC2086
docker compose --profile "$MODE" up -d ${MODE_SERVICES[$MODE]}

echo
echo "Switched to ${MODE^^} mode — GPU services: ${MODE_SERVICES[$MODE]}"
echo "Other modes stopped. Always-on: lact, gpu-exporter, otel-collector, llama-sd, llamacpp-igpu."
echo "Run 'make status' anytime to check."
