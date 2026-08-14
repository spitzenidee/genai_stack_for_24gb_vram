# ComfyUI — CPU-only build
# No CUDA / ROCm. PyTorch CPU wheel is ~250MB vs ~3GB for CUDA.
# The Radeon 780M iGPU shares system RAM, so GPU mode would compete
# for the same memory budget — CPU-only is the right trade-off here.

FROM python:3.11-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libgomp1 \
    libjemalloc2 \
    && rm -rf /var/lib/apt/lists/*

# CPU-only PyTorch (significantly smaller than the default CUDA wheel)
RUN pip install --no-cache-dir \
    torch torchvision torchaudio \
    --index-url https://download.pytorch.org/whl/cpu

# Clone a pinned release tag — change ARG to upgrade
# Releases: https://github.com/Comfy-Org/ComfyUI/releases
ARG COMFYUI_VERSION=v0.24.0
RUN git clone --depth 1 --branch ${COMFYUI_VERSION} https://github.com/Comfy-Org/ComfyUI.git /ComfyUI

WORKDIR /ComfyUI

RUN pip install --no-cache-dir -r requirements.txt requests

# ComfyUI-GGUF custom node dependencies
RUN pip install --no-cache-dir \
    "gguf>=0.13.0" \
    sentencepiece \
    protobuf

# Runtime tuning for AMD Zen 4 (AVX-512 + BF16)
# DNNL_DEFAULT_FPMATH_MODE=BF16  — oneDNN runs conv/matmul internally in BF16
#   using avx512_bf16; results are rounded back to FP32. ~1.5-2x faster.
# OMP_NUM_THREADS=6               — leave 1 thread for OS/HTTP/queue work
# KMP_BLOCKTIME=50                — OpenMP spin-wait 50ms (default 200ms)
#   avoids threads going cold between the ~50 U-Net sampling steps
# ONEDNN_PRIMITIVE_CACHE_CAPACITY — avoid JIT recompilation during SDXL runs
# LD_PRELOAD jemalloc              — reduces glibc malloc fragmentation
# MALLOC_CONF                      — background GC + delayed OS return
ENV OMP_NUM_THREADS=6 \
    KMP_BLOCKTIME=50 \
    DNNL_DEFAULT_FPMATH_MODE=BF16 \
    ONEDNN_PRIMITIVE_CACHE_CAPACITY=4096 \
    LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libjemalloc.so.2 \
    MALLOC_CONF=background_thread:true,metadata_thp:auto,dirty_decay_ms:30000,muzzy_decay_ms:30000

# Persistent data lives in mounted volumes, not in the image
VOLUME ["/ComfyUI/models", "/ComfyUI/output", "/ComfyUI/input", "/ComfyUI/custom_nodes"]

EXPOSE 8188

# --cpu         : force CPU inference (no GPU)
# --listen      : bind to 0.0.0.0 so the port is reachable from outside the container
# --cache-lru 1 : keep only the last workflow result in RAM (reduces idle RAM footprint)
CMD ["python", "main.py", "--cpu", "--listen", "0.0.0.0", "--port", "8188", "--cache-lru", "1"]
