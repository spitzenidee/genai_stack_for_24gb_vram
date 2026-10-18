#!/usr/bin/env python3
"""Stress-test the llamacpp-igpu Vulkan backend with a large-context prefill.

Reproduces the vk::Queue::submit: ErrorDeviceLost class reported in:
  - https://github.com/ggml-org/llama.cpp/issues/27306
  - https://github.com/ggml-org/llama.cpp/issues/27076
  - https://github.com/ggml-org/llama.cpp/issues/26447

Tuning notes for Radeon 780M iGPU (gfx1103, UMA/Vulkan):
  - Lower ubatch-size avoids AMDGPU compute-ring watchdog timeouts during
    long-context flash-attention, but greatly reduces prompt-processing speed.
    Example speed ranking at the start of a long-context run:
      ubatch 4096 >> ubatch 512 ~= ubatch 256
  - If speed is more important than avoiding a reboot, raise the kernel
    watchdog timeout so larger ubatch values can finish without triggering
    vk::DeviceLost. Add this to the kernel command line (grub/systemd-boot):
      amdgpu.lockup_timeout=10000,60000,10000,10000
    This raises the compute-ring timeout from 10 s to 60 s. It applies to
    all AMD GPUs in the system (iGPU + eGPU), so genuine hangs take longer
    to recover. Reboot required after changing the cmdline.
  - Alternative without reboot: keep ubatch-size at 256/512 and accept the
    slower prefill speed; 200k+ context has been shown to complete cleanly.

Usage:
  python3 vulkan_stresstest.py --tokens 70000 --url http://localhost:8093/v1/chat/completions
"""

import argparse
import json
import os
import sys
import time

import requests


DEFAULT_URL = os.environ.get("LLAMA_IGPU_URL", "http://localhost:8093/v1/chat/completions")
DEFAULT_MODEL = os.environ.get("LLAMA_IGPU_MODEL", "igpu-Qwen3.6-35B-A3B")


def build_prompt(target_tokens: int) -> str:
    """Return a long neutral text of approximately target_tokens tokens.

    Calibration from an actual Qwen3.6 run:
      1,680,066 chars -> 360,034 tokens
      -> ~4.66 chars/token for this highly repetitive filler text.
    """
    sentence = (
        "The quick brown fox jumps over the lazy dog while seven noisy crows "
        "fly across the deep blue sky. "
    )
    trailing = (
        "\n\nYou have read the passage above. Do not summarize it. Instead, "
        "answer the following question with a single concise sentence: what color was the sky?"
    )

    chars_needed = int(target_tokens * 4.66)
    repeats = max(1, chars_needed // len(sentence))
    text = sentence * repeats
    prompt = text + trailing
    return prompt


def main() -> int:
    parser = argparse.ArgumentParser(description="Stress-test llamacpp-igpu Vulkan backend")
    parser.add_argument("--url", default=DEFAULT_URL, help="llama-server chat completions URL")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="model preset name")
    parser.add_argument("--tokens", type=int, default=70000, help="approximate prompt token count")
    parser.add_argument("--max-tokens", type=int, default=50, help="max completion tokens")
    parser.add_argument("--temperature", type=float, default=0.6, help="sampling temperature")
    parser.add_argument("--timeout", type=int, default=7200, help="HTTP request timeout in seconds")
    args = parser.parse_args()

    print(f"Building prompt of ~{args.tokens} tokens...", flush=True)
    prompt = build_prompt(args.tokens)
    print(f"Prompt length: {len(prompt):,} chars (~{args.tokens:,} tokens requested, ~{len(prompt) // 4.66:,} estimated)", flush=True)

    body = {
        "model": args.model,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": args.max_tokens,
        "temperature": args.temperature,
    }

    print(f"POST {args.url}", flush=True)
    print(f"Model: {args.model}", flush=True)
    start = time.time()
    try:
        response = requests.post(
            args.url,
            headers={"Content-Type": "application/json"},
            data=json.dumps(body),
            timeout=args.timeout,
        )
    except requests.exceptions.Timeout:
        elapsed = time.time() - start
        print(f"\nREQUEST TIMEOUT after {elapsed:.1f}s — possible Vulkan hang/DeviceLost", flush=True)
        return 1
    except requests.exceptions.ConnectionError as exc:
        elapsed = time.time() - start
        print(f"\nCONNECTION ERROR after {elapsed:.1f}s: {exc}", flush=True)
        return 1

    elapsed = time.time() - start
    print(f"\nHTTP status: {response.status_code}", flush=True)
    print(f"Elapsed: {elapsed:.1f}s", flush=True)

    try:
        payload = response.json()
    except Exception:
        payload = None
        print("Raw response:", response.text[:1000], flush=True)

    if payload:
        if "error" in payload:
            print("Server error:", json.dumps(payload["error"], indent=2), flush=True)
            return 1
        if "choices" in payload and payload["choices"]:
            content = payload["choices"][0].get("message", {}).get("content", "")
            print("Completion:", content[:500], flush=True)
            print("\nSTRESS TEST PASSED — no DeviceLost", flush=True)
            return 0

    if response.status_code == 200:
        print("\nSTRESS TEST PASSED — no DeviceLost", flush=True)
        return 0

    print("\nSTRESS TEST FAILED", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
