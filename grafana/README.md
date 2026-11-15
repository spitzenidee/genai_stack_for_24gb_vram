[Back to main README](../README.md)

# Grafana (dashboards + standalone LGTM backend)

## TL;DR

The visualization side of the stack's observability pipeline: two
dashboards (llama.cpp + AMD GPU, and host RAM pressure), provisioning files
for a Grafana instance outside this compose stack, and a self-contained
`docker compose` example (`grafana/resources/`) for an all-in-one
Grafana/LGTM backend — in this setup running in its own small Proxmox LXC.
You touch this when you want to import a dashboard, provision a new Grafana
instance, or tune backend retention.

## What & why

The [otel collector](../otel/README.md) pushes all metrics and logs to an
*external* backend via OTLP — Grafana is deliberately **not** part of the
main compose stack, so the monitoring backend can live on its own machine
(LXC) and keep running even when the stack is rebuilt. The dashboards turn
the pipeline's signals into the views this stack is actually operated from:
GPU hardware + inference at a glance, and host RAM/swap pressure (the
iGPU's system-memory carve-out makes host RAM the scarce resource here).

## How it works

### Dashboards (`grafana/dashboards/`)

- **`llama-gpu-amdgpu.json`** — "llama-cpp + AMD GPU (eGPU/iGPU)"
  (32 panels): llama.cpp inference metrics + AMD GPU hardware
  (VRAM, temps, power, clocks, fan) + host/container resources. Hardware and
  inference metrics correlate via the shared `gpu=egpu|igpu` label.
- **`ram-pressure.json`** — "RAM pressure (genai host)" (13 panels):
  effective headroom (`MemAvailable`), RAM-budget gauge (vs the effective
  pool = total − iGPU carve-out), swap usage + swap I/O, per-container
  memory, and the iGPU's true footprint (cgroup +
  `amdgpu_vram_used_bytes{gpu="igpu"}`). Carve-out and total are adjustable
  dashboard variables.

Both are standalone-importable (schemaVersion 38, `${datasource}` template
variable) and expect a Prometheus-compatible datasource **named
`Prometheus`**.

### Provisioning (`grafana/provisioning/`)

- **`dashboards/provider.yaml`** — a file-based dashboard provider
  (`genai_stack`) pointing at
  `/etc/grafana/provisioning/dashboards/genai_stack/`, with
  `updateIntervalSeconds: 30` and `allowUiUpdates: true`.
- **`datasources/prometheus.yaml`** — provisions the default `Prometheus`
  datasource (URL to adjust to your actual endpoint, `timeInterval: 15s`
  matching the collector's scrape interval).

### Standalone backend example (`grafana/resources/`)

A portable, all-in-one LGTM setup for a machine that hosts *only* the
monitoring backend:

- **`docker-compose.yml`** — runs `grafana/otel-lgtm:latest` (Grafana +
  Prometheus + Loki + Tempo + OTel collector in one container) with
  Grafana UI on `:3000` and OTLP receivers on `:4317`/`:4318` — the
  endpoints the stack's collector pushes to. Data persists in
  `./container/{grafana,prometheus,loki}`.
- **`.env.example`** — optional feature flags and backend retention knobs
  (e.g. Prometheus TSDB retention, Loki compactor retention).
- **`loki-config.yaml`** — Loki config (filesystem storage, v13 schema) for
  the log side of the LGTM container.

In this setup the LXC has Docker installed and runs exactly this compose
file, so the backend stays portable across machines.

## How to use

**Point the stack at the backend** — set `OTEL_EXPORTER_OTLP_ENDPOINT` in
the stack's `.env` to the backend's OTLP gRPC address (e.g.
`192.168.1.XX:4317`), then `docker compose up -d otel-collector`.

**Import a dashboard (UI)** — Grafana → Dashboards → Import → paste the
JSON from `grafana/dashboards/*.json` → pick the `Prometheus` datasource.

**Provision a fresh Grafana instance (file-based)**:

```bash
# on the Grafana host (e.g. the LXC):
# 1. datasource (skip if a datasource named "Prometheus" already exists)
sudo cp grafana/provisioning/datasources/prometheus.yaml \
  /etc/grafana/provisioning/datasources/
sudo systemctl restart grafana-server

# 2. dashboards
sudo cp grafana/provisioning/dashboards/provider.yaml \
  /etc/grafana/provisioning/dashboards/
sudo mkdir -p /etc/grafana/provisioning/dashboards/genai_stack
sudo cp grafana/dashboards/*.json \
  /etc/grafana/provisioning/dashboards/genai_stack/
sudo systemctl reload grafana-server
# or without a restart:
# curl -X POST http://admin:admin@localhost:3000/api/admin/provisioning/dashboards/reload
```

## Configuration & influence

- **Backend retention** — `grafana/resources/.env`: `PROMETHEUS_EXTRA_ARGS`
  (e.g. `--storage.tsdb.retention.time=14d`) and `LOKI_EXTRA_ARGS`
  (e.g. compactor retention) are passed straight to the LGTM components.
- **Dashboard provider** — `provider.yaml` options: `updateIntervalSeconds`
  (how often the file provider rescans), `allowUiUpdates` (UI edits to
  provisioned dashboards are kept), `disableDeletion`.
- **Datasource** — `prometheus.yaml`: `url` (your Prometheus/Mimir/
  VictoriaMetrics endpoint), `timeInterval` (keep at `15s` to match the
  scrape interval), `isDefault`.
- **Dashboards** — the RAM-pressure dashboard's carve-out/total variables
  are tuned per hardware; edit via the UI (`allowUiUpdates: true`) or in the
  JSON.

## Troubleshooting

- **Panels are empty / "datasource not found".** The datasource must be
  named exactly `Prometheus` (the dashboards' template variable resolves by
  name). Check the datasource URL in `prometheus.yaml` (or the existing
  datasource) points at a live Prometheus.
- **Provisioned dashboard not updating.** The file provider rescans every
  `updateIntervalSeconds` (30 s); force it with the
  `provisioning/dashboards/reload` API call or `systemctl reload
  grafana-server`.
- **No data at all.** Work backwards: Grafana → Explore → run a query for
  `amdgpu_gpu_busy_percent` (always produced by the exporter). If empty, the
  problem is upstream — see [otel/README.md](../otel/README.md) →
  Troubleshooting.

## Related

- The pipeline that feeds these dashboards (exporters, collector):
  [otel/README.md](../otel/README.md)
- Services & ports, GPU work modes: main README
  ([../README.md](../README.md))

[Back to main README](../README.md)
