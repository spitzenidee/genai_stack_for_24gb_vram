[Back to main README](../README.md)

# Chat frontend: Open WebUI

## TL;DR

`open-webui` is the web chat frontend for the stack. It runs the upstream
`ghcr.io/open-webui/open-webui:main` image, connects to the eGPU (and iGPU)
llama.cpp endpoints as OpenAI-API providers, and is started only in `llama`
mode (host port `8080`). You touch it to chat with your local models, add
endpoints, or tune provider tags/prefixes.

## What & why

A browser-based chat interface for prototyping and testing the local LLMs,
mostly for interactive use (vs. the raw API). It gives you a model picker,
per-provider tags/prefixes, and prompt-processing / token-generation speed
numbers, so you can sanity-check both llama instances without writing curl
commands.

## How it works

The `open-webui` service runs the upstream container image and connects to the
eGPU inference backend.

- Port: `8080` on the host → `8080` in the container.
- Depends on `llamacpp-egpu`.
- Pushes OpenTelemetry traces to `otel-collector:4317` (gRPC, insecure/plaintext).
- Stores state in a bind-mounted backend data directory (`open-webui/`).

Started only in `llama` mode (compose profile `llama`).

## How to use

```bash
make llama        # starts open-webui + llamacpp-egpu (llamacpp-igpu is always-on)
```

Then open `http://<host>:8080` in a browser.

### Configure iGPU and eGPU endpoints in OpenWebUI

Both llama-server instances (iGPU, eGPU) must be configured as "OpenAI API"
endpoints as follows (IP `192.0.2.123` is used as an example here — RFC 5737
documentation range — use the IP address your own VM / machine is running at):

- eGPU
  - `http://192.0.2.123:8092/v1`
- iGPU
  - `http://192.0.2.123:8093/v1`

In the connection config you can add a tag and/or a prefix, which helps dearly
with identifying where a model will be served from. E.g. if you assign the
prefix `igpu` to the iGPU endpoint, then in e.g. the chat window all models
exposed by this endpoint will be available as `igpu.<modelname>`.

## Configuration & influence

Environment variables (`.env`):

| Variable | Meaning |
|---|---|
| `OPEN_WEBUI_PORT` | host port (default `8080`) |
| `WEBUI_SECRET_KEY` | secret key for the web UI (set in `.env`) |

Environment set on the compose service:

- `ENABLE_OTEL=true` / `ENABLE_OTEL_TRACES=true` — OTel traces on.
- `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317` — gRPC exporter target.
- `OTEL_EXPORTER_OTLP_INSECURE=true` — plaintext OTLP.
- `AIOHTTP_CLIENT_TIMEOUT=7200` — long-running request timeout.

State (chat history, vector DB, uploads) persists in the bind-mounted
`open-webui/` directory.

## Troubleshooting

- **No models shown** — the endpoint isn't configured, or the llama server
  isn't up. Confirm `curl http://localhost:8092/v1/models` returns the model,
  then add the endpoint in Open WebUI.
- **OTel metrics not pushed** — by design: only traces are pushed (gRPC); the
  collector has no OTLP metrics receiver, so metrics are scraped via
  Prometheus instead.

## Related

- Inference endpoints: [llamacpp/README.md](../llamacpp/README.md)
- Observability (collector / Grafana): see the main README.

[Back to main README](../README.md)
