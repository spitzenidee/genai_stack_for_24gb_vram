[Back to main README](../README.md)

# GPU tuning: LACT (Linux AMD Configuration Tool)

## TL;DR

`lact` is the stack's GPU tuning daemon: the official `ghcr.io/ilya-zlobintsev/lact:v0.9.0`
image in a privileged container, so it can write sysfs for power/voltage/fan control on
the eGPU (RX 7900 XTX). It is **always-on** (no compose profile — runs in every work
mode), and its settings persist in the host-mounted `lact/config.yaml`. You touch it when
tuning the eGPU's power/voltage sweet spot, checking current settings via `lact cli`, or
running the power sweep in `scripts/power_bench.py`.

## What & why

The eGPU's out-of-box power and fan behavior is not optimized for this stack's workload
(long inference sessions, long idle periods). LACT gives the stack direct, persistent
control over the knobs that matter for the power-vs-performance trade:

- **Power cap** — cap the eGPU at a wattage sweet spot (265 W here) for better
  efficiency at a small peak-performance cost.
- **Voltage offset** — undervolt the GPU (−150 mV here) for the same trade.
- **Fan control** — PMFW firmware fan targets (optional; off by default).
- **Performance level / clocks** — pin the GPU to a performance level.

It exists so tuning is a *config file change* (or a one-shot `lact cli` call) instead of
a host-level driver operation — and so the settings survive reboots and container
restarts.

## How it works

| Piece | Where |
|---|---|
| Compose service | `lact` in `docker-compose.yml` — **no profile** (always-on, every work mode) |
| Image | `ghcr.io/ilya-zlobintsev/lact:v0.9.0` (official: daemon + CLI only, no GUI) |
| Privilege | `privileged: true` — required: sysfs writes for power/voltage control |
| Device passthrough | eGPU DRI nodes `${GPU_RENDER_DEVICE}` / `${GPU_CARD_DEVICE}` (from `.env`) |
| Config | `${APP_ROOT}/lact` → `/etc/lact` (bind mount — `config.yaml` persists across restarts) |
| Tracked example | `lact/config.yaml.example` — the stable setup (see Configuration) |

The daemon starts with the container and applies `config.yaml` on a short timer
(`apply_settings_timer: 5` s). The control interface is the CLI inside the container:
`docker exec lact lact cli …`.

## How to use

```sh
docker compose up -d lact                 # start (targeted — safe)
docker compose logs -f lact               # logs
docker exec lact lact cli                 # interactive CLI (show/set power, voltage, fan, …)
```

`scripts/power_bench.py` uses `docker exec lact lact cli` to sweep the GPU
power limit and record llama.cpp tokens/s to CSV — see
[scripts/README.md](../scripts/README.md).

## Configuration & influence

`lact/config.yaml` (bind-mounted from the host; `lact/config.yaml.example` is the
tracked reference). Key per-GPU knobs:

| Knob | Example value | Meaning |
|---|---|---|
| `power_cap` | `265.0` | power cap in watts — the efficiency sweet spot for this stack |
| `voltage_offset` | `-150` | undervolt in mV |
| `performance_level` | `auto` | pin to `auto` / `high` / `low` |
| `pmfw_options` | see example | PMFW firmware fan targets (`target_temperature`, `acoustic_target`, `zero_rpm`, …) — off by default (`fan_control_enabled: false`) |
| `max_memory_clock` | commented out | optional memory-clock pin |

The `config.yaml.example` resembles my stable setup. I tested an undervolt of -160mV
but am not quite sure that it really is 100% stable, so I settled on -150mV incl
power-capping the eGPU at 265W for a better power efficiency sweet-spot (going higher
we'll approach diminishing returns quickly). Note: during the Vulkan→ROCm investigation
(see [llamacpp/README.md](../llamacpp/README.md)) the -150mV undervolt was explicitly
tested as a possible cause of GPU hangs and ruled out — it is stable for this workload.

Measured tokens/s at the fixed benchmark prompt (from the `config.yaml.example`
comments):

| Voltage offset | Result |
|---|---|
| −150 mV | ~48.5 t/s, fully stable |
| −160 mV | ~51.0 t/s, fully stable |
| −175 mV | ~49.5 t/s, **unstable** |

## Troubleshooting

- **Settings not applied after a restart** — the daemon applies `config.yaml` on a 5 s
  timer; check `docker logs lact`. If the GPU id under `gpus:` no longer matches
  (re-seat, firmware change), update the key.
- **`lact cli` cannot find the GPU** — the eGPU DRI nodes must be passed through
  (`GPU_RENDER_DEVICE` / `GPU_CARD_DEVICE` in `.env`); check `ls -l /sys/class/drm/`.

## Related

- The power sweep that drives LACT: [scripts/README.md](../scripts/README.md)
  (`power_bench.py`)
- The eGPU workload LACT tunes: [llamacpp/README.md](../llamacpp/README.md)
- Services & ports, GPU work modes: main README ([../README.md](../README.md))

[Back to main README](../README.md)
