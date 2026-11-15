[Back to main README](../README.md)

# ComfyUI (ROCm/HIP, gfx1100)

## TL;DR

`comfyui-rocm` runs ComfyUI (pinned `v0.33.1`) with ROCm 7.14 PyTorch on the
eGPU (RX 7900 XTX / gfx1100). It is a node-based UI for diffusion-model image
generation, served on host port `8082` (default `COMFYUI_ROCM_PORT`; the
container listens on `8188`). You touch this when you want to generate
images, add models or custom nodes, rebuild the image, or tune the VRAM
flags.

## What & why

The image-generation work mode of the stack. ComfyUI is a node graph editor
for Stable-Diffusion-class models (SDXL, Qwen-Image, …). It runs on the eGPU
via ROCm/HIP and is profile-gated behind the `comfyui` work mode, so it never
contends with the llama.cpp servers for VRAM.

## How it works

Two build files exist:

- `Dockerfile.rocm` — active in `comfyui` mode.
- `Dockerfile` — CPU-only PyTorch variant, not wired into the default compose
  profile.

### ROCm image (`Dockerfile.rocm`)

- Base: `rocm/dev-ubuntu-24.04:7.14.1-full` (the `-full` variant is required:
  `--use-pytorch-cross-attention` / Triton JIT needs `hipcc` from the full
  ROCm toolchain).
- PyTorch: ROCm 7.14 nightly wheels
  (`torch==2.14.0.dev20260807+rocm7.14`, pinned via `TORCH_DATE`).
- ComfyUI: pinned release tag `v0.33.1`.
- Extra Python deps for the ComfyUI-GGUF custom nodes: `gguf>=0.13.0`,
  `sentencepiece`, `protobuf`.

**Note:** I decided to keep the ComfyUI docker image, as I started out with
testing it on the CPU only and then moved later on to the eGPU. I may remove
it later, but for now keep it as a historic reference. It's very slow, though,
I recommend to **not** test it out.

### Runtime flags

The compose service overrides the image CMD with performance-oriented flags:

```bash
python3 main.py --listen 0.0.0.0 --port 8188 \
  --use-pytorch-cross-attention \
  --reserve-vram 2 \
  --cache-ram \
  --dont-upcast-attention \
  --async-offload 2 \
  --preview-method latent2rgb
```

### Volumes

Models, outputs, inputs, and custom nodes are bind-mounted from the host so
they persist across rebuilds and can be shared with the CPU image. A patched
built-in node module is mounted read-only into the image without shadowing
the rest of the package.

## How to use

```bash
make comfyui          # switch to ComfyUI mode
# then open http://<host>:8082 in a browser
```

Drop model weights into `comfyui/models/`, inputs into `comfyui/input/`, and
custom nodes into `comfyui/custom_nodes/` (all bind-mounted, all persist
across rebuilds).

## Configuration & influence

### Environment variables (`.env`)

| Variable | Meaning |
|---|---|
| `COMFYUI_ROCM_PORT` | host port (default `8082`; container listens on `8188`) |
| `APP_ROOT` | absolute path to this repository (volume roots) |
| `GPU_RENDER_DEVICE` | eGPU DRI render node |
| `RENDER_GID` / `VIDEO_GID` | host group IDs for GPU access |

### Runtime environment (set in the image / compose)

- `HSA_ENABLE_SDMA=0` — required in this VFIO/KVM passthrough setup to avoid
  IOMMU TLB-flush storms.
- `PYTORCH_CUDA_ALLOC_CONF=garbage_collection_threshold:0.8` — proactive VRAM
  reclaim.
- `LD_PRELOAD=libjemalloc.so.2` — reduces malloc fragmentation.

## Troubleshooting

If the Web UI does not load, check that the `comfyui` mode is active
(`make status`), that the eGPU render node is passed through
(`GPU_RENDER_DEVICE`), and that no other heavy GPU workload is running in the
same mode slot.

## Related

- GPU work-mode switching and the always-on services: see the main README
  (GPU work modes, Services and ports).
- Observability (GPU exporter, Grafana): see the main README.

[Back to main README](../README.md)
