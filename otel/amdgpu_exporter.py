#!/usr/bin/env python3
"""AMD GPU sysfs Prometheus exporter.

Pure stdlib — no pip, no ROCm, no device-driver libraries.
Reads directly from /sys/class/drm and /sys/class/hwmon (world-readable).
Detects all AMD cards (vendor 0x1002) automatically.

Metrics exposed at  GET /metrics
  amdgpu_gpu_busy_percent
  amdgpu_vram_used_bytes / amdgpu_vram_total_bytes
  amdgpu_gtt_used_bytes
  amdgpu_temperature_celsius        {sensor="edge|junction|mem"}
  amdgpu_power_watts
  amdgpu_core_clock_hz / amdgpu_memory_clock_hz
  amdgpu_fan_rpm
  amdgpu_voltage_millivolts         {sensor="vddgfx|…"}

All metrics also carry a "gpu" label ("egpu"/"igpu"/"unknown") derived from
the PCI device ID, matching llama-sd's "server" label values (otel/llama_sd.py)
so Grafana can correlate hardware + inference metrics for the same physical
GPU via a single $gpu template variable. Override the mapping with the
GPU_ROLE_MAP env var, format: "744c=egpu,15bf=igpu".
"""

import glob
import os
import re
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = int(os.environ.get("PORT", 9898))

_DEFAULT_GPU_ROLE_MAP = "744c=egpu,15bf=igpu"


def _parse_role_map(raw: str) -> dict:
    roles = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        dev_id, role = pair.split("=", 1)
        roles[dev_id.strip().lower()] = role.strip()
    return roles


GPU_ROLES = _parse_role_map(os.environ.get("GPU_ROLE_MAP", _DEFAULT_GPU_ROLE_MAP))


# ---------------------------------------------------------------------------
# sysfs helpers
# ---------------------------------------------------------------------------

def _read_int(path: str):
    try:
        with open(path) as f:
            return int(f.read().strip())
    except Exception:
        return None


def _read_str(path: str):
    try:
        with open(path) as f:
            return f.read().strip()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# GPU discovery
# ---------------------------------------------------------------------------

def find_amd_cards() -> list[str]:
    """Return sorted list of /sys/class/drm/cardN paths with vendor 0x1002."""
    cards = []
    for path in sorted(glob.glob("/sys/class/drm/card*")):
        if not re.search(r"/card\d+$", path):
            continue  # skip cardN-<connector> entries
        if _read_str(os.path.join(path, "device", "vendor")) == "0x1002":
            cards.append(path)
    return cards


def _card_labels(card_path: str) -> dict:
    card = os.path.basename(card_path)
    uevent = _read_str(os.path.join(card_path, "device", "uevent")) or ""
    m = re.search(r"PCI_SLOT_NAME=(\S+)", uevent)
    pci = m.group(1) if m else "unknown"
    m = re.search(r"PCI_ID=\S*:(\S+)", uevent)
    dev_id = m.group(1).lower() if m else ""
    gpu = GPU_ROLES.get(dev_id, "unknown")
    return {"card": card, "pci": pci, "gpu": gpu}


def find_hwmon(card_path: str):
    """Return the hwmon directory for a card, or None."""
    # /sys/class/drm/cardN/device/hwmon/hwmonM/
    dirs = sorted(glob.glob(os.path.join(card_path, "device", "hwmon", "hwmon*")))
    return dirs[0] if dirs else None


# ---------------------------------------------------------------------------
# Prometheus text-format helpers
# ---------------------------------------------------------------------------

class MetricFamily:
    def __init__(self, name: str, help_text: str, mtype: str = "gauge"):
        self.name = name
        self.help_text = help_text
        self.mtype = mtype
        self._samples: list[tuple] = []

    def add(self, value, labels: dict | None = None):
        if value is not None:
            self._samples.append((value, labels or {}))

    def render(self) -> str:
        if not self._samples:
            return ""
        lines = [
            f"# HELP {self.name} {self.help_text}",
            f"# TYPE {self.name} {self.mtype}",
        ]
        for value, labels in self._samples:
            if labels:
                lstr = "{" + ",".join(f'{k}="{v}"' for k, v in labels.items()) + "}"
            else:
                lstr = ""
            lines.append(f"{self.name}{lstr} {value}")
        return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Metric collection
# ---------------------------------------------------------------------------

def collect() -> str:
    cards = find_amd_cards()

    busy       = MetricFamily("amdgpu_gpu_busy_percent",   "GPU engine utilization, percent (0–100)")
    vram_used  = MetricFamily("amdgpu_vram_used_bytes",    "VRAM currently in use, bytes")
    vram_total = MetricFamily("amdgpu_vram_total_bytes",   "VRAM total capacity, bytes")
    gtt_used   = MetricFamily("amdgpu_gtt_used_bytes",     "GTT (system RAM pinned as VRAM overflow), bytes")
    temp       = MetricFamily("amdgpu_temperature_celsius","GPU temperature by sensor, degrees Celsius")
    power      = MetricFamily("amdgpu_power_watts",        "GPU average power draw, watts")
    core_clk   = MetricFamily("amdgpu_core_clock_hz",      "GPU core (GFX) clock, Hz")
    mem_clk    = MetricFamily("amdgpu_memory_clock_hz",    "GPU memory clock, Hz")
    fan        = MetricFamily("amdgpu_fan_rpm",            "GPU fan speed, RPM")
    voltage    = MetricFamily("amdgpu_voltage_millivolts", "GPU voltage by sensor, millivolts")

    for card_path in cards:
        lbl  = _card_labels(card_path)
        dev  = os.path.join(card_path, "device")

        # DRM device-level counters
        busy.add(_read_int(os.path.join(dev, "gpu_busy_percent")),      lbl)
        vram_used.add(_read_int(os.path.join(dev, "mem_info_vram_used")), lbl)
        vram_total.add(_read_int(os.path.join(dev, "mem_info_vram_total")), lbl)
        gtt_used.add(_read_int(os.path.join(dev, "mem_info_gtt_used")),   lbl)

        hwmon = find_hwmon(card_path)
        if not hwmon:
            continue

        # Temperatures — iterate all temp*_input entries
        for tin in sorted(glob.glob(os.path.join(hwmon, "temp*_input"))):
            idx = re.search(r"temp(\d+)_input", tin).group(1)
            sensor = (_read_str(os.path.join(hwmon, f"temp{idx}_label")) or f"temp{idx}").lower()
            val = _read_int(tin)
            if val is not None:
                temp.add(round(val / 1000.0, 1), {**lbl, "sensor": sensor})

        # Power: power1_average (µW), fallback to power1_input
        p = _read_int(os.path.join(hwmon, "power1_average"))
        if p is None:
            p = _read_int(os.path.join(hwmon, "power1_input"))
        if p is not None:
            power.add(round(p / 1_000_000.0, 3), lbl)

        # Clocks
        core_clk.add(_read_int(os.path.join(hwmon, "freq1_input")), lbl)
        mem_clk.add( _read_int(os.path.join(hwmon, "freq2_input")), lbl)

        # Fan
        fan.add(_read_int(os.path.join(hwmon, "fan1_input")), lbl)

        # Voltages — iterate all in*_input entries (mV, already in mV in amdgpu driver)
        for vin in sorted(glob.glob(os.path.join(hwmon, "in*_input"))):
            idx = re.search(r"in(\d+)_input", vin).group(1)
            sensor = (_read_str(os.path.join(hwmon, f"in{idx}_label")) or f"in{idx}").lower()
            voltage.add(_read_int(vin), {**lbl, "sensor": sensor})

    families = [busy, vram_used, vram_total, gtt_used, temp, power, core_clk, mem_clk, fan, voltage]
    return "\n".join(f.render() for f in families if f._samples)


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/metrics"):
            body = collect().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        pass  # suppress per-request log noise


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"amdgpu-exporter listening on :{PORT}/metrics", flush=True)
    server.serve_forever()
