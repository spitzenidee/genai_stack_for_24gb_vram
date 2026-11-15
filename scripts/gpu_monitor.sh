#!/usr/bin/env bash
# Unified GPU + CPU monitor for the genai_stack VM.
# Reads sysfs directly to avoid the rocm-smi parser crashes seen when the iGPU
# returns unsupported/None sclk values.
# CPU utilization (htop-style per-thread bars) is computed from /proc/stat
# deltas between refresh frames.
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
FAINT=$'\e[2m'
RESET=$'\e[0m'

# --- Sparkline configuration (adjust to taste) ------------------------------
# Every sparkline is SPARK_N frames long and starts at column SPARK_COL, so
# all sparklines line up vertically (rows are right-padded to that column).
SPARK_N=15
SPARK_COL=59
# Min/max ranges for the non-percentage sparklines (percentage metrics — busy,
# VRAM, power % of cap, fan, swap — scale 0–100 naturally). Values below min
# render as ▁, above max render as █ (clamped).
SPARK_TEMP_MIN=0
SPARK_TEMP_MAX=100      # °C: eGPU edge/junction/mem, iGPU edge
SPARK_CORECLK_MIN=0
SPARK_CORECLK_MAX=3000  # MHz: eGPU core clock
SPARK_MEMCLK_MIN=0
SPARK_MEMCLK_MAX=2500   # MHz: eGPU mem clock (sparkline dropped per user decision 2026-10-24)
SPARK_IGPU_PWR_MIN=0
SPARK_IGPU_PWR_MAX=80   # W: iGPU power

# Global frame buffer: build the whole screen in memory, print once per refresh.
FRAME=""

frame_append() {
    local chunk
    printf -v chunk "$@"
    FRAME+="$chunk"
}

read_int() {
    local v=""
    [[ -r "$1" ]] || { echo 0; return; }
    read -r v < "$1" || true
    echo "${v:-0}"
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

# Return color for a percentage 0-100.
# Compared in integer tenths so no external tool (bc/awk) is forked per call.
color_pct() {
    local p=${1:-0}
    [[ "$p" =~ ^-?[0-9]+([.][0-9]+)?$ ]] || p=0
    [[ "$p" == -* ]] && p=0
    local p10 frac
    if [[ "$p" == *.* ]]; then
        frac=${p#*.}
        p10=$(( 10 * 10#${p%%.*} + 10#${frac:0:1} ))
    else
        p10=$(( 10 * 10#$p ))
    fi
    if (( p10 >= 900 )); then
        echo "$RED"
    elif (( p10 >= 700 )); then
        echo "$YELLOW"
    else
        echo "$GREEN"
    fi
}

bar() {
    local pct=$1
    local width=${2:-20}
    local int=${pct%%.*}
    [[ "$int" =~ ^[0-9]+$ ]] || int=0
    local filled=$(( int * width / 100 ))
    (( filled > width )) && filled=$width
    local empty=$(( width - filled ))
    local bar="["
    for ((i=0; i<filled; i++)); do bar+="="; done
    for ((i=0; i<empty; i++)); do bar+=" "; done
    bar+="]"
    echo "$bar"
}

# htop-style gauge: [||||||||| 30.1G/31.3G] — a bar with a right-aligned
# used/total overlay (the text sits inside the bar's right edge). Values in kB.
# Pure bash (no forks).
htop_gauge() {
    local used_kb=$1 total_kb=$2 width=${3:-20}
    local u10 t10 txt textlen barwidth filled empty bar
    u10=$(( used_kb * 10 / 1048576 ))
    t10=$(( total_kb * 10 / 1048576 ))
    txt="$(($u10/10)).$(($u10%10))G/$(($t10/10)).$(($t10%10))G"
    textlen=${#txt}
    barwidth=$(( width - textlen ))
    (( barwidth < 0 )) && barwidth=0
    if (( total_kb > 0 )); then
        filled=$(( used_kb * barwidth / total_kb ))
        (( filled > barwidth )) && filled=$barwidth
    else
        filled=0
    fi
    empty=$(( barwidth - filled ))
    bar="["
    for ((i=0; i<filled; i++)); do bar+="|"; done
    for ((i=0; i<empty; i++)); do bar+=" "; done
    bar+="$txt]"
    echo "$bar"
}

# Sparkline: SPARK_N-frame rolling window per metric, rendered as Unicode
# blocks (▁▂▃▄▅▆▇█). Appended to a gauge line to show the trend (Option A).
# Pure bash. Sets SPARK_OUT (NOT echo) so the history persists in the current
# shell — a $(...) subshell would discard the SPARK[] update every frame.
# By default the value is a 0–100 percentage; with optional min/max the value
# is mapped from [min, max] onto the 0–100 scale (clamped) for the
# non-percentage metrics (temps, clocks, power).
declare -A SPARK=()
SPARK_OUT=""
spark() {
    local key=$1 val=$2 min=${3:-0} max=${4:-100}
    local int=${val%%.*}
    [[ "$int" =~ ^-?[0-9]+$ ]] || int=0
    local scaled
    if (( max > min )); then
        scaled=$(( (int - min) * 100 / (max - min) ))
    else
        scaled=0
    fi
    (( scaled < 0 )) && scaled=0
    (( scaled > 100 )) && scaled=100
    local hist="${SPARK[$key]:-} $scaled"
    local -a parts
    read -r -a parts <<< "$hist"
    if (( ${#parts[@]} > SPARK_N )); then
        parts=("${parts[@]: -SPARK_N}")
    fi
    SPARK[$key]="${parts[*]}"
    local out="" v level
    for v in "${parts[@]}"; do
        level=$(( v * 8 / 100 ))
        (( level > 7 )) && level=7
        case $level in
            0) out+="▁" ;; 1) out+="▂" ;; 2) out+="▃" ;; 3) out+="▄" ;;
            4) out+="▅" ;; 5) out+="▆" ;; 6) out+="▇" ;; 7) out+="█" ;;
        esac
    done
    SPARK_OUT=$out
}

# Render a line with its sparkline aligned at column SPARK_COL: right-pads the
# line so the sparkline starts at SPARK_COL and all sparklines line up
# vertically. $1 = visible line text (no ANSI codes, used for the width),
# $2 = line text to print (may contain ANSI codes, same visible width),
# $3 = sparkline. Sets REPLY (no fork).
spark_row() {
    local vis=$1 row=$2 spark=$3 pad
    pad=$(( SPARK_COL - 1 - ${#vis} ))
    (( pad < 0 )) && pad=0
    printf -v REPLY '%s%*s%s' "$row" "$pad" '' "$spark"
}

# One per-core cell for the 2-column CPU grid: "CPU<n>: [========] 45.0%"
# The index is right-aligned in a 2-char field (CPU%2d) so 1-digit and 2-digit
# core numbers (10+) keep the per-core bars vertically aligned across rows.
# Bar is 10 chars wide (half the full gauge). Sets REPLY (no fork).
core_cell() {
    local idx=$1 pct=$2
    printf -v REPLY 'CPU%2d: %s %5.1f%%' "$idx" "$(bar "$pct" 10)" "$pct"
}

read_egpu() {
    local busy mem_busy vram_used vram_total vram_pct
    local edge junction mem temp_color
    local power power_cap power_pct
    local sclk mclk fan_pct fan_rpm
    local pcie_speed pcie_width pcie_max_width
    local mem_current mem_stat_vals anon file shmem

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
    # pwm1 is a 0–255 duty cycle, not a percentage — scale by pwm1_max (fall
    # back to 255) so the display and the 0–100 fan sparkline are both correct.
    local fan_pwm fan_pwm_max
    fan_pwm=$(read_int "$EGPU_HWMON/pwm1")
    fan_pwm_max=$(read_int "$EGPU_HWMON/pwm1_max")
    (( fan_pwm_max > 0 )) || fan_pwm_max=255
    fan_pct=$(( fan_pwm * 100 / fan_pwm_max ))

    vram_pct=$(awk -v u="$vram_used" -v t="$vram_total" 'BEGIN{ if(t>0) printf "%.1f", 100*u/t; else print 0 }')
    power_pct=$(awk -v p="$power" -v c="$power_cap" 'BEGIN{ if(c>0) printf "%.1f", 100*p/c; else print 0 }')

    frame_append "%seGPU: AMD Radeon 7900 XTX (card1)%s\n" "$BOLD$CYAN" "$RESET"
    local c v b vu vt
    c=$(color_pct "$busy"); printf -v v '%5.1f%%' "$busy"; b=$(bar "$busy")
    spark egpu_core "$busy"
    spark_row "GPU busy:        ${v}  ${b}" "GPU busy:        ${c}${v}${RESET}  ${b}" "$SPARK_OUT"
    frame_append '%s\n' "$REPLY"
    c=$(color_pct "$mem_busy"); printf -v v '%5.1f%%' "$mem_busy"; b=$(bar "$mem_busy")
    spark egpu_mem "$mem_busy"
    spark_row "Mem busy:        ${v}  ${b}" "Mem busy:        ${c}${v}${RESET}  ${b}" "$SPARK_OUT"
    frame_append '%s\n' "$REPLY"
    c=$(color_pct "$vram_pct"); printf -v v '%5.1f%%' "$vram_pct"
    vu=$(awk -v x="$vram_used" 'BEGIN{ printf "%6.2f", x/1073741824 }')
    vt=$(awk -v x="$vram_total" 'BEGIN{ printf "%6.2f", x/1073741824 }')
    spark egpu_vram "$vram_pct"
    spark_row "VRAM used:       ${v}   ${vu} / ${vt} GiB" \
              "VRAM used:       ${c}${v}${RESET}   ${vu} / ${vt} GiB" "$SPARK_OUT"
    frame_append '%s\n' "$REPLY"
    # Feature 4: host RAM used by the eGPU llama-server container (footprint, no spill framing).
    if [[ -n "$EGPU_CGROUP" && -r "$EGPU_CGROUP/memory.current" ]]; then
        mem_current=$(cat "$EGPU_CGROUP/memory.current" 2>/dev/null || echo 0)
        frame_append "Host RAM (llama):  %s GiB\n" \
            "$(awk -v x="$mem_current" 'BEGIN{ printf "%.2f", x/1073741824 }')"
        mem_stat_vals=$(awk '/^anon /{a=$2} /^file /{f=$2} /^shmem /{s=$2} END{printf "%.2f %.2f %.2f", a/1073741824, f/1073741824, s/1073741824}' "$EGPU_CGROUP/memory.stat" 2>/dev/null)
        if [[ -n "$mem_stat_vals" ]]; then
            read -r anon file shmem <<< "$mem_stat_vals"
            frame_append "  anon %s · file %s · shmem %s GiB\n" "$anon" "$file" "$shmem"
        fi
    else
        frame_append "Host RAM (llama):  n/a\n"
    fi
    # Feature 1: PCIe link status (static health check — flags link degradation).
    pcie_speed=$(cat "$EGPU_DRM/current_link_speed" 2>/dev/null || echo "")
    pcie_width=$(cat "$EGPU_DRM/current_link_width" 2>/dev/null || echo "")
    pcie_max_width=$(cat "$EGPU_DRM/max_link_width" 2>/dev/null || echo "")
    if [[ -n "$pcie_speed" && -n "$pcie_width" && -n "$pcie_max_width" ]]; then
        frame_append "PCIe link:       %s x%s (max x%s)\n" "$pcie_speed" "$pcie_width" "$pcie_max_width"
    else
        frame_append "PCIe link:       n/a\n"
    fi
    local pw pc pp sc mc tv
    pw=$(awk -v x="$power" 'BEGIN{ printf "%6.2f", x/1000000 }')
    pc=$(awk -v x="$power_cap" 'BEGIN{ printf "%6.2f", x/1000000 }')
    printf -v pp '%5.1f' "$power_pct"
    spark egpu_power "$power_pct"
    spark_row "Power:           ${pw} / ${pc} W (${pp}% of cap)" \
              "Power:           ${pw} / ${pc} W (${pp}% of cap)" "$SPARK_OUT"
    frame_append '%s\n' "$REPLY"
    printf -v sc '%4d' "$sclk"
    printf -v mc '%4d' "$mclk"
    spark egpu_coreclk "$sclk" "$SPARK_CORECLK_MIN" "$SPARK_CORECLK_MAX"
    spark_row "Core / Mem clk:  ${sc} MHz / ${mc} MHz" \
              "Core / Mem clk:  ${sc} MHz / ${mc} MHz" "$SPARK_OUT"
    frame_append '%s\n' "$REPLY"
    # Voltage (vddgfx) + offset (lact OD_VDDGFX_OFFSET; degrades to n/a when
    # the file/key is missing — same read as gpu_error_watch.sh).
    local vddgfx egpu_offset
    vddgfx=$(read_int "$EGPU_HWMON/in0_input")
    egpu_offset=$(grep -A1 OD_VDDGFX_OFFSET "$EGPU_DRM/pp_od_clk_voltage" 2>/dev/null | tail -1 | tr -d ' ' || echo "n/a")
    frame_append "Voltage:         %s mV (offset %s)\n" "$vddgfx" "$egpu_offset"
    c=$(color_temp "$edge"); tv=$(awk -v x="$edge" 'BEGIN{ printf "%5.1f", x/1000 }')
    spark egpu_edge "$(( edge / 1000 ))" "$SPARK_TEMP_MIN" "$SPARK_TEMP_MAX"
    spark_row "Edge temp:       ${tv} C" "Edge temp:       ${c}${tv}${RESET} C" "$SPARK_OUT"
    frame_append '%s\n' "$REPLY"
    c=$(color_temp "$junction"); tv=$(awk -v x="$junction" 'BEGIN{ printf "%5.1f", x/1000 }')
    spark egpu_junc "$(( junction / 1000 ))" "$SPARK_TEMP_MIN" "$SPARK_TEMP_MAX"
    spark_row "Junction temp:   ${tv} C" "Junction temp:   ${c}${tv}${RESET} C" "$SPARK_OUT"
    frame_append '%s\n' "$REPLY"
    c=$(color_temp "$mem"); tv=$(awk -v x="$mem" 'BEGIN{ printf "%5.1f", x/1000 }')
    spark egpu_memtemp "$(( mem / 1000 ))" "$SPARK_TEMP_MIN" "$SPARK_TEMP_MAX"
    spark_row "Mem temp:        ${tv} C" "Mem temp:        ${c}${tv}${RESET} C" "$SPARK_OUT"
    frame_append '%s\n' "$REPLY"
    spark egpu_fan "$fan_pct"
    spark_row "Fan:             ${fan_pct}% (${fan_rpm} RPM)" \
              "Fan:             ${fan_pct}% (${fan_rpm} RPM)" "$SPARK_OUT"
    frame_append '%s\n' "$REPLY"
}

read_igpu() {
    local vram_used vram_total gtt_used busy real_used sys_total
    local power temp_edge clk_core clk_mem real_pct

    vram_used=$(read_int "$IGPU_DRM/mem_info_vram_used")
    vram_total=$(read_int "$IGPU_DRM/mem_info_vram_total")
    gtt_used=$(read_int "$IGPU_DRM/mem_info_gtt_used")
    busy=$(read_int "$IGPU_DRM/gpu_busy_percent")

    real_used=$(( vram_used + gtt_used ))
    sys_total=$(awk '/MemTotal/{print $2*1024}' /proc/meminfo)
    host_total=$(( sys_total + vram_total ))

    power=$(read_int "$IGPU_HWMON/power1_average")
    temp_edge=$(read_int "$IGPU_HWMON/temp1_input")
    clk_core=$(read_int "$IGPU_HWMON/freq1_input")
    clk_mem=$(read_int "$IGPU_HWMON/freq2_input")

    real_pct=$(awk -v u="$real_used" -v ht="$host_total" 'BEGIN{ if(ht>0) printf "%.1f", 100*u/ht; else print 0 }')

    frame_append "\n%siGPU: Radeon 780M / gfx1103 (card2)%s\n" "$BOLD$CYAN" "$RESET"
    local c v b tv pw
    c=$(color_pct "$busy"); printf -v v '%5.1f%%' "$busy"; b=$(bar "$busy")
    spark igpu_core "$busy"
    spark_row "GPU busy:        ${v}  ${b}" "GPU busy:        ${c}${v}${RESET}  ${b}" "$SPARK_OUT"
    frame_append '%s\n' "$REPLY"
    c=$(color_temp "$temp_edge"); tv=$(awk -v x="$temp_edge" 'BEGIN{ printf "%5.1f", x/1000 }')
    spark igpu_temp "$(( temp_edge / 1000 ))" "$SPARK_TEMP_MIN" "$SPARK_TEMP_MAX"
    spark_row "Temp (edge):     ${tv} C" "Temp (edge):     ${c}${tv}${RESET} C" "$SPARK_OUT"
    frame_append '%s\n' "$REPLY"
    pw=$(awk -v x="$power" 'BEGIN{ printf "%5.1f", x/1000000 }')
    spark igpu_power "$(( power / 1000000 ))" "$SPARK_IGPU_PWR_MIN" "$SPARK_IGPU_PWR_MAX"
    spark_row "Power:           ${pw} W" "Power:           ${pw} W" "$SPARK_OUT"
    frame_append '%s\n' "$REPLY"
    frame_append "Core / Mem clk:  %4d MHz / %4d MHz\n" "$((clk_core/1000000))" "$((clk_mem/1000000))"
    frame_append "Voltage:         %s mV\n" "$(read_int "$IGPU_HWMON/in0_input")"
    frame_append "REAL used (vram+gtt): %s%6.2f GiB (%5.1f%% of host pool)%s\n" \
        "$(color_pct "$real_pct")" \
        "$(awk -v x="$real_used" 'BEGIN{ printf "%.2f", x/1073741824 }')" \
        "$real_pct" "$RESET"
    frame_append "Host RAM pool:        %6.2f GiB  (VM: %6.2f GiB + carveout: %6.2f GiB)\n" \
        "$(awk -v x="$host_total" 'BEGIN{ printf "%.2f", x/1073741824 }')" \
        "$(awk -v x="$sys_total" 'BEGIN{ printf "%.2f", x/1073741824 }')" \
        "$(awk -v x="$vram_total" 'BEGIN{ printf "%.2f", x/1073741824 }')"
}

# --- CPU section (htop-style per-thread meters from /proc/stat) ----------

# Previous /proc/stat snapshot; empty until the first frame.
PREV_STAT=""

# Previous per-PID "pid ticks" (utime+stime) snapshot for instantaneous
# top-3 %CPU deltas; empty until the first frame. PREV_PROCS_T = sample time
# in µs (EPOCHREALTIME) for the Δt denominator.
PREV_PROCS=""
PREV_PROCS_T=""

# Previous /proc/diskstats snapshot for the I/O device:
# "reads rsect writes wsect iotime_ms" (fields 4 6 8 10 13). Empty until the
# first frame. PREV_IO_SECS = SECONDS at sample time (for the Δt denominator).
PREV_IO=""
PREV_IO_SECS=0

# Snapshot the /proc/diskstats line for IO_DEV (pure bash, no fork).
# Emits "reads rsect writes wsect iotime_ms" (1-indexed fields 4 6 8 10 13);
# empty when IO_DEV is unset. Uses read -ra (array) rather than `set --` so
# the multi-digit fields are not mis-parsed as $1+"0" under POSIX splitting.
sample_diskstats() {
    local line
    local -a f
    [[ -n "$IO_DEV" ]] || return 0
    while IFS= read -r line; do
        read -ra f <<< "$line"
        if [[ "${f[2]}" == "$IO_DEV" ]]; then
            printf '%s %s %s %s %s' "${f[3]}" "${f[5]}" "${f[7]}" "${f[9]}" "${f[12]}"
            return 0
        fi
    done < /proc/diskstats
    return 0
}

# Snapshot of the CPU lines of /proc/stat (aggregate "cpu" + one line per CPU).
sample_stat() {
    awk '/^cpu/ { print }' /proc/stat
}

# Compute per-CPU usage % from two /proc/stat samples (prev, curr).
# Emits "avg <pct>" (aggregate line) then "<idx> <pct>" per logical CPU.
# iowait is counted as idle (not busy).
# Note: two process-substitution file operands (not a single pipe) so the
# NR==FNR split between the prev and curr samples works.
cpu_deltas() {
    awk '
        NR==FNR {
            for (i = 2; i <= NF; i++) prev[FNR-1, i] = $i
            next
        }
        {
            idx = ($1 == "cpu") ? "avg" : substr($1, 4)
            total = 0
            for (i = 2; i <= NF; i++) {
                d = $i - prev[FNR-1, i]
                if (d < 0) d = 0
                total += d
            }
            idle = ($5 - prev[FNR-1, 5]) + ($6 - prev[FNR-1, 6])
            if (idle < 0) idle = 0
            pct = (total > 0) ? 100 * (1 - idle / total) : 0
            if (pct < 0) pct = 0
            if (pct > 100) pct = 100
            printf "%s %.1f\n", idx, pct
            if (idx == "avg") {
                # iowait % (field 6) — same sample, no extra reads.
                iow = $6 - prev[FNR-1, 6]
                if (iow < 0) iow = 0
                iopct = (total > 0) ? 100 * iow / total : 0
                if (iopct < 0) iopct = 0
                if (iopct > 100) iopct = 100
                printf "iowait %.1f\n", iopct
            }
        }' <(printf '%s\n' "$1") <(printf '%s\n' "$2")
}

read_cpu() {
    local curr deltas ncpu idx pct global_pct rows row i half left right
    local -a curr_lines prev_lines pcts
    curr=$(sample_stat)
    readarray -t curr_lines <<< "$curr"
    ncpu=$(( ${#curr_lines[@]} - 1 ))

    # Resync if the CPU count changed between frames (hotplug).
    if [[ -n "$PREV_STAT" ]]; then
        readarray -t prev_lines <<< "$PREV_STAT"
        if (( ${#prev_lines[@]} != ${#curr_lines[@]} )); then
            PREV_STAT=""
        fi
    fi

    global_pct="0.0"
    iowait_pct="0.0"
    pcts=()
    if [[ -n "$PREV_STAT" ]]; then
        deltas=$(cpu_deltas "$PREV_STAT" "$curr")
        while read -r idx pct; do
            if [[ "$idx" == "avg" ]]; then
                global_pct=$pct
            elif [[ "$idx" == "iowait" ]]; then
                iowait_pct=$pct
            else
                pcts[$idx]=$pct
            fi
        done <<< "$deltas"
    fi
    # Fill any gaps with 0.0 (first frame, or a core missing from the deltas).
    for ((i = 0; i < ncpu; i++)); do
        pcts[$i]="${pcts[$i]:-0.0}"
    done

    # 2-column core grid: the overall gauge stays full-width on top; per-core
    # rows are paired (left = i, right = i + half) so a many-core box no longer
    # dominates the screen. Adapts to any core count (odd N -> last row single).
    half=$(( (ncpu + 1) / 2 ))
    rows=""
    for ((i = 0; i < half; i++)); do
        core_cell "$i" "${pcts[$i]}"
        left=$REPLY
        if (( i + half < ncpu )); then
            core_cell "$((i + half))" "${pcts[$((i + half))]}"
            right=$REPLY
            printf -v row '%-28s%s\n' "$left" "$right"
        else
            printf -v row '%s\n' "$left"
        fi
        rows+="$row"
    done

    spark cpu_total "$global_pct"
    local c v b40
    c=$(color_pct "$global_pct")
    printf -v v '%5.1f%%' "$global_pct"
    b40=$(bar "$global_pct" 38)
    # Label shortened to "CPU"; the overall gauge spans both core-grid columns:
    # it starts at the first core bar (col 8) and ends at the second core bar's
    # closing bracket (col 47) = 40 chars total (38 inner + 2 brackets).
    spark_row "CPU    ${b40} ${v}" "${BOLD}${CYAN}CPU${RESET}    ${b40} ${c}${v}${RESET}" "$SPARK_OUT"
    frame_append "\n%s\n" "$REPLY"
    frame_append '%s\n' "$rows"
    if read -r la1 la5 la15 _ < /proc/loadavg 2>/dev/null; then
        frame_append '%-19s%s %s %s  (1/5/15 min)\n' "loadavg:" "$la1" "$la5" "$la15"
    fi
    # Mem/Swp gauges (htop-style) — overall host RAM + swap pressure.
    # "used" = total - available (the htop definition: what is not reclaimable).
    local mi mem_total mem_avail swap_total swap_free
    local mem_used swap_used mem_pct swap_pct mem_pct_s swap_pct_s
    mi=$(awk '/^MemTotal:/{t=$2} /^MemAvailable:/{a=$2} /^SwapTotal:/{st=$2} /^SwapFree:/{sf=$2} END{print t, a, st, sf}' /proc/meminfo)
    read -r mem_total mem_avail swap_total swap_free <<< "$mi"
    mem_total=${mem_total:-0}; mem_avail=${mem_avail:-0}
    swap_total=${swap_total:-0}; swap_free=${swap_free:-0}
    mem_used=$(( mem_total - mem_avail ))
    swap_used=$(( swap_total - swap_free ))
    if (( mem_total > 0 )); then mem_pct=$(( mem_used * 1000 / mem_total )); else mem_pct=0; fi
    if (( swap_total > 0 )); then swap_pct=$(( swap_used * 1000 / swap_total )); else swap_pct=0; fi
    mem_pct_s="$(($mem_pct/10)).$(($mem_pct%10))"
    swap_pct_s="$(($swap_pct/10)).$(($swap_pct%10))"
    local c mg sg
    c=$(color_pct "$mem_pct_s"); mg=$(htop_gauge "$mem_used" "$mem_total")
    spark mem "$mem_pct_s"
    spark_row "Mem:               ${mg}" "Mem:               ${c}${mg}${RESET}" "$SPARK_OUT"
    frame_append '%s\n' "$REPLY"
    c=$(color_pct "$swap_pct_s"); sg=$(htop_gauge "$swap_used" "$swap_total")
    spark swp "$swap_pct_s"
    spark_row "Swp:               ${sg}" "Swp:               ${c}${sg}${RESET}" "$SPARK_OUT"
    frame_append '%s\n' "$REPLY"
    # SSD I/O load (device-busy gauge + throughput + IOPS) from /proc/diskstats
    # deltas, and iowait % from /proc/stat (already sampled — no extra reads).
    # First frame (no previous sample) shows 0, like the CPU deltas.
    local io_curr io_util io_mibs io_iops
    io_util="0.0"; io_mibs="0.0"; io_iops="0"
    io_curr=$(sample_diskstats)
    if [[ -n "$PREV_IO" && -n "$io_curr" ]]; then
        local pr psr pw_ psw pio cr csr cw_ csw cio
        read -r pr psr pw_ psw pio <<< "$PREV_IO"
        read -r cr csr cw_ csw cio <<< "$io_curr"
        local dt_ms=$(( (SECONDS - PREV_IO_SECS) * 1000 ))
        (( dt_ms > 0 )) || dt_ms=$(( ${interval%%.*} * 1000 ))
        local io_vals
        io_vals=$(awk -v dt="$dt_ms" \
            -v dio="$(( cio - pio ))" \
            -v dsec="$(( (csr - psr) + (csw - psw) ))" \
            -v dops="$(( (cr - pr) + (cw_ - pw_) ))" 'BEGIN{
                util = (dt > 0) ? 100 * dio / dt : 0
                if (util < 0) util = 0; if (util > 100) util = 100
                mibs = (dt > 0) ? dsec * 512 / dt / 1048576 : 0
                iops = (dt > 0) ? dops * 1000 / dt : 0
                printf "%.1f %.1f %.0f", util, mibs, iops
            }')
        read -r io_util io_mibs io_iops <<< "$io_vals"
    fi
    PREV_IO=$io_curr
    PREV_IO_SECS=$SECONDS
    if [[ -n "$IO_DEV" ]]; then
        local io_b io_v io_m io_i
        c=$(color_pct "$io_util")
        io_b=$(bar "$io_util" 12)
        printf -v io_v '%5.1f%%' "$io_util"
        printf -v io_m '%5.1f' "$io_mibs"
        printf -v io_i '%5.0f' "$io_iops"
        spark io "$io_util"
        spark_row "I/O (${IO_DEV}): ${io_b} ${io_v}  ${io_m} MiB/s  ${io_i} iops" \
                  "I/O (${IO_DEV}): ${c}${io_b}${RESET} ${c}${io_v}${RESET}  ${io_m} MiB/s  ${io_i} iops" \
                  "$SPARK_OUT"
        frame_append '%s\n' "$REPLY"
    else
        frame_append "I/O:               n/a\n"
    fi
    frame_append "  iowait:          %5.1f%%\n" "$iowait_pct"
    # Top-3 CPU processes by instantaneous %CPU (delta between frames, like
    # top/htop): one awk pass over /proc/[0-9]*/stat (no extra external tools
    # in the frame loop). Vanished PIDs are skipped (getline), so a process
    # exiting between glob expansion and the read can no longer empty the list.
    local t_cur dt_ticks top_out line top_procs tpct tpid tcomm
    if [[ -n "${EPOCHREALTIME:-}" ]]; then
        t_cur=${EPOCHREALTIME/./}              # integer µs (bash ≥ 5)
    else
        t_cur=$(( SECONDS * 1000000 ))         # coarse fallback (bash < 5)
    fi
    dt_ticks=0
    if [[ -n "$PREV_PROCS_T" ]]; then
        dt_ticks=$(( (t_cur - PREV_PROCS_T) / 10000 ))   # 100 Hz ticks
    fi
    top_out=$(awk -v dt="$dt_ticks" -v prev="$PREV_PROCS" '
      BEGIN {
        n = split(prev, pl, "\n")
        for (i = 1; i <= n; i++) {
          if (pl[i] == "") continue
          split(pl[i], a, " ")
          prev_ticks[a[1]] = a[2]
        }
      }
      {
        # $0 = one /proc/<pid>/stat path from the glob
        if ((getline line < $0) <= 0) next     # exited since glob: skip, no fatal
        close($0)
        np = split($0, parts, "/"); pid = parts[np-1]
        match(line, /\((.*)\)/); comm = substr(line, RSTART+1, RLENGTH-2)
        split(substr(line, RSTART+RLENGTH+1), f, " ")
        ticks = f[12] + f[13]
        d = (pid in prev_ticks) ? ticks - prev_ticks[pid] : 0
        if (d < 0) d = 0                       # PID reuse: clamp
        pct = (dt > 0) ? 100 * d / dt : 0      # may exceed 100 (multi-thread), like top
        cnt++; P[cnt] = pct; N[cnt] = pid; T[cnt] = ticks; C[cnt] = comm
      }
      END {
        if (dt > 0) {
          for (i = 1; i <= 3 && i <= cnt; i++) {
            bi = i
            for (j = i + 1; j <= cnt; j++) if (P[j] > P[bi]) bi = j
            printf "  %5.1f%%  %-8d  %s\n", P[bi], N[bi], C[bi]
            P[bi] = -1
          }
        }
        for (i = 1; i <= cnt; i++) printf "S %s %s\n", N[i], T[i]
      }' <(printf '%s\n' /proc/[0-9]*/stat) || true)
    top_procs=""
    PREV_PROCS=""
    while IFS= read -r line; do
        if [[ "$line" == "S "* ]]; then
            PREV_PROCS+="${line#S }"$'\n'
        else
            top_procs+="$line"$'\n'
        fi
    done <<< "$top_out"
    PREV_PROCS_T=$t_cur
    frame_append "\nTop CPU procs:\n"
    local rss rbytes gib100 mib10 spages
    while read -r tpct tpid tcomm; do
        [[ -n "$tpct" ]] || continue
        # RSS from /proc/<pid>/statm (field 2 = resident pages × 4096 B).
        # Pure bash (no fork); n/a if the process exited between selection
        # and read.
        rss="n/a"
        if [[ -r "/proc/${tpid}/statm" ]]; then
            read -r _ spages _ < "/proc/${tpid}/statm" 2>/dev/null || spages=""
            if [[ "${spages:-}" =~ ^[0-9]+$ ]]; then
                rbytes=$(( spages * 4096 ))
                if (( rbytes >= 1073741824 )); then
                    gib100=$(( rbytes * 100 / 1073741824 ))
                    rss="$(($gib100/100)).$(printf '%02d' $((gib100%100))) GiB"
                else
                    mib10=$(( rbytes * 10 / 1048576 ))
                    rss="$(($mib10/10)).$(($mib10%10)) MiB"
                fi
            fi
        fi
        frame_append "  %s%s%s  %s  %s  %12s\n" "$(color_pct "${tpct%}")" "$tpct" "$RESET" "$tpid" "$tcomm" "$rss"
    done <<< "$top_procs"
    PREV_STAT=$curr
}

interval=${1:-2}
if ! [[ "$interval" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
    echo "Usage: $0 [<interval_seconds>]" >&2
    exit 1
fi

# Feature 4: resolve the eGPU llama-server cgroup path ONCE at startup.
# The raw <CID> is not a valid cgroup path; the system.slice/docker-<CID>.scope
# form is. If the container is down, EGPU_CGROUP stays empty and the lines show n/a.
EGPU_CGROUP=""
if cid=$(docker inspect --format '{{.Id}}' llamacpp-egpu 2>/dev/null); then
    cgp="/sys/fs/cgroup/system.slice/docker-${cid}.scope"
    [[ -d "$cgp" ]] && EGPU_CGROUP="$cgp"
fi

# I/O device resolved ONCE at startup: the largest real disk in /sys/block.
# loop*/ram*/zram*/sr* (CD-ROM)/dm-* (device-mapper virtual) are excluded so
# the physical disk is monitored (on this host: sda; dm-0 is an LVM volume on
# top of it and would double-count). Empty when no real disk is found — the
# I/O row then shows n/a.
IO_DEV=""
io_best=0
for d in /sys/block/*/size; do
    [[ -e "$d" ]] || continue
    name=${d#/sys/block/}; name=${name%/size}
    case $name in loop*|ram*|zram*|sr*|dm-*) continue ;; esac
    sz=$(read_int "$d")
    if (( sz > io_best )); then io_best=$sz; IO_DEV=$name; fi
done

# Use the alternate screen buffer so the terminal composes the whole frame
# off-screen and swaps it in instantly. Hide the cursor while refreshing.
# Restore both on exit so the shell prompt returns cleanly.
cleanup() {
    printf '\e[?25h\e[?1049l'
    stty echo icanon < /dev/tty 2>/dev/null || true
}
trap cleanup EXIT
printf '\e[?1049h\e[?25l'
# Feature 2: quiet, canonical-off so a single keypress is available immediately.
stty -echo -icanon < /dev/tty 2>/dev/null || true

while true; do
    FRAME=""
    frame_append '\e[H\e[J'
    frame_append "Every %.1fs: %s\n\n" "$interval" "$0"
    read_egpu
    read_igpu
    read_cpu
    frame_append "\n%sPress q to quit (Ctrl-C also works).%s\n" "$BOLD" "$RESET"
    printf '%s' "$FRAME"
    key=""
    IFS= read -rsn1 -t "$interval" key < /dev/tty || true
    case "$key" in q|Q) break ;; esac
done
