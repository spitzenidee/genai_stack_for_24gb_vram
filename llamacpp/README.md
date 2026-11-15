[Back to main README](../README.md)

# Inference: llama.cpp (ROCm eGPU / Vulkan iGPU)

## TL;DR

Two `llama-server` instances serve GGUF models independently on the two AMD
GPUs: `llamacpp-egpu` (RX 7900 XTX, ROCm/HIP, port `8092`) and
`llamacpp-igpu` (Radeon 780M, Vulkan/RADV, port `8093`, always-on). Models are
downloaded into a bind-mounted weights dir and exposed per-server via
`models-*.ini`. You touch this when you want to add or serve a model, rebuild
the llama.cpp image, or point a client (Open WebUI, Hindsight, an agent) at an
inference endpoint.

## What & why

The inference layer of the stack: local, self-hosted LLM serving with no
external API. Two servers run in parallel because the eGPU (24 GB VRAM) and
the iGPU (a system-memory carve-out) are separate hardware — the eGPU is the
heavy workhorse (large models, agent brains) and the iGPU is an always-on side
channel that never contends for eGPU VRAM. Both expose an OpenAI-compatible
API, so any OpenAI client can talk to them.

## How it works

Two `llama-server` instances serve models independently:

| Service          | GPU   | Backend | Image build                                        | Port |
|------------------|-------|---------|----------------------------------------------------|------|
| `llamacpp-egpu`  | eGPU  | ROCm/HIP | `llamacpp/Dockerfile.rocm` on `Dockerfile.rocm-builder` | 8092 |
| `llamacpp-igpu`  | iGPU  | Vulkan/RADV | `llamacpp/Dockerfile.vulkan`                    | 8093 |

### Build: eGPU (`Dockerfile.rocm-builder` + `Dockerfile.rocm`)

The eGPU build is split into two stages to keep iteration fast:

- `Dockerfile.rocm-builder` — the expensive stage (~20+ min): base
  `rocm/dev-ubuntu-24.04:7.14.1-full`, clones the latest tagged llama.cpp
  release, compiles with `GGML_HIP=ON` for `AMDGPU_TARGETS=gfx1100`
  (Navi 31 / RX 7900 XTX) with `GGML_HIP_MMQ_MFMA` + `GGML_HIP_GRAPHS`.
  Rebuild only when llama.cpp should be updated:
  `docker build --no-cache -f llamacpp/Dockerfile.rocm-builder -t llama-rocm-builder:latest llamacpp`
- `Dockerfile.rocm` — thin runtime stage on top of the cached builder image
  (seconds to rebuild).

### Build: iGPU (`Dockerfile.vulkan`)

- Multi-stage Ubuntu 24.04 image.
- Builds the latest tagged `llama.cpp` release from GitHub.
- Back end: `GGML_VULKAN=ON` (RADV selects the GPU at runtime via the
  bind-mounted render node; no arch-specific compile needed).
- `GGML_NATIVE=OFF` so the binary is portable across host CPUs.
- Runtime image installs `mesa-vulkan-drivers` and points the loader to
  `/usr/share/vulkan/icd.d/radeon_icd.json`.
- The iGPU (Radeon 780M, gfx1103) deliberately stays on Vulkan: ROCm does not
  officially support gfx1103, and Vulkan handles the UMA carve-out well.
  The carve-out is a performance target, not a hard limit — weights/KV that
  spill past it are allocated from the same physical DDR5 system DRAM via
  GTT. They remain usable; the iGPU already talks to system memory, so there
  is no separate VRAM bus to fall back from. Performance may still degrade
  due to allocation/mapping overhead and CPU/VMM contention.

`Dockerfile.cpu` (AVX-512/VNNI CPU-only build) also exists in `llamacpp/` but
is not wired into any compose profile.

### Runtime

Both services are started by `make llama` (the `llama` work mode). The eGPU
service is profile-gated (`llama`); the iGPU service has no profile and runs in
every mode. Each bind-mounts the shared weights dir `llamacpp/hfmodels` to
`/models` and its own `models-*.ini` to `/config/models.ini`.

## How to use

### API

`llama-server` exposes an OpenAI-compatible chat-completions endpoint at
`http://<host>:8092/v1/chat/completions` (and `:8093` for the iGPU).

```bash
# list the configured models
curl http://localhost:8092/v1/models
```

### Rebuild the llama.cpp image

`docker compose build` alone does not refresh the llama.cpp version in the eGPU
image — the ROCm compile lives in the separate `llama-rocm-builder:latest`
image. Use the `rebuild-genai-llama` shell alias to rebuild builder + both
llama services in the correct order:

```bash
alias rebuild-genai-llama="
  cd /home/<user>/docker/genai_stack &&
  docker build --no-cache -f llamacpp/Dockerfile.rocm-builder -t llama-rocm-builder:latest llamacpp &&
  docker compose build llamacpp-egpu llamacpp-igpu &&
  docker compose up -d --force-recreate llamacpp-egpu llamacpp-igpu
"
```

### Download a model from Huggingface and move to the model folder

`hf_download.sh` (repo root) is a small resumable download helper for GGUF
weights: it runs `wget --continue` in the background via `nohup`, so the
download survives closing the SSH session, and interrupted transfers resume
where they left off.

```bash
./hf_download.sh <huggingface_resolve_url> [target_dir]
```

If no target directory is given, files land in `_dl/` (a staging area; the
script writes a `_download.log` and `.pid` file next to each download so
you can monitor with `tail -f` or cancel via `kill $(cat <name>.pid)`).

After the download completes, move the `.gguf` file into
`llamacpp/hfmodels/` — that directory is bind-mounted to `/models` in both
`llamacpp-egpu` and `llamacpp-igpu`, so the weights are visible to both
servers. To actually serve the model, add a `[ModelName]` section for it in
`llamacpp/models-egpu.ini` and/or `llamacpp/models-igpu.ini` (see
Configuration & influence below) and restart the corresponding service. By
adding a specific LLM to the eGPU / iGPU `models.ini` variant you can control
which model is available in which llama.cpp instance. Only LLMs configured in
either `models-egpu.ini` or `models-igpu.ini` will be available, all others
will not be exposed.

## Configuration & influence

### Model configuration (`models-*.ini`)

Production model-configuration files are created from the tracked example
files in `llamacpp/` and bind-mounted into `/config/models.ini`. The examples
tune KV-cache quantization, context length, speculative decoding, and reasoning
budgets.

- `models-egpu.ini` — a **symlink** pointing at the active eGPU variant
  (`models-egpu-vanilla.ini` by default, or `models-egpu-rdna.ini` for the
  rdna-boosts image). Re-point it **before** `docker compose up -d` when
  switching images.
- `models-igpu.ini` — the iGPU model set.

Models themselves are stored in the bind-mounted weights directory
`llamacpp/hfmodels/`.

Only LLMs configured in `models-egpu.ini` / `models-igpu.ini` are exposed by
the respective server; all others are not served.

### Runtime flags

- `--models-preset /config/models.ini` — load configured models.
- `-cb` — continuous batching.
- `-b` / `-ub` — batch / micro-batch sizes.
- `--models-max` — maximum concurrently loaded models.
- `--metrics` — expose Prometheus metrics.

### Environment variables (`.env`)

| Variable | Meaning |
|---|---|
| `LLAMA_EGPU_PORT` / `LLAMA_IGPU_PORT` | host ports (default `8092` / `8093`) |
| `LLAMA_EGPU_MODELS_MAX` / `LLAMA_IGPU_MODELS_MAX` | max concurrently loaded models per server |
| `LLAMA_EGPU_IMAGE` | eGPU image tag (`llama-cpp-rocm:latest` vanilla / `llama-cpp-rocm:rdna`) |
| `GPU_RENDER_DEVICE` / `GPU_CARD_DEVICE` | eGPU DRI nodes |
| `GPU_IGPU_RENDER_DEVICE` / `GPU_IGPU_CARD_DEVICE` | iGPU DRI nodes |
| `RENDER_GID` / `VIDEO_GID` | host group IDs for GPU access |

## Troubleshooting

**Why the eGPU moved from Vulkan to ROCm (2026-08):** I started with llama.cpp
on CPU, moved to ROCm, then switched to Vulkan because token generation
measured ~20% faster at small/medium context sizes and the image is vastly
smaller. That decision was reversed after Qwen3.6/3.8 models showed severe,
reproducible corruption on the Vulkan/RADV backend that did not occur on ROCm
(HIP) or CPU with identical settings: mistyped tokens in tool calls, ignored
requests, invented tasks, and intermittent GPU hangs
(`vk::Queue::submit: ErrorDeviceLost`). Relevant upstream issues:
[ggml-org/llama.cpp#26744](https://github.com/ggml-org/llama.cpp/issues/26744)
(Vulkan flash-attn coopmat shader lets stale KV cells influence output),
[#26195](https://github.com/ggml-org/llama.cpp/issues/26195) (Vulkan FA +
quantized V cache garbles head_dim=256 models — the Qwen3.x family),
[#24812](https://github.com/ggml-org/llama.cpp/issues/24812) (Qwen on RADV:
clustered garbage in warm streaming sessions),
[#23088](https://github.com/ggml-org/llama.cpp/issues/23088) (MTP speculative
decoding garbled on Vulkan/RADV at ~0.7% acceptance vs 81% on HIP, same GPU),
[#21446](https://github.com/ggml-org/llama.cpp/issues/21446) (Qwen on Vulkan:
`ErrorDeviceLost` on RX 7900 XTX). On ROCm, the same Qwen3.8 config runs
correctly, and with its embedded MTP draft head
(`spec-type = draft-mtp,ngram-mod`, 80–95% acceptance) reaches 40+ t/s —
faster than the Vulkan setup ever was. A lact undervolt (`-150 mV`) was
investigated as a possible cause of the GPU hangs and ruled out. Do not move
the eGPU service back to `Dockerfile.vulkan` without re-testing Qwen-family
models specifically.

- **Qwen3.8 residual quirk (accepted):** with `spec-type = draft-mtp`, the
  first tokens of a response occasionally contain typos (e.g. folder names)
  which the model reliably self-corrects within its thinking chain. Errors
  cluster at response start (cold MTP draft context); `cache-reuse = 0` was
  tested and ruled out. If it ever worsens, test `spec-type = none`.
- **Qwen-family models corrupt file paths in tool calls / reasoning.** If
  paths that previously appeared in context get mangled
  (`homelab` → `hommelab`, `ARCHITECTURE.md` → `ARCHITECTURD.md`, etc.),
  check the model's `models.ini` section for `dry-*` parameters. DRY
  (Don't Repeat Yourself) penalizes repeated token sequences, which is
  useful for prose but actively harmful for exact strings like file paths,
  JSON keys, and shell commands. Remove or comment out `dry-multiplier`,
  `dry-base`, and `dry-allowed-length` for Qwen-family (and other
  agentic/tool-calling) models. If removing DRY causes repetition loops,
  raise `repeat-penalty` slightly (e.g. from `1.0` to `1.01`) instead.

## Related

- Chat frontend that consumes these endpoints: [open-webui/README.md](../open-webui/README.md)
- Observability (llama metrics + GPU exporter): see the main README.

[Back to main README](../README.md)
