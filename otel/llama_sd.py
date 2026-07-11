#!/usr/bin/env python3
"""
Prometheus HTTP Service Discovery for llama.cpp router-mode servers.

llama.cpp router mode calls ensure_model() on EVERY /metrics?model=X request,
which means naive prometheus scraping triggers model loads (then fails with
"failed to fit params to free device memory" when VRAM is occupied).

This service solves that by:
  1. Querying /v1/models on each llama server — which has a status.value field
     ("loaded", "loading", "unloaded") that reflects the worker state WITHOUT
     triggering any model load.
  2. Returning ONLY "loaded" models as scrape targets in Prometheus HTTP SD format.
  3. Returning an empty list when all models are idle — OTel Collector scrapes nothing.

Result: /metrics?model=X is only called when the model IS loaded, eliminating
the 500-error / VRAM-contention churn from the previous static scrape config.

OTel Collector config (collector.yaml):
  prometheus:
    config:
      scrape_configs:
        - job_name: llama
          scrape_interval: 15s
          http_sd_configs:
            - url: http://llama-sd:8099/targets
              refresh_interval: 15s

Environment variables:
  PORT         Listening port (default: 8099)
  LLAMA_SERVERS  JSON array of {url, name} objects — one per llama-server instance
"""

import http.server
import json
import logging
import os
import urllib.error
import urllib.request

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

_DEFAULT_SERVERS = json.dumps([
    {"url": "http://llama-cpp-cpu:8090", "name": "cpu"},
    {"url": "http://llama-cpp-vulkan:8092", "name": "vulkan"},
])

SERVERS: list[dict] = json.loads(os.environ.get("LLAMA_SERVERS", _DEFAULT_SERVERS))
PORT: int = int(os.environ.get("PORT", "8099"))


def get_targets() -> list[dict]:
    """Query each server and return Prometheus HTTP SD target groups for loaded models."""
    targets = []
    for server in SERVERS:
        url: str = server["url"]
        name: str = server["name"]
        # host:port for use as the prometheus scrape address
        host_port = url.split("//", 1)[1]

        try:
            req = urllib.request.Request(
                f"{url}/v1/models",
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read())
        except Exception as exc:
            log.warning("Failed to query %s/v1/models: %s", url, exc)
            continue

        for model in data.get("data", []):
            model_id: str = model.get("id", "")
            status: str = model.get("status", {}).get("value", "unloaded")

            if status == "loaded":
                # __param_model sets ?model=<id> on the scrape URL
                targets.append({
                    "targets": [host_port],
                    "labels": {
                        "__metrics_path__": "/metrics",
                        "__param_model": model_id,
                        "model": model_id,
                        "server": name,
                        "job": f"llama-{name}",
                    },
                })
                log.debug("  + %s / %s (loaded)", name, model_id)
            else:
                log.debug("  - %s / %s (%s, skipped)", name, model_id, status)

    return targets


class SDHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path.rstrip("/") != "/targets":
            self.send_error(404)
            return
        try:
            body = json.dumps(get_targets(), indent=2).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            log.exception("Error building targets: %s", exc)
            self.send_error(500, str(exc))

    def log_message(self, fmt: str, *args) -> None:  # noqa: N802
        pass  # silence per-request access logs


if __name__ == "__main__":
    log.info("llama-sd listening on :%d/targets", PORT)
    log.info("Monitoring servers: %s", [s["url"] for s in SERVERS])
    with http.server.HTTPServer(("", PORT), SDHandler) as httpd:
        httpd.serve_forever()
