[Back to main README](../README.md)

# Blender (Cycles/HIP, gfx1100)

## TL;DR

`blender-rocm` runs Blender `5.2.0` LTS headless with Cycles on the eGPU
(RX 7900 XTX / gfx1100). The `blender-render` wrapper forces GPU compute and
the HIP backend, so `.blend` files saved with a CPU device still render on
the eGPU. You touch this when you want to render a scene, run the
smoketest/stresstest, or rebuild the image.

## What & why

The 3D-rendering work mode of the stack. Blender is a full 3D suite; here it
is used headless for Cycles path-tracing on the eGPU. It is profile-gated
behind the `blender` work mode, so it never contends with the llama.cpp
servers for VRAM.

## How it works

### Build (`Dockerfile.rocm`)

- Base: `rocm/dev-ubuntu-24.04:7.14.1-full`.
- Downloads the official Blender Linux tarball (`BLENDER_VERSION=5.2.0`).
- Installs ROCm runtime libraries and graphics/font/X11 deps required by the
  official binary.
- Sets `HSA_ENABLE_SDMA=0` and `LD_PRELOAD=libjemalloc.so.2`.

### `blender-render` wrapper

`blender/bin/blender-render` is copied into `/usr/local/bin`. It forces:

- background mode (`-b`);
- Cycles engine (`-E CYCLES`);
- GPU compute device (`bpy.context.scene.cycles.device = 'GPU'`);
- HIP back end (`-- --cycles-device HIP`).

This lets you submit `.blend` files saved with a CPU device and still render
on the eGPU.

### File ownership

The service runs as `${UID}:${GID}` (default 1000:1000), so rendered outputs
are owned by the host user.

## How to use

```bash
cp scene.blend ${APP_ROOT}/blender/work/
make blender
docker compose exec blender-rocm blender-render /work/scene.blend \
  -f 1 -o /work/output/frame_ -F PNG
```

One-off project folder override:

```bash
docker compose run --rm \
  -v /path/to/project:/work:rw \
  blender-rocm \
  blender-render /work/scene.blend -f 1 -o /work/output/frame_ -F PNG
```

### Smoketest: BMW27

Download `BMW27_2.blend.zip` from
<https://download.blender.org/demo/test/BMW27_2.blend.zip>, extract it into
`blender/work/_smoketest/` so the scene is at
`blender/work/_smoketest/bmw27/bmw27_gpu.blend`, then run:

```bash
make blender
docker compose exec blender-rocm bash /work/_smoketest/smoketest.sh
```

Expected render time: ~11–13 s for frame 1 on the target hardware.

### Stresstest: Barbershop Interior

Download `barbershop_interior.blend` from the Blender demo files and place it
at `blender/work/_stresstest/barbershop_interior.blend`, then run:

```bash
docker compose exec blender-rocm bash /work/_stresstest/stresstest.sh
```

Expected render time: ~1:40–1:50 min for frame 1 on the target hardware.

## Configuration & influence

### Environment variables (`.env`)

| Variable | Meaning |
|---|---|
| `APP_ROOT` | absolute path to this repository (the `blender/work` volume root) |
| `UID` / `GID` | host user/group the service runs as (default `1000:1000`) |
| `GPU_RENDER_DEVICE` / `GPU_CARD_DEVICE` | eGPU DRI nodes |
| `RENDER_GID` / `VIDEO_GID` | host group IDs for GPU access |

### Runtime environment (set in the image / compose)

- `HSA_ENABLE_SDMA=0` — required in this VFIO/KVM passthrough setup to avoid
  IOMMU TLB-flush storms.
- `LD_PRELOAD=libjemalloc.so.2` — reduces malloc fragmentation.

## Troubleshooting

If a render falls back to the CPU or fails to find the device, confirm the
`blender` mode is active (`make status`), that both eGPU DRI nodes
(`GPU_RENDER_DEVICE` / `GPU_CARD_DEVICE`) are passed through, and that the
`blender-render` wrapper (not plain `blender`) is being used — plain `blender`
does not force the HIP backend.

## Related

- GPU work-mode switching and the always-on services: see the main README
  (GPU work modes, Services and ports).
- Observability (GPU exporter, Grafana): see the main README.

[Back to main README](../README.md)
