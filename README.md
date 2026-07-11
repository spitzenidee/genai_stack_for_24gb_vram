# Opinionated GenAI stack for 24GB VRAM (minimum)

This is my personal Docker Compose stack for local GenAI inference. Opinionated and built around a specific hardware setup — not intended as a general-purpose template, but maybe helpful to someone. You can find the documentation of my hardware stack and the setup at https://github.com/spitzenidee/um790pro_7900xtx_setup.

This stack and documentation / README is not finished yet, it needs quite some more love.

## Hardware target

- **GPU:** AMD RDNA3 (gfx1100), 24 GB VRAM (AMD Radeon RX 7900 XTX, via Oculink adapter and Minisforum DEG1 eGPU dock)
- **CPU:** AMD Zen4 (Minisforum UM790Pro, 64GB RAM, Ryzen 9 7940HS)

## Services

| Service | Description |
|---|---|
| `open-webui` | Chat UI (Open WebUI), OpenAI-compatible API frontend |
| `llama-cpp-vulkan` | llama.cpp inference server, Vulkan backend (GPU) |
| `llama-cpp-cpu` | llama.cpp inference server, CPU-only (Zen4-tuned build) |
| `comfyui-rocm` | ComfyUI image generation, ROCm backend |
| `lact` | LACT daemon for AMD GPU power/voltage control |
| `gpu-exporter` | Custom sysfs-based AMD GPU Prometheus exporter (no ROCm dependency) |
| `llama-sd` | Prometheus HTTP SD that exposes only currently loaded llama.cpp models |
| `otel-collector` | OpenTelemetry Collector (metrics, traces, logs) |

Grafana dashboard configs and Prometheus datasource provisioning are in `grafana/` but run outside this compose file. This stack does not include the Grafana stack itself, it runs elsewhere.

## Models

GGUF text models are served by llama.cpp. Image generation uses safetensors/GGUF models under `comfyui/models/`. No models are included in the repo — paths are mapped via volumes.

## Configuration

Runtime configuration is done via environment variables (`.env` file, not committed). See `llamacpp/models.ini.example` and `lact/config.yaml.example` for required config files.

## Notes

- Llama.cpp images are built from source at compose build time, always pulling the latest release tag.
- ComfyUI uses ROCm with `HSA_ENABLE_SDMA=0` to avoid workqueue storms under KVM/VFIO passthrough.
- This repo mirrors a sanitized subset of a private repo; some config files and model directories are excluded.
