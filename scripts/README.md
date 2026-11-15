[Back to main README](../README.md)

# Utility scripts

## TL;DR

The `scripts/` directory (plus `hf_download.sh` at the repo root) holds the stack's
operational helpers: the GPU work-mode switcher (`switch-mode.sh`, driven by `make`),
the host GPU monitor (`gpu_monitor.sh`), one-shot llama.cpp benchmark helpers
(`benchmark.sh`, `power_bench.py`), a resumable Hugging Face download helper
(`hf_download.sh`), and the publish/`pi`-wrapper tooling. They are plain host scripts
(no container, no service) — you touch them when switching work modes, watching GPU
load, or re-running a power/performance benchmark.

## What & why

These scripts are the manual layer around the compose stack:

- **Work-mode switching** — the eGPU has no VRAM isolation, so `switch-mode.sh`
  enforces one heavy GPU mode at a time (invoked by the `make` mode targets).
- **Observability** — `gpu_monitor.sh` reads host sysfs directly (no `rocm-smi`
  parser) to show live eGPU + iGPU metrics in a terminal.
- **Benchmarks** — `benchmark.sh` and `power_bench.py` are one-shot helpers for
  finding the power-vs-performance sweet spot; `bench_egpu_ab.py` compares llama.cpp
  rebuilds A/B on the eGPU.
- **Housekeeping** — model downloads (`hf_download.sh`), publishing
  (`publish.sh`), and the `pi-*` session wrappers.

## How it works

All of them run on the **host** (not in a container) from the repo root. The ones that
talk to containers use `docker compose` / `docker exec` against the running stack;
the ones that talk to the GPU read `/sys/class/drm/` and `/proc` directly. Nothing
here is a compose service — there is no build step and no port.

## How to use

| Script                        | Purpose                                                  |
|-------------------------------|----------------------------------------------------------|
| `scripts/switch-mode.sh`      | Stops non-target GPU modes, starts target mode (invoked by the `make` mode targets). |
| `scripts/gpu_monitor.sh`      | Host sysfs monitor for eGPU + iGPU.                      |
| `scripts/benchmark.sh`        | Builds llama.cpp variants from `bench_configs.ini` and benchmarks tokens/s. |
| `scripts/power_bench.py`      | Sweeps GPU power limit via LACT and records tokens/s.    |
| `hf_download.sh`              | Resumable `wget` download helper for GGUF files.         |

I only use `gpu_monitor.sh` and `hf_download.sh` directly - the gpu-monitor script
via a bash alias:

`alias gpumon='/home/<my_user>/docker/genai_stack/scripts/gpu_monitor.sh'`

`switch-mode.sh` is only used via `make` targets, not directly, and both
`benchmark.sh` and `power_bench.py` are one-shot benchmark helpers I had created by
CoPilot to aide with checking on power-vs-performance sweet spots. I have rarely used
them after, but I left them in for reference and in case I might want to pick up
further power-finetuning for any reason.

Usage examples:

```sh
./hf_download.sh <huggingface_url> [target_dir]   # resumable GGUF download (default dir: _dl/)
./scripts/benchmark.sh [bench_configs.ini]        # build + benchmark llama.cpp variants
python3 scripts/power_bench.py                    # power-limit sweep via LACT → CSV
```

## The rest of the directory

| Script | Purpose |
|---|---|
| `scripts/bench_egpu_ab.py` | A/B benchmark for the `llamacpp-egpu` server — compares llama.cpp rebuilds (e.g. rdna r176 vs r205) on the same model + prompts. **Recreates the eGPU llama container per config** — never run it while an agent session runs on the eGPU. |
| `scripts/gpu_error_watch.sh` | Foreground eGPU **error** watcher — prints GPU failure signals immediately as they appear (the "see errors the moment they happen" companion to `gpu_monitor.sh`). |
| `scripts/vulkan_stresstest.py` | Stress-test the `llamacpp-igpu` Vulkan backend with a large-context prefill (reproduces the `ErrorDeviceLost` issue class). |
| `scripts/pi-gromacs` | Interactive `pi` session for GROMACS work — iGPU model pinned, Hindsight fully inert (no memory confounder). |
| `scripts/pi-igpu-bench` | Benchmark the iGPU llama instance with Hindsight fully inert, so tokens/s reflect the GPU alone. |
| `scripts/pi-no-hindsight` | Plain `pi` with Hindsight hooks disabled (baseline sessions). |
| `scripts/publish.sh` | The publish pipeline: private repo → immutable public GitHub snapshots (whitelist `publish.include` + sanitize `publish.sanitize`). |
| `scripts/restore-egpu-rdna-detached.sh` | One-shot: restore `llamacpp-egpu` to the production rdna image after a benchmark left it on vanilla. Takes the eGPU llama-server down briefly — run detached, after any worker session. |
| `scripts/setup-smb-gromacs.sh` | Root-only host setup for the SMB share GROMACS projects use. |
| `scripts/bench_configs.ini` | Config set for `benchmark.sh` (compiler-flag variants). |
| `scripts/bench_eval_prompts.json` | Prompt set for the benchmark/eval runs. |

## Configuration & influence

- **`gpumon` alias** — the everyday entry point for `gpu_monitor.sh` (see above).
- **`bench_configs.ini`** — the llama.cpp build variants `benchmark.sh` iterates over.
- **`DEFAULT_DIR`** — env override for `hf_download.sh`'s target directory (default
  `<repo>/_dl/`).
- **`publish.include` / `publish.sanitize`** (repo root) — the whitelist and the
  deterministic sanitize rules `publish.sh` applies; see `docs/publishing.md`.

## Related

- The GPU tuning daemon `power_bench.py` drives: [lact/README.md](../lact/README.md)
- The work modes `switch-mode.sh` enforces: main README ([../README.md](../README.md),
  "GPU work modes")
- The inference server the benchmarks target: [llamacpp/README.md](../llamacpp/README.md)
- Live metrics the monitor complements: [otel/README.md](../otel/README.md)

[Back to main README](../README.md)
