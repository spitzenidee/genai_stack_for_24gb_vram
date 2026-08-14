#!/usr/bin/env bash
# Unified GPU monitor for the genai_stack VM.
# Reads sysfs directly to avoid the rocm-smi parser crashes seen when the iGPU
# returns unsupported/None sclk values.
#
# Assumption: both the eGPU (7900 XTX, card1) and the iGPU (Radeon 780M, card2)
# are always present while this VM is running.
#
# Usage:
#   gpu_monitor.sh          # refresh every 2 seconds
#   gpu_monitor.sh <secs>   # refresh every <secs> seconds

set -euo pipefail

EGPU_DRM=/sys/class/drm/card1/device
EGPU_HWMON=/sys/class/hwmon/hwmon0
IGPU_DRM=/sys/class/drm/card2/device
IGPU_HWMON=/sys/class/hwmon/hwmon1

# Color escape sequences (use $'...' so printf/echo render them as ANSI codes)
RED=$'\e[0;31m'
YELLOW=$'\e[1;33m'
GREEN=$'\e[0;32m'
CYAN=$'\e[0;36m'
BOLD=$'\e[1m'
RESET=$'\e[0m'

# Global frame buffer: build the whole screen in memory, print once per refresh.
FRAME=""

frame_append() {
    local chunk
    printf -v chunk "$@"
    FRAME+="$chunk"
}

read_int() {
    cat "$1" 2>/dev/null || echo 0
}

read_hz_to_mhz() {
    local v
    v=$(read_int "$1")
    if [[ "$v" -gt 0 ]]; then
        echo "$(( v / 1000000 ))"
    else
        echo 0
    fi
}

# Return color for a temperature (millidegrees C)
color_temp() {
    local t=$1
    if [[ "$t" -ge 90000 ]]; then
        echo "$RED"
    elif [[ "$t" -ge 80000 ]]; then
        echo "$YELLOW"
    else
        echo "$GREEN"
    fi
}

# Return color for a percentage 0-100
color_pct() {
    local p=$1
    if (( $(echo "$p >= 90" | bc -l) )); then
        echo "$RED"
    elif (( $(echo "$p >= 70" | bc -l) )); then
        echo "$YELLOW"
    else
        echo "$GREEN"
    fi
}

gpu_bar() {
    local pct=$1
    local width=${2:-20}
    local filled
    filled=$(awk -v p="$pct" -v w="$width" 'BEGIN{ printf "%d", p*w/100 }')
    local empty=$(( width - filled ))
    local bar="["
    for ((i=0; i<filled; i++)); do bar+="="; done
    for ((i=0; i<empty; i++)); do bar+=" "; done
    bar+="]"
    echo "$bar"
}

read_egpu() {
    local busy mem_busy vram_used vram_total vram_pct
    local edge junction mem temp_color
    local power power_cap power_pct
    local sclk mclk fan_pct fan_rpm

    busy=$(read_int "$EGPU_DRM/gpu_busy_percent")
    mem_busy=$(read_int "$EGPU_DRM/mem_busy_percent")
    vram_used=$(read_int "$EGPU_DRM/mem_info_vram_used")
    vram_total=$(read_int "$EGPU_DRM/mem_info_vram_total")

    edge=$(read_int "$EGPU_HWMON/temp1_input")
    junction=$(read_int "$EGPU_HWMON/temp2_input")
    mem=$(read_int "$EGPU_HWMON/temp3_input")

    power=$(read_int "$EGPU_HWMON/power1_average")
    power_cap=$(read_int "$EGPU_HWMON/power1_cap")

    sclk=$(read_hz_to_mhz "$EGPU_HWMON/freq1_input")
    mclk=$(read_hz_to_mhz "$EGPU_HWMON/freq2_input")

    fan_rpm=$(read_int "$EGPU_HWMON/fan1_input")
    fan_pct=$(read_int "$EGPU_HWMON/pwm1")

    vram_pct=$(awk -v u="$vram_used" -v t="$vram_total" 'BEGIN{ if(t>0) printf "%.1f", 100*u/t; else print 0 }')
    power_pct=$(awk -v p="$power" -v c="$power_cap" 'BEGIN{ if(c>0) printf "%.1f", 100*p/c; else print 0 }')

    frame_append "%seGPU: AMD Radeon 7900 XTX (card1)%s\n" "$BOLD$CYAN" "$RESET"
    frame_append "GPU busy:        %s%5.1f%%%s  %s\n" \
        "$(color_pct "$busy")" "$busy" "$RESET" "$(gpu_bar "$busy")"
    frame_append "Mem busy:        %s%5.1f%%%s  %s\n" \
        "$(color_pct "$mem_busy")" "$mem_busy" "$RESET" "$(gpu_bar "$mem_busy")"
    frame_append "VRAM used:       %s%5.1f%%%s  %6.2f / %6.2f GiB\n" \
        "$(color_pct "$vram_pct")" "$vram_pct" "$RESET" \
        "$(awk -v x="$vram_used" 'BEGIN{ printf "%.2f", x/1073741824 }')" \
        "$(awk -v x="$vram_total" 'BEGIN{ printf "%.2f", x/1073741824 }')"
    frame_append "Power:           %6.2f / %6.2f W (%5.1f%% of cap)\n" \
        "$(awk -v x="$power" 'BEGIN{ printf "%.2f", x/1000000 }')" \
        "$(awk -v x="$power_cap" 'BEGIN{ printf "%.2f", x/1000000 }')" \
        "$power_pct"
    frame_append "Core / Mem clk:  %4d MHz / %4d MHz\n" "$sclk" "$mclk"
    frame_append "Edge temp:       %s%5.1f C%s\n" "$(color_temp "$edge")" "$(awk -v x="$edge" 'BEGIN{ printf "%.1f", x/1000 }')" "$RESET"
    frame_append "Junction temp:   %s%5.1f C%s\n" "$(color_temp "$junction")" "$(awk -v x="$junction" 'BEGIN{ printf "%.1f", x/1000 }')" "$RESET"
    frame_append "Mem temp:        %s%5.1f C%s\n" "$(color_temp "$mem")" "$(awk -v x="$mem" 'BEGIN{ printf "%.1f", x/1000 }')" "$RESET"
    frame_append "Fan:             %d%% (%d RPM)\n" "$fan_pct" "$fan_rpm"
}

read_igpu() {
    local vram_used vram_total gtt_used gtt_total busy real_used sys_total
    local power temp_edge clk_core clk_mem vram_pct real_pct

    vram_used=$(read_int "$IGPU_DRM/mem_info_vram_used")
    vram_total=$(read_int "$IGPU_DRM/mem_info_vram_total")
    gtt_used=$(read_int "$IGPU_DRM/mem_info_gtt_used")
    gtt_total=$(read_int "$IGPU_DRM/mem_info_gtt_total")
    busy=$(read_int "$IGPU_DRM/gpu_busy_percent")

    real_used=$(( vram_used + gtt_used ))
    sys_total=$(awk '/MemTotal/{print $2*1024}' /proc/meminfo)
    host_total=$(( sys_total + vram_total ))

    power=$(read_int "$IGPU_HWMON/power1_average")
    temp_edge=$(read_int "$IGPU_HWMON/temp1_input")
    clk_core=$(read_int "$IGPU_HWMON/freq1_input")
    clk_mem=$(read_int "$IGPU_HWMON/freq2_input")

    vram_pct=$(awk -v u="$vram_used" -v t="$vram_total" 'BEGIN{ if(t>0) printf "%.1f", 100*u/t; else print 0 }')
    real_pct=$(awk -v u="$real_used" -v ht="$host_total" 'BEGIN{ if(ht>0) printf "%.1f", 100*u/ht; else print 0 }')

    frame_append "\n%siGPU: Radeon 780M / gfx1103 (card2)%s\n" "$BOLD$CYAN" "$RESET"
    frame_append "GPU busy:        %s%5.1f%%%s  %s\n" \
        "$(color_pct "$busy")" "$busy" "$RESET" "$(gpu_bar "$busy")"
    frame_append "Temp (edge):     %s%5.1f C%s\n" "$(color_temp "$temp_edge")" "$(awk -v x="$temp_edge" 'BEGIN{ printf "%.1f", x/1000 }')" "$RESET"
    frame_append "Power:           %5.1f W\n" "$(awk -v x="$power" 'BEGIN{ printf "%.1f", x/1000000 }')"
    frame_append "Core / Mem clk:  %4d MHz / %4d MHz\n" "$((clk_core/1000000))" "$((clk_mem/1000000))"
    frame_append "rocm-smi VRAM%%  (misleading): %5.1f%%  %6.2f / %6.2f GiB\n" \
        "$vram_pct" \
        "$(awk -v x="$vram_used" 'BEGIN{ printf "%.2f", x/1073741824 }')" \
        "$(awk -v x="$vram_total" 'BEGIN{ printf "%.2f", x/1073741824 }')"
    frame_append "GTT used:                     %6.2f / %6.2f GiB\n" \
        "$(awk -v x="$gtt_used" 'BEGIN{ printf "%.2f", x/1073741824 }')" \
        "$(awk -v x="$gtt_total" 'BEGIN{ printf "%.2f", x/1073741824 }')"
    frame_append "REAL used (vram+gtt): %s%6.2f GiB (%5.1f%% of host RAM pool = VM RAM + iGPU carveout)%s\n" \
        "$(color_pct "$real_pct")" \
        "$(awk -v x="$real_used" 'BEGIN{ printf "%.2f", x/1073741824 }')" \
        "$real_pct" "$RESET"
    frame_append "Host RAM pool:        %6.2f GiB  (VM: %6.2f GiB + carveout: %6.2f GiB)\n" \
        "$(awk -v x="$host_total" 'BEGIN{ printf "%.2f", x/1073741824 }')" \
        "$(awk -v x="$sys_total" 'BEGIN{ printf "%.2f", x/1073741824 }')" \
        "$(awk -v x="$vram_total" 'BEGIN{ printf "%.2f", x/1073741824 }')"
}

interval=${1:-2}
if ! [[ "$interval" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
    echo "Usage: $0 [<interval_seconds>]" >&2
    exit 1
fi

# Use the alternate screen buffer so the terminal composes the whole frame
# off-screen and swaps it in instantly. Hide the cursor while refreshing.
# Restore both on exit so the shell prompt returns cleanly.
cleanup() {
    printf '\e[?25h\e[?1049l'
}
trap cleanup EXIT
printf '\e[?1049h\e[?25l'

while true; do
    FRAME=""
    frame_append '\e[H\e[J'
    frame_append "Every %.1fs: %s\n\n" "$interval" "$0"
    read_egpu
    read_igpu
    frame_append "\n%sPress Ctrl-C to quit.%s\n" "$BOLD" "$RESET"
    printf '%s' "$FRAME"
    sleep "$interval"
done
