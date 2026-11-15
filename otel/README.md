[Back to main README](../README.md)

# Observability (OpenTelemetry)

## TL;DR

The always-on monitoring pipeline of the stack: three compose services —
`gpu-exporter` (AMD GPU hardware metrics), `llama-sd` (safe scrape-target
discovery for llama.cpp), and `otel-collector` (aggregates metrics and logs,
pushes them via OTLP to an external Grafana backend) — plus
`scripts/gpu_monitor.sh`, a host-side terminal monitor for both GPUs. You
touch this when you want to add a scrape target or receiver, point the stack
at a different backend, or debug why a metric is (not) showing up.

## What & why

The stack needs continuous visibility into three things: GPU hardware
(VRAM, temps, power, clocks), llama.cpp inference (per-model tokens/s,
load), and host/container resources (CPU, RAM, swap, per-container usage,
logs).

Two design constraints shaped the pipeline:

- **No ROCm in the exporter.** The GPU exporter reads sysfs only — pure
  Python stdlib — so it runs in a tiny `python:3.13-alpine` container
  without any GPU driver stack.
- **Scraping must never load a model.** llama.cpp in router mode calls
  `ensure_model()` on every `/metrics?model=X` request, so a naive static
  Prometheus scrape would trigger model loads (VRAM contention + 500 errors)
  for idle models. `llama-sd` solves this with Prometheus HTTP service
  discovery: it only advertises models that are *currently loaded*.

Everything is always-on (no work-mode profile), so monitoring survives every
`make <mode>` switch.

## How it works

### `gpu-exporter` (`otel/amdgpu_exporter.py`)

Pure-stdlib Python Prometheus exporter. Reads `/sys/class/drm/card*/device`
and `/sys/class/hwmon/hwmon*`, auto-detects all AMD cards (vendor `0x1002`).
Exposes GPU busy %, VRAM/GTT bytes, temperatures, power, clocks, fan RPM,
and voltages with a `gpu=egpu|igpu` label (derived from the PCI device ID;
override with `GPU_ROLE_MAP`). Port: `9898`.

### `llama-sd` (`otel/llama_sd.py`)

Prometheus HTTP service discovery for `llama-server`. Queries `/v1/models`
on each configured server and returns only `loaded` models as scrape targets
in Prometheus HTTP SD format; when all models are idle it returns `[]` and
the collector scrapes nothing — no side effects. Port: `8099`.

It is intentionally **profile-free** (no `depends_on` on the llama servers):
`otel-collector` depends on it, and target discovery must keep working in
every GPU work mode. Per-server connection failures are caught and skipped.

### `otel-collector`

Runs the pinned `otel/opentelemetry-collector-contrib:0.165.0` image with a
bind-mounted config (`otel/collector.yaml`). Receivers:

- **`prometheus`** — scrapes `llama` (via `llama-sd` HTTP SD, 15 s) and
  `amdgpu` (the `gpu-exporter`, 15 s).
- **`docker_stats`** — per-container CPU/mem/net/IO via the Docker socket.
- **`host_metrics`** — host CPU/memory/load + paging (swap) +
  `system.linux.memory.available` (drives the RAM-pressure dashboard's
  effective-headroom stat). A per-process `process` scraper is a documented
  follow-up (needs `pid: host` + SYS_PTRACE/root — deliberately not enabled).
- **`file_log`** — Docker JSON logs (per-container ID extracted for
  filtering) and host syslog files (`syslog`, `auth.log`, `kern.log`).
- **`otlp`** — gRPC `:4317` / HTTP `:4318` push endpoint for instrumented
  services (e.g. `open-webui` pushes traces via
  `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317`).

Processors: `memory_limiter` (256 MiB cap), `resource_detection`, `batch`.
Single exporter: `otlp_grpc` → `OTEL_EXPORTER_OTLP_ENDPOINT` (the external
Grafana/LGTM backend, plaintext/insecure on the LAN). The container
`hostname` is set to `genaivm` so `host.name` in Grafana is stable instead of
a container ID.

### Host monitor (`scripts/gpu_monitor.sh`)

Dependency-light bash monitor that reads sysfs directly (no `rocm-smi` —
it crashes on the iGPU's unsupported clock values). Shows both eGPU and
iGPU in a single colorized, low-flicker view with sparklines, plus
htop-style per-thread CPU bars.

```bash
scripts/gpu_monitor.sh        # refresh every 2 seconds
scripts/gpu_monitor.sh 1      # refresh every 1 second
```

Requires `bash`, `awk`, `bc`, `cat`, `printf`, `sleep`, `trap`.

## How to use

```bash
scripts/gpu_monitor.sh                    # terminal view of both GPUs
curl -s localhost:9898/metrics | head     # raw GPU hardware metrics
curl -s localhost:8099/targets            # which llama models are scrape targets right now
docker compose logs -f otel-collector     # collector health / pipeline errors
```

Everything else is viewed in Grafana — see [grafana/README.md](../grafana/README.md).

## Configuration & influence

### Environment variables (`.env`)

| Variable | Meaning |
|---|---|
| `GPU_EXPORTER_PORT` | host port for `gpu-exporter` (default `9898`) |
| `LLAMA_SD_PORT` | host port for `llama-sd` (default `8099`) |
| `OTEL_GRPC_PORT` | host port for OTLP gRPC (default `4317`) |
| `OTEL_HTTP_PORT` | host port for OTLP HTTP (default `4318`) |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP gRPC endpoint of your external Grafana/LGTM backend (e.g. `192.168.1.XX:4317`) |
| `LLAMA_SERVERS` | JSON array of `{url, name}` objects — the llama servers `llama-sd` probes |

`gpu-exporter` additionally honors `GPU_ROLE_MAP`
(`"744c=egpu,15bf=igpu"` by default) to map PCI device IDs to the `gpu`
label.

### Adding a scrape target or receiver

Edit `otel/collector.yaml` (bind-mounted, read-only into the container):
append a `scrape_configs` entry under `receivers.prometheus.config`, or add
a new receiver and wire it into the matching pipeline under `service`.
Instrumented services push instead: set
`OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317`
(+ `OTEL_EXPORTER_OTLP_INSECURE=true`) in their environment. Then
`docker compose up -d otel-collector` to reload.

## Troubleshooting

- **No llama metrics in Grafana.** By design, only *loaded* models are
  scraped. Check `curl -s localhost:8099/targets` — an empty list means all
  models are idle. Also check that `LLAMA_SERVERS` in `.env` matches the
  running llama services.
- **Backend gets nothing.** Verify `OTEL_EXPORTER_OTLP_ENDPOINT` in `.env`
  is reachable from the host (the collector exports over plaintext OTLP gRPC
  to the LAN backend). Watch `docker compose logs otel-collector` for
  exporter retry errors.
- **Collector self-noise.** Telemetry log level is pinned to `warn` in
  `collector.yaml`; set it to `info` temporarily when debugging the pipeline.

## Related

- Dashboards, provisioning, and the standalone Grafana/LGTM backend:
  [grafana/README.md](../grafana/README.md)
- Services & ports, GPU work modes: main README
  ([../README.md](../README.md))

[Back to main README](../README.md)
