#!/usr/bin/env bash
# Usage: ./hf_download.sh <huggingface_url> [target_dir]
# Example: ./hf_download.sh https://huggingface.co/ibm-granite/granite-4.0-h-small-GGUF/resolve/main/granite-4.0-h-small-Q5_K_M.gguf

set -euo pipefail

URL="${1:?Usage: $0 <huggingface_url> [target_dir]}"
TARGET_DIR="${2:-/home/spitzem/docker/genai_stack/_dl}"
FILENAME="$(basename "$URL")"
LOG_FILE="$TARGET_DIR/${FILENAME%.gguf}_download.log"

mkdir -p "$TARGET_DIR"

echo "Starting download of $FILENAME"
echo "Target : $TARGET_DIR/$FILENAME"
echo "Log    : $LOG_FILE"

nohup wget \
    --continue \
    --show-progress \
    --progress=bar:force \
    --output-document="$TARGET_DIR/$FILENAME" \
    "$URL" \
    > "$LOG_FILE" 2>&1 &

WGET_PID=$!
echo "PID    : $WGET_PID (saved to ${LOG_FILE%.log}.pid)"
echo $WGET_PID > "${LOG_FILE%.log}.pid"
echo ""
echo "You can safely close this SSH session."
echo "Monitor progress : tail -f $LOG_FILE"
echo "Cancel download  : kill \$(cat ${LOG_FILE%.log}.pid)"
