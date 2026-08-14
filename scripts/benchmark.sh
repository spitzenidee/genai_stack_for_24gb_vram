#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# benchmark.sh — Build & benchmark llama.cpp with different compiler flags
#
# Usage:  ./benchmark.sh [bench_configs.ini]
#
# Reads configs from the INI file, builds a Docker image per config,
# runs llama-server, sends a chat completion request, extracts t/s,
# and writes results back into the INI file as "# result: ..." comments.
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${1:-$SCRIPT_DIR/bench_configs.ini}"
DOCKERFILE_DIR="$SCRIPT_DIR"

# Model to benchmark (tiny = fast load, representative for t/s comparison)
MODEL_DIR="/home/spitzem/docker/genai_stack/hfmodels"
MODEL_FILE="granite-4.0-h-tiny-Q4_K_M.gguf"

# Container settings (match docker-compose.yml)
CONTAINER_NAME="llama-bench-runner"
HOST_PORT=8091          # avoid clash with running llama-server on 8090
CONTAINER_PORT=8091
CPU_LIMIT="7.0"

# Benchmark settings
RUNS=5
HEALTH_TIMEOUT=120      # seconds to wait for /health
PROMPT="Describe yourself in 300 words."

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

log()  { echo ">>> $*"; }
fail() { echo "ERROR: $*" >&2; exit 1; }

require_cmd() {
    command -v "$1" >/dev/null 2>&1 || fail "'$1' is required but not found. Install it first."
}

cleanup_container() {
    docker stop "$CONTAINER_NAME" 2>/dev/null || true
    docker rm -f "$CONTAINER_NAME" 2>/dev/null || true
}

wait_for_health() {
    local elapsed=0
    while (( elapsed < HEALTH_TIMEOUT )); do
        if curl -sf "http://localhost:${HOST_PORT}/health" >/dev/null 2>&1; then
            return 0
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done
    return 1
}

# Send a chat completion and return predicted_per_second via jq
run_inference() {
    local response
    response=$(curl -sf "http://localhost:${HOST_PORT}/v1/chat/completions" \
        -H "Content-Type: application/json" \
        -d '{
            "model": "'"$MODEL_FILE"'",
            "messages": [{"role": "user", "content": "'"$PROMPT"'"}],
            "max_tokens": 512
        }')
    echo "$response" | jq -r '.timings.predicted_per_second'
}

# ---------------------------------------------------------------------------
# INI parser — yields (name, cmake_args) pairs
# ---------------------------------------------------------------------------

parse_configs() {
    local current_name="" current_flags=""
    while IFS= read -r line || [[ -n "$line" ]]; do
        # Strip leading/trailing whitespace
        line="${line#"${line%%[![:space:]]*}"}"
        line="${line%"${line##*[![:space:]]}"}"

        # Skip blank lines and comments
        [[ -z "$line" || "$line" == \#* ]] && continue

        # Section header
        if [[ "$line" =~ ^\[(.+)\]$ ]]; then
            # Emit previous section if any
            if [[ -n "$current_name" ]]; then
                echo "${current_name}|${current_flags}"
            fi
            current_name="${BASH_REMATCH[1]}"
            current_flags=""
        else
            # Accumulate flags (space-separated)
            if [[ -n "$current_flags" ]]; then
                current_flags="$current_flags $line"
            else
                current_flags="$line"
            fi
        fi
    done < "$CONFIG_FILE"
    # Emit last section
    if [[ -n "$current_name" ]]; then
        echo "${current_name}|${current_flags}"
    fi
}

# Write result back into the INI file for a given section
write_result() {
    local name="$1" result_line="$2"
    local tmpfile
    tmpfile=$(mktemp)

    local in_section=0 written=0
    while IFS= read -r line || [[ -n "$line" ]]; do
        # Remove old result line for this section
        if (( in_section )) && [[ "$line" =~ ^#\ result: ]]; then
            continue
        fi

        # Detect entering our target section (literal match, not regex — name may contain + etc.)
        if [[ "$line" == "[${name}]" ]]; then
            in_section=1
            written=0
            echo "$line" >> "$tmpfile"
            continue
        fi

        # Detect leaving our section (next section or EOF-like)
        if (( in_section )) && [[ "$line" =~ ^\[.+\]$ ]]; then
            # Insert result before the next section
            if (( ! written )); then
                echo "$result_line" >> "$tmpfile"
                written=1
            fi
            in_section=0
        fi

        echo "$line" >> "$tmpfile"
    done < "$CONFIG_FILE"

    # If we were still in our section at EOF, append result
    if (( in_section && ! written )); then
        echo "$result_line" >> "$tmpfile"
    fi

    mv "$tmpfile" "$CONFIG_FILE"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

require_cmd docker
require_cmd curl
require_cmd jq

[[ -f "$CONFIG_FILE" ]] || fail "Config file not found: $CONFIG_FILE"

log "Config file: $CONFIG_FILE"
log "Model: $MODEL_DIR/$MODEL_FILE"
log "Runs per config: $RUNS"
echo ""

# Collect all configs first
mapfile -t configs < <(parse_configs)
total=${#configs[@]}

log "Found $total configurations to benchmark"
echo ""

trap cleanup_container EXIT

for idx in "${!configs[@]}"; do
    IFS='|' read -r name cmake_args <<< "${configs[$idx]}"
    num=$((idx + 1))
    tag="$name"

    echo "============================================================"
    log "[$num/$total] Config: $name"
    log "CMAKE_ARGS: $cmake_args"
    echo "============================================================"

    # --- Build ---
    log "Building Docker image llama-bench:$tag ..."
    if ! docker build \
        --no-cache \
        --build-arg CMAKE_ARGS="$cmake_args" \
        -t "llama-bench:$tag" \
        "$DOCKERFILE_DIR"; then
        log "BUILD FAILED for $name — skipping"
        write_result "$name" "# result: BUILD FAILED"
        echo ""
        continue
    fi

    # --- Run container ---
    cleanup_container
    log "Starting container ..."
    docker run -d \
        --name "$CONTAINER_NAME" \
        --cpus="$CPU_LIMIT" \
        --ulimit memlock=-1:-1 \
        -v "$MODEL_DIR:/models:ro" \
        -p "${HOST_PORT}:${CONTAINER_PORT}" \
        "llama-bench:$tag" \
        --model "/models/$MODEL_FILE" \
        --host 0.0.0.0 \
        --port "$CONTAINER_PORT"

    # --- Wait for health ---
    log "Waiting for server to be ready ..."
    if ! wait_for_health; then
        log "HEALTH TIMEOUT for $name — skipping"
        cleanup_container
        write_result "$name" "# result: HEALTH TIMEOUT"
        echo ""
        continue
    fi
    log "Server is ready"

    # --- Warmup ---
    log "Warmup request (discarded) ..."
    run_inference >/dev/null 2>&1 || true

    # --- Benchmark runs ---
    declare -a run_results=()
    for run in $(seq 1 $RUNS); do
        ts=$(run_inference)
        log "  Run $run: ${ts} t/s"
        run_results+=("$ts")
    done

    # --- Compute mean ---
    mean=$(printf '%s\n' "${run_results[@]}" | awk '{ sum += $1; n++ } END { if (n>0) printf "%.2f", sum/n }')
    individual=$(IFS=', '; echo "${run_results[*]}")

    log "Mean: ${mean} t/s"

    # --- Stop container ---
    cleanup_container

    # --- Write result into INI ---
    write_result "$name" "# result: ${individual} → mean: ${mean} t/s"

    # --- Cleanup image to save disk (optional — comment out to keep images) ---
    # docker rmi "llama-bench:$name" 2>/dev/null || true

    echo ""
done

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo ""
echo "============================================================"
echo "  BENCHMARK RESULTS"
echo "============================================================"
printf "%-25s %s\n" "Config" "Result"
printf "%-25s %s\n" "-------------------------" "--------------------"

while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" =~ ^\[(.+)\]$ ]]; then
        current_name="${BASH_REMATCH[1]}"
    fi
    if [[ "$line" =~ ^#\ result:\ (.+)$ ]]; then
        printf "%-25s %s\n" "$current_name" "${BASH_REMATCH[1]}"
    fi
done < "$CONFIG_FILE"

echo ""
log "Results are saved in: $CONFIG_FILE"
