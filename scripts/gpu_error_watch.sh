#!/usr/bin/env bash
# gpu_error_watch.sh — foreground, interactive eGPU ERROR watcher.
#
# Watches for GPU errors and prints them IMMEDIATELY as they appear. This is
# the "see errors the moment they happen" companion to gpu_monitor.sh (which
# shows live metrics) — run this in a shell while a stress test is going.
#
# It does NOT show clock/temp/power/t-s (that's gpu_monitor.sh's job). It only
# surfaces failure signals:
#   1. new GPU-related dmesg lines   (amdgpu / gpu / ecc / retire / page)
#   2. RAS retired/pending page changes (hard memory errors)
#   3. the llamacpp-egpu container stopping (crash)
#   4. the undervolt offset changing (undervolt lost, or you changed it)
#
# GPU mapping (verified): rocm-smi GPU[0] = Navi 31 = eGPU = sysfs card1
#
# Usage:   gpu_error_watch.sh [interval_seconds]     (default 5)
# Quit:    press q  OR  Ctrl-C
set -u

INTERVAL="${1:-5}"
CONTAINER="llamacpp-egpu"
GPU_SYSFS="/sys/class/drm/card1/device"

RED=$'\e[0;31m'; GREEN=$'\e[0;32m'; YELLOW=$'\e[1;33m'
CYAN=$'\e[0;36m'; BOLD=$'\e[1m'; FAINT=$'\e[2m'; RESET=$'\e[0m'

# Is there a real terminal for single-key reads? If not (e.g. piped/CI), we fall
# back to a plain sleep so the interval is always respected and we never spin.
HAVE_TTY=0
[[ -r /dev/tty && -w /dev/tty ]] && HAVE_TTY=1

cleanup() {
  [[ "$HAVE_TTY" == 1 ]] && stty echo icanon 2>/dev/null < /dev/tty || true
  printf '\n%swatcher stopped.%s\n' "$FAINT" "$RESET"
}
trap 'cleanup; exit 0' INT TERM

# The undervolt offset (mV) actually applied in the kernel.
get_offset() {
  grep -A1 OD_VDDGFX_OFFSET "$GPU_SYSFS/pp_od_clk_voltage" 2>/dev/null | tail -1 | tr -d ' '
}

# --- startup header ---------------------------------------------------------
printf '%s=== eGPU error watcher ===%s\n' "$BOLD$CYAN" "$RESET"
echo "eGPU:      rocm-smi GPU[0] = sysfs card1 (Navi 31)"
echo "container: $CONTAINER"
echo "offset:    $(get_offset)  (at start)"
echo "interval:  ${INTERVAL}s"
echo "watching:  dmesg · RAS pages · container · offset"
printf '%spress q to quit (Ctrl-C also works)%s\n' "$FAINT" "$RESET"
echo "--------------------------------------------------"

# Quiet, canonical-off so a single keypress is available immediately.
[[ "$HAVE_TTY" == 1 ]] && stty -echo -icanon 2>/dev/null < /dev/tty || true

dmesg_cursor=$(dmesg 2>/dev/null | wc -l)
ras_prev=""
offset_prev="$(get_offset)"

while true; do
  tick_start=$(date +%s)
  now=$(date '+%H:%M:%S')
  errors=""

  # 1. new GPU-related dmesg lines since last tick
  newdm=$(dmesg 2>/dev/null | tail -n +$((dmesg_cursor + 1)) \
          | grep -iE 'amdgpu|gpu|ecc|retire|page' || true)
  if [ -n "$newdm" ]; then
    n=$(printf '%s\n' "$newdm" | wc -l)
    errors+="${RED}${BOLD}[$now] NEW GPU DMESG ($n line(s)):${RESET}\n"
    errors+="$(printf '%s\n' "$newdm" | sed 's/^/    /')\n"
  fi
  dmesg_cursor=$(dmesg 2>/dev/null | wc -l)

  # 2. RAS retired/pending pages changed (first read = silent baseline)
  ras=$(rocm-smi --showretiredpages --showpendingpages 2>/dev/null | md5sum | cut -d' ' -f1)
  if [ -n "$ras" ]; then
    if [ -n "$ras_prev" ] && [ "$ras" != "$ras_prev" ]; then
      errors+="${RED}${BOLD}[$now] RAS PAGE STATE CHANGED:${RESET}\n"
      errors+="$(rocm-smi --showretiredpages --showpendingpages 2>/dev/null | sed 's/^/    /')\n"
    fi
    ras_prev="$ras"
  fi

  # 3. container not running (crash = primary failure signal)
  cstat=$(docker inspect -f '{{.State.Status}}' "$CONTAINER" 2>/dev/null || echo GONE)
  if [ "$cstat" != "running" ]; then
    errors+="${RED}${BOLD}[$now] CONTAINER NOT RUNNING: $cstat${RESET}\n"
  fi

  # 4. undervolt offset changed
  offset_now="$(get_offset)"
  if [ "$offset_now" != "$offset_prev" ]; then
    errors+="${YELLOW}${BOLD}[$now] VOLTAGE OFFSET CHANGED: $offset_prev -> $offset_now${RESET}\n"
    offset_prev="$offset_now"
  fi

  # print: errors (red/yellow) if any, else a faint heartbeat so you know it's alive
  if [ -n "$errors" ]; then
    printf '%b' "$errors"
  else
    printf '%s\n' "${GREEN}[$now] ok${RESET}"
  fi

  # --- wait out the interval, allowing early exit on 'q' ---
  # Attempt a key read (only works with a real tty; fails fast + silently
  # otherwise). Then always sleep whatever time is left, so the interval is
  # respected in every case (no tty, early keypress, slow checks, ...).
  key=""
  IFS= read -rsn1 -t "$INTERVAL" key 2>/dev/null < /dev/tty || true
  case "$key" in q|Q) break ;; esac
  elapsed=$(( $(date +%s) - tick_start ))
  remaining=$(( INTERVAL - elapsed ))
  (( remaining > 0 )) && sleep "$remaining"
done

cleanup
exit 0
