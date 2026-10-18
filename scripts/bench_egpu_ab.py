#!/usr/bin/env python3
"""
bench_egpu_ab.py — A/B benchmark for the llamacpp-egpu server (RX 7900 XTX eGPU).

Compares, on the SAME model and the SAME prompts:
  1. vanilla             llama-cpp-rocm:latest   egpu-SWIFT-1.5-Qwen3.8-27B-Q4KM_KVQ4
  2. rdna-adaptive       llama-cpp-rocm:rdna     egpu-SWIFT-1.5-Qwen3.8-27B-Q4KM_KVQ4-adaptive

This is the PRODUCTION set (chosen 2026-10-10 after the r37 A/B sweep, see the
comment block on the -adaptive entry in llamacpp/models-egpu-rdna.ini):
vanilla is the stock-baseline anchor, rdna-adaptive is the production llm
config. The r37 sweep's other variants (plain d3, nmax9, p6, p9, d2, d1,
pmin07, ngram-off) were dropped — five measured worse, three competitive but
fixed-depth (no adaptivity). Re-add them (or new ones) only when a new
rdna-boosts release hints at new configs to test.

The script switches images itself (rewrites LLAMA_EGPU_IMAGE in .env,
`docker compose up -d llamacpp-egpu`, waits for health) and restores .env on
exit (finally). Configs 2-6 share the rdna image, so a full run performs
exactly 2 container recreations.

Measurements per config:
  * warmup request (model load; excluded from stats)
  * throughput: N reps of a ~4k-token open-ended reasoning prompt (5 number
    variants to defeat the server's KV cache-reuse), streamed, max_tokens cap
    (default 16384). Records TTFT, server-reported prefill/decode t/s,
    draft acceptance (MTP), wall time, finish_reason, cached_tokens.
  * evaluation: agentic prompt set from bench_eval_prompts.json at
    temperature=0, seed=42; assertion-based scoring + corruption scan
    (//// marker, repeated-token loops).

Optional OMP self-diagnostic pass (see --omp-passive): re-runs the throughput
reps of ONE config with OMP_WAIT_POLICY=PASSIVE KMP_BLOCKTIME=0 in the
container env. If MTP t/s jumps, the model's input embeddings are host-mapped
and OpenMP active-wait spinning was depressing the measurement (rdna-boosts
2026-09-24 methodology note); if nothing changes, there is no CPU input split.

Results: <out>/config-<name>.json (flushed after every rep), <out>/summary.md,
appended rows in <out>/../history.csv.

Stdlib only. Run from anywhere:  python3 scripts/bench_egpu_ab.py [--dry-run]

WARNING: image switches recreate the llamacpp-egpu container — any pi session
running inside it is dropped. Run this from a normal bash shell.
"""

import argparse
import csv
import json
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

# ── Constants ─────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / ".env"
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"
EVAL_PROMPTS_FILE = Path(__file__).resolve().parent / "bench_eval_prompts.json"
SERVICE = "llamacpp-egpu"
BASE_URL = "http://localhost:8092"
ENV_KEY = "LLAMA_EGPU_IMAGE"

# The compose service mounts models-egpu.ini, which is a symlink (docker
# follows it at container creation). The vanilla image's stock binary cannot
# parse the draft-mtp-adaptive preset entry (upstream PR #27210 unmerged —
# the flag exists only in the rdna-boosts patch set), so the preset must be
# swapped per image: rdna -> models-egpu-rdna.ini (11 models, incl. the
# rdna-adaptive production entry), vanilla -> models-egpu.ini (11 models,
# vanilla-safe).
ACTIVE_INI = REPO_ROOT / "llamacpp" / "models-egpu.ini"
INI_VANILLA = REPO_ROOT / "llamacpp" / "models-egpu-vanilla.ini"
INI_RDNA = REPO_ROOT / "llamacpp" / "models-egpu-rdna.ini"


def ini_for_image(image: str) -> Path:
    return INI_RDNA if image == "llama-cpp-rocm:rdna" else INI_VANILLA


def set_active_ini(image: str) -> None:
    target = ini_for_image(image)
    if not target.exists():
        sys.exit(f"ERROR: preset file missing: {target}")
    if ACTIVE_INI.is_symlink() and ACTIVE_INI.resolve() == target.resolve():
        return
    ACTIVE_INI.unlink(missing_ok=True)
    ACTIVE_INI.symlink_to(target.name)  # relative symlink, stays valid if repo moves
    log(f"active preset -> {target.name}")


def active_ini_target() -> str | None:
    if ACTIVE_INI.is_symlink():
        return ACTIVE_INI.resolve().name
    return None

CONFIGS = [
    {"name": "vanilla",       "image": "llama-cpp-rocm:latest", "model": "egpu-SWIFT-1.5-Qwen3.8-27B-Q4KM_KVQ4"},
    {"name": "rdna-adaptive", "image": "llama-cpp-rocm:rdna",   "model": "egpu-SWIFT-1.5-Qwen3.8-27B-Q4KM_KVQ4-adaptive"},
]

IMAGE_REBUILD_CMDS = {
    "llama-cpp-rocm:latest": "docker build -f llamacpp/Dockerfile.rocm -t llama-cpp-rocm:latest llamacpp/",
    "llama-cpp-rocm:rdna": (
        "docker build -f llamacpp/Dockerfile.rocm-builder-rdna -t llama-rocm-builder-rdna:latest llamacpp/ && "
        "docker build -f llamacpp/Dockerfile.rocm --build-arg BUILDER_IMAGE=llama-rocm-builder-rdna:latest "
        "-t llama-cpp-rocm:rdna llamacpp/"
    ),
}

# ── Throughput prompt (open-ended reasoning; 5 number variants) ───────────────
# Variants change every number so the server's KV cache-reuse (prefix caching)
# cannot serve a repeated prompt; each rep asserts cached_tokens == 0.

VARIANTS = [
    dict(n_customers=1240, n_inbound=48200, n_outbound=46900, n_doors=14, n_door_rate=310,
         n_shift_hours=8, n_operators=3, n_handle_min=1.9, p_misort=1.2, c_misort=6.5, c_labor=24,
         n_ot_cap=10, n_sorter_rate=2400, c_sorter=1850, p_misort_auto=0.4, c_install=420000,
         n_peak_in=6, n_peak_weeks=12, p_peak=38, c_budget=900000, p_misort_max=1.5, c_penalty=12000),
    dict(n_customers=980, n_inbound=39400, n_outbound=38100, n_doors=12, n_door_rate=295,
         n_shift_hours=8, n_operators=3, n_handle_min=2.1, p_misort=1.5, c_misort=7.0, c_labor=22,
         n_ot_cap=8, n_sorter_rate=2100, c_sorter=1650, p_misort_auto=0.5, c_install=380000,
         n_peak_in=8, n_peak_weeks=10, p_peak=45, c_budget=750000, p_misort_max=1.8, c_penalty=10000),
    dict(n_customers=1510, n_inbound=55800, n_outbound=54200, n_doors=16, n_door_rate=325,
         n_shift_hours=9, n_operators=4, n_handle_min=1.7, p_misort=0.9, c_misort=6.0, c_labor=26,
         n_ot_cap=12, n_sorter_rate=2600, c_sorter=2050, p_misort_auto=0.3, c_install=460000,
         n_peak_in=5, n_peak_weeks=14, p_peak=32, c_budget=1100000, p_misort_max=1.2, c_penalty=15000),
    dict(n_customers=760, n_inbound=31200, n_outbound=30400, n_doors=10, n_door_rate=280,
         n_shift_hours=8, n_operators=2, n_handle_min=2.3, p_misort=1.8, c_misort=7.5, c_labor=21,
         n_ot_cap=6, n_sorter_rate=1900, c_sorter=1500, p_misort_auto=0.6, c_install=340000,
         n_peak_in=10, n_peak_weeks=8, p_peak=52, c_budget=600000, p_misort_max=2.0, c_penalty=9000),
    dict(n_customers=1330, n_inbound=44600, n_outbound=43800, n_doors=13, n_door_rate=305,
         n_shift_hours=8, n_operators=3, n_handle_min=2.0, p_misort=1.1, c_misort=6.8, c_labor=23,
         n_ot_cap=10, n_sorter_rate=2250, c_sorter=1750, p_misort_auto=0.4, c_install=400000,
         n_peak_in=7, n_peak_weeks=12, p_peak=41, c_budget=850000, p_misort_max=1.4, c_penalty=11000),
]

WEEK_FACTORS = [0.94, 0.97, 0.99, 0.96, 1.01, 1.03, 1.00, 1.05, 1.02, 1.08, 1.06, 1.11]
DAY_FACTORS = [1.02, 1.01, 0.99, 1.03, 1.08, 0.88, 0.85]  # Mon..Sun (weekend dip)
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
LINE_SHARES = [0.16, 0.14, 0.13, 0.12, 0.12, 0.11, 0.11, 0.11]
LINE_EXCEPTIONS = ["label damage", "address correction", "oversize reroute", "damaged on intake",
                   "customs hold", "return-to-sender", "wrong dock scan", "fragile flag miss"]

THROUGHPUT_TEMPLATE = """You are a senior operations analyst at a parcel logistics company. Work through the capacity-planning problem below step by step. Show your reasoning explicitly: state every assumption, compute intermediate figures, explore at least two alternative strategies with their trade-offs, sanity-check your arithmetic as you go, and only then give a final recommendation with concrete numbers.

SCENARIO
A regional hub processes parcels for {n_customers} retail customers.

Current state (off-peak):
- Inbound parcels per day: {n_inbound}
- Outbound parcels per day: {n_outbound}
- Dock doors: {n_doors}; a staffed door processes {n_door_rate} parcels per hour
- Shifts: 2 shifts of {n_shift_hours} hours; {n_operators} operators per door per shift
- Average manual handling time: {n_handle_min} minutes per parcel
- Mis-sort rate: {p_misort} percent
- Mis-sort remediation cost: ${c_misort} per parcel
- Operator labor: ${c_labor} per hour; overtime at 1.5x, capped at {n_ot_cap} hours per operator per week

Available investment:
- Automated sorter: {n_sorter_rate} parcels per hour, ${c_sorter} per day to operate, reduces mis-sort rate to {p_misort_auto} percent, one-time install ${c_install} (amortize over 3 years, 365 days)

Peak season:
- Starts in {n_peak_in} weeks, lasts {n_peak_weeks} weeks
- Inbound volume rises by {p_peak} percent for the whole peak window

Twelve weeks of observed inbound volume (parcels per day, by weekday), oldest first:
{volume_table}

LINE DETAILS (per sorting line, off-peak averages)
{line_table}

LABOR AGREEMENT EXCERPTS (relevant clauses)
1. Regular hours are 8 per shift; any hour beyond regular hours is overtime at 1.5x base rate.
2. Overtime is capped at {n_ot_cap} hours per operator per week and requires 48h notice.
3. Cross-training: an operator may cover a second door only if certified; currently 60 percent of operators are dual-certified.
4. The union allows up to 8 temporary operators per peak season at 1.2x base rate, with a 2-week lead time.
5. Breaks are 2 x 15 minutes per shift and are paid; they reduce effective door staffing time.
6. Night shift (second shift) carries a 10 percent shift premium on base rate.
7. Safety rule: a door must be unstaffed (closed) if fewer than 2 operators are available for it.
8. Any automation deployment requires 3 weeks of parallel running before the manual line is reduced.

STAKEHOLDER REQUIREMENTS
- The VP of Network wants peak-season on-time dispatch of at least 97 percent.
- Finance caps the annual incremental cost of any strategy at ${c_budget} over the do-nothing baseline.
- The head of Customer Experience requires the mis-sort rate to stay below {p_misort_max} percent in every week, peak or not.
- Real estate confirms no new dock doors can be added before next fiscal year.
- IT can integrate the sorter's telemetry within 2 weeks at no cost.
- The hub manager prefers strategies that do not require more than 12 additional headcount at any time.

CONTRACT PENALTIES
- If on-time dispatch falls below 95 percent in any peak week, the hub pays ${c_penalty} per 0.1 percent shortfall.
- If mis-sort rate exceeds {p_misort_max} percent in any week, remediation cost doubles for that week (expedited re-routing).

SITE & EQUIPMENT INVENTORY
- {n_doors} dock doors (12 active, 2 in maintenance rotation), door width 3.2 m
- 8 conveyor lines, total length 1.2 km, belt speed 1.5 m/s
- 2 tilt-truck bays for manual loading, 4 for automated
- Sorting wall: 96 chutes, 12 scan stations, 2 exception lanes
- 3 forklifts (2 electric, 1 diesel backup), 12 pallet jacks
- Weighing integration at intake: 4 scales, 99.2 percent accuracy last quarter
- Label printer farm: 18 thermal printers, 2 re-label stations
- Bagging station: 6 operators, 420 bags per hour at target rate
- Security screening: 2 X-ray lanes, 110 parcels per minute each
- IT: 34 handheld scanners, 12 desktop terminals, warehouse WLAN (dual-band)
- Environmental: HVAC rated for 40 concurrent workers; lighting LED, 90 percent on during shifts
- Maintenance: 1 in-house technician, 24h vendor SLA for conveyor drives

RECENT CHANGE LOG (last 90 days)
- 2026-04-02: door 11 back from maintenance; throughput test passed at 305 parcels/h
- 2026-04-18: scan station 7 replaced; mis-sort attribution improved 0.1 percent
- 2026-05-06: new bagging SOP rolled out; bagging rate up 6 percent
- 2026-05-21: WMS upgrade v9.4; route optimization changed dock assignment rules
- 2026-06-03: two operators cross-trained to dual certification
- 2026-06-15: sorter vendor completed site survey; install quote issued
- 2026-06-27: peak-season labor request submitted to union (8 temporary operators)
- 2026-07-01: security lane 2 throughput audit: 96 percent of rated capacity
- 2026-07-08: belt tension recalibrated on lines C and D; jam rate down 12 percent
- 2026-07-10: this planning cycle opened; all figures above current as of this date

HISTORICAL INCIDENTS (last 6 months, most recent last)
- 2026-02-14: conveyor line F jam cascade; 42 min downtime; 1,850 parcels re-sequenced; on-time dispatch 96.1 percent that day
- 2026-03-02: scanner firmware bug misread 3 percent of labels; 210 mis-sorts; vendor patch same day
- 2026-03-29: power flicker reset WMS; 25 min of manual routing; no customer impact
- 2026-04-22: peak-rehearsal drill; overtime at 92 percent of cap; two doors closed per safety rule
- 2026-05-11: forklift collision with chute 41; 35 min repair; 12 parcels damaged
- 2026-05-30: address-correction backlog hit 4,000; cleared in 3 days with 4 temporary operators
- 2026-06-19: customs hold spike (holiday in origin country); 8 percent of inbound held 48h
- 2026-07-05: mis-sort rate touched 1.9 percent for one day (new hire cohort); back to baseline after retraining

STAKEHOLDER Q&A (hub manager, 2026-07-09)
Q: What breaks first in peak, doors or people?
A: People. Doors are fine to about 110 percent of rated volume if we run both shifts full; we run out of certified operators before we run out of belt time.
Q: How realistic is the 97 percent on-time target?
A: Realistic off-peak. In peak it depends on the overtime cap - last year we missed it in two of twelve peak weeks.
Q: Any appetite for the sorter?
A: Yes, if it pays for itself within three years and does not require re-housing the team. The parallel-running month is the part that worries me: we lose 15 percent of manual capacity during it.
Q: What about the temporary operators?
A: The union said 8 is the ceiling. They are 85 percent as productive as permanent staff in their first two weeks.
Q: Anything else I should know?
A: The 18:00 cutoff is contractual with three of the largest customers. Missing it triggers the penalty clause, not just the KPI.

SORTER VENDOR PROPOSAL EXCERPT (2026-06-15)
- Machine: tilt-tray sorter, rated at the stated parcels/hour at label-read success >= 99.5 percent
- Footprint: 420 m2 in the northeast corner; requires relocating the bagging station (2 weeks, 1 FTE)
- Install: 6 weeks on site, including the 3-week parallel-running window required by the labor agreement
- Power: 3-phase 60A dedicated; the site has one spare circuit, so an electrician visit (1 day) is needed
- Integration: WMS v9.4 supported out of the box; scan-wall API adapter included
- Service: 4h response SLA, 98 percent parts availability, filter kits included for year 1
- Resale: vendor buy-back at 40 percent of install price after 3 years if decommissioned
- Caveat from the vendor: rated throughput assumes label-read success >= 99.5 percent; our current label-read success is 98.7 percent, so expect roughly 3-5 percent derating until the label program improves

ASSUMPTIONS YOU MUST STATE EXPLICITLY IN YOUR ANALYSIS
- Any utilization factor you apply to rated capacities (doors, sorter, belt time)
- How you treat the 3-week parallel-running capacity loss in the 52-week horizon
- How you model the 85 percent productivity of temporary operators in their first two weeks
- Whether the label-read derating applies to the sorter in year 1
- How you allocate the 10 percent night-shift premium across the two shifts
- Your discounting: state whether you use simple annual sums (no discounting) - the finance cap is stated in simple annual terms

GLOSSARY (internal terms used in this document)
- Dock door: a loading bay with one conveyor connection; the unit of inbound/outbound capacity.
- Certified operator: an operator cleared to run a door unassisted after the 40h training program.
- Mis-sort: a parcel routed to the wrong destination line; measured at the scan wall.
- Re-sequencing: re-prioritizing parcels after a disruption so the 18:00 cutoff still holds.
- Peak window: the period of elevated volume ending with the holiday shipping deadline.
- Parallel running: operating the new sorter alongside the manual line to validate sort accuracy.
- Chute: one of the 96 destination bins on the sorting wall.
- Belt time: total conveyor operating hours available in a shift after maintenance windows.
- Exception lane: a manual lane for parcels the automated path cannot process.
- Cutoff: the contractual 18:00 local departure time for linehaul.

KPI DEFINITIONS (use these exact definitions in your analysis)
- On-time dispatch: share of outbound parcels leaving the hub before the contractual cutoff (18:00 local).
- Effective door rate: parcels per staffed door-hour after subtracting paid break time and the observed handling time.
- Binding constraint: the resource (door-hours, operators, sorter capacity, or money) that first caps throughput if all others grew 10 percent.
- Peak service risk: probability-weighted estimate (state your weights) that on-time dispatch falls below 95 percent in at least one peak week.
- Annual incremental cost: strategy cost minus do-nothing cost over 52 weeks, including penalties.
- Break-even growth: the peak volume growth at which the sorter strategy's annual incremental cost equals the overtime-only strategy's.
- Mis-sort exposure: expected remediation cost per day at the current mis-sort rate and current volume.
- Amortized install: one-time install cost divided by 365*3 days, added to daily sorter operating cost.
- Overtime headroom: remaining legal overtime hours per operator per week after covering the off-peak shortfall, if any.
- Headcount delta: maximum additional FTEs (permanent + temporary) required by the strategy at any point in the 52-week horizon.

QUESTIONS
1. Compute the current effective daily throughput of the manual line (doors x hours x rate, adjusted for the observed handling time and paid breaks) and identify the binding constraint using the definition above.
2. Compute expected daily mis-sort cost today and during peak (mis-sort exposure definition).
3. Over a 52-week horizon, estimate total annual cost for each strategy:
   (a) do nothing (absorb peak with overtime where possible; quantify the shortfall if not),
   (b) overtime only (at the maximum legal cap, including the 8 temporary operators if needed),
   (c) automated sorter plus minimal overtime.
   Include labor, overtime, temporary labor, mis-sort remediation, contract penalties where they trigger, and sorter operating plus amortized install cost.
4. State the break-even condition for the sorter as an explicit inequality in terms of peak volume growth, and solve it with the numbers given.
5. Recommend one strategy. Quantify the annual cost delta versus the next-best strategy and the peak-season service risk of your choice, naming which stakeholder requirement binds.
6. For your recommended strategy, produce a week-by-week staffing plan for the first 4 weeks of peak (operators per shift per door, overtime hours per operator, temporary operators on site), and state which week is the tightest and by how much.

Be thorough and quantitative. Prefer exact arithmetic; where you must approximate, say so and bound the error."""


def build_throughput_prompt(variant_idx: int) -> str:
    v = VARIANTS[variant_idx % len(VARIANTS)]
    weekly = v["n_inbound"] * 7
    volume_rows = []
    for i, f in enumerate(WEEK_FACTORS):
        weekly_val = weekly * f
        days = [f"{DAYS[d]} {int(round(weekly_val * DAY_FACTORS[d] / 7 / 10.0)) * 10}"
                for d in range(7)]
        volume_rows.append(f"  week -{12 - i:2d}: " + "  ".join(days))
    line_rows = []
    for i, share in enumerate(LINE_SHARES):
        lw = int(round(weekly * share / 10.0)) * 10
        mr = round(v["p_misort"] * (1.0 + 0.12 * i - 0.3), 2)
        line_rows.append(
            f"  line {chr(65 + i)}: 2 doors, {lw} parcels/week, mis-sort {mr}%, "
            f"top exception: {LINE_EXCEPTIONS[i]}"
        )
    return THROUGHPUT_TEMPLATE.format(
        volume_table="\n".join(volume_rows),
        line_table="\n".join(line_rows),
        **v,
    )


# ── Logging / IO helpers ──────────────────────────────────────────────────────

def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def save_json(path: Path, data) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(path)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ── HTTP ──────────────────────────────────────────────────────────────────────

def http_get_json(url: str, timeout: float = 10.0):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode())


def stream_chat(model: str, prompt: str, max_tokens: int,
                temperature=None, seed=None, timeout: float = 1200.0) -> dict:
    """One streaming chat completion. Returns text, reasoning, usage, timings,
    TTFT (client-side, to first content/reasoning token)."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if temperature is not None:
        payload["temperature"] = temperature
    if seed is not None:
        payload["seed"] = seed
    req = urllib.request.Request(
        BASE_URL + "/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.monotonic()
    ttft = None
    content_parts, reasoning_parts = [], []
    usage, timings, finish_reason, fingerprint = None, None, None, None
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            chunk = json.loads(data)
            choices = chunk.get("choices") or [{}]
            delta = choices[0].get("delta") or {}
            rc, c = delta.get("reasoning_content"), delta.get("content")
            if rc:
                reasoning_parts.append(rc)
            if c:
                content_parts.append(c)
            if ttft is None and (rc or c):
                ttft = time.monotonic() - t0
            if chunk.get("usage"):
                usage = chunk["usage"]
            if chunk.get("timings"):
                timings = chunk["timings"]
            if chunk.get("system_fingerprint"):
                fingerprint = chunk["system_fingerprint"]
            fr = choices[0].get("finish_reason")
            if fr:
                finish_reason = fr
    return {
        "content": "".join(content_parts),
        "reasoning": "".join(reasoning_parts),
        "usage": usage,
        "timings": timings,
        "finish_reason": finish_reason,
        "ttft_s": ttft,
        "system_fingerprint": fingerprint,
    }


# ── Docker / compose ──────────────────────────────────────────────────────────

def docker_current_image() -> str | None:
    p = subprocess.run(
        ["docker", "inspect", "--format", "{{.Config.Image}}", SERVICE],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    return p.stdout.strip() if p.returncode == 0 else None


def docker_image_exists(image: str) -> bool:
    p = subprocess.run(["docker", "image", "inspect", image], capture_output=True)
    return p.returncode == 0


def set_env_image(image: str) -> None:
    lines = ENV_FILE.read_text().splitlines()
    for i, line in enumerate(lines):
        if line.startswith(ENV_KEY + "="):
            lines[i] = f"{ENV_KEY}={image}"
            break
    else:
        lines.append(f"{ENV_KEY}={image}")
    ENV_FILE.write_text("\n".join(lines) + "\n")


def compose_up() -> None:
    subprocess.run(["docker", "compose", "up", "-d", SERVICE],
                   cwd=REPO_ROOT, check=True)


# The OMP self-diagnostic pass (see --omp-passive) needs OMP_WAIT_POLICY and
# KMP_BLOCKTIME inside the container. The compose service has a static
# environment: list, so we temporarily insert the two lines (same
# save/modify/restore pattern as .env) and recreate the container.
COMPOSE_ENV_MARKER = "      - LD_LIBRARY_PATH=/usr/local/lib:/opt/rocm/lib\n"
COMPOSE_OMP_LINES = ("      - OMP_WAIT_POLICY=PASSIVE\n"
                     "      - KMP_BLOCKTIME=0\n")


def compose_omp_env(enabled: bool) -> None:
    text = COMPOSE_FILE.read_text()
    if enabled:
        if "OMP_WAIT_POLICY" not in text:
            if COMPOSE_ENV_MARKER not in text:
                sys.exit("ERROR: compose env marker not found; cannot inject OMP vars")
            COMPOSE_FILE.write_text(text.replace(COMPOSE_ENV_MARKER,
                                                 COMPOSE_ENV_MARKER + COMPOSE_OMP_LINES, 1))
            log("docker-compose.yml: OMP_WAIT_POLICY=PASSIVE KMP_BLOCKTIME=0 injected")
    elif COMPOSE_OMP_LINES in text:
        COMPOSE_FILE.write_text(text.replace(COMPOSE_ENV_MARKER + COMPOSE_OMP_LINES,
                                             COMPOSE_ENV_MARKER, 1))
        log("docker-compose.yml: OMP vars removed")


def wait_health(timeout_s: float = 300.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            if http_get_json(BASE_URL + "/health", timeout=3).get("status") == "ok":
                return True
        except Exception:
            pass
        time.sleep(2)
    return False


def list_models() -> set:
    return {m["id"] for m in http_get_json(BASE_URL + "/v1/models")["data"]}


def switch_to(image: str) -> None:
    cur = docker_current_image()
    if cur == image and active_ini_target() == ini_for_image(image).name:
        log(f"container already on {image} with matching preset")
        return
    log(f"SWITCH: recreating {SERVICE} on {image} (was: {cur})")
    set_active_ini(image)  # BEFORE compose up: the mount captures the target at creation
    set_env_image(image)
    compose_up()
    if not wait_health(300):
        raise RuntimeError(f"server not healthy within 300 s after switch to {image}")
    got = docker_current_image()
    if got != image:
        raise RuntimeError(f"image mismatch after switch: wanted {image}, got {got}")
    log(f"switch complete: {SERVICE} on {image}, health ok")


# ── JSON extraction + check engine ────────────────────────────────────────────

def extract_json_values(text: str):
    """All top-level balanced JSON values found in text, in order (parsed)."""
    out = []
    n = len(text)
    i = 0
    while i < n:
        if text[i] not in "{[":
            i += 1
            continue
        depth, in_str, esc, j = 0, False, False, i
        while j < n:
            ch = text[j]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch in "{[":
                    depth += 1
                elif ch in "}]":
                    depth -= 1
                    if depth == 0:
                        break
            j += 1
        if j < n and depth == 0:
            try:
                out.append(json.loads(text[i:j + 1]))
                i = j + 1  # skip past a valid span (nested spans are part of it)
                continue
            except json.JSONDecodeError:
                pass
        i += 1
    return out


def _ctx_json(ctx):
    if "json" not in ctx:
        raise ValueError("no preceding 'json' check extracted a value")
    return ctx["json"]


def check_json(spec, text, ctx):
    vals = extract_json_values(text)
    if not vals:
        return False, "no JSON value found in content"
    val = vals[0] if spec.get("which", "first") == "first" else vals[-1]
    expect = spec.get("expect", "object")
    ok = (expect == "object" and isinstance(val, dict)) or \
         (expect == "array" and isinstance(val, list))
    if ok:
        ctx["json"] = val
    return ok, f"extracted {type(val).__name__} (wanted {expect})"


def check_json_keys(spec, text, ctx):
    val = _ctx_json(ctx)
    missing = [k for k in spec["keys"] if k not in val]
    return not missing, f"missing keys: {missing}" if missing else "all keys present"


def check_json_array_len(spec, text, ctx):
    val = _ctx_json(ctx)
    return len(val) == spec["len"], f"len={len(val)} (wanted {spec['len']})"


def check_json_field_set(spec, text, ctx):
    val = _ctx_json(ctx)
    got = {e.get(spec["field"]) for e in val if isinstance(e, dict)}
    want = set(spec["expected"])
    return got == want, f"got {sorted(map(str, got))}, wanted {sorted(map(str, want))}"


def check_json_exact(spec, text, ctx):
    val = _ctx_json(ctx)
    want = spec["expected"]
    if not isinstance(val, dict) or set(val) != set(want):
        return False, f"key sets differ: got {sorted(map(str, val.keys())) if isinstance(val, dict) else type(val).__name__}"
    for k in want:
        a, b = val[k], want[k]
        if isinstance(a, list) and isinstance(b, list):
            a, b = sorted(map(str, a)), sorted(map(str, b))
        if a != b:
            return False, f"key {k!r}: got {a!r}, wanted {b!r}"
    return True, "exact match"


def check_json_tool_steps(spec, text, ctx):
    val = _ctx_json(ctx)
    steps = val.get("steps")
    if not isinstance(steps, list) or not (1 <= len(steps) <= spec.get("max", 6)):
        return False, f"steps is not a 1..{spec.get('max', 6)} list: {type(steps).__name__}"
    allowed = set(spec["allowed"])
    for i, s in enumerate(steps):
        if not isinstance(s, dict) or s.get("tool") not in allowed:
            return False, f"step {i}: bad tool {s.get('tool') if isinstance(s, dict) else s!r}"
        if not isinstance(s.get("args"), dict):
            return False, f"step {i}: args not an object"
        if not isinstance(s.get("purpose"), str) or not s["purpose"].strip():
            return False, f"step {i}: purpose missing/empty"
    return True, f"{len(steps)} steps, all tools allowed"


def check_json_enum(spec, text, ctx):
    val = _ctx_json(ctx)
    got = val.get(spec["field"])
    return got in spec["values"], f"{spec['field']}={got!r} (wanted one of {spec['values']})"


def check_contains_all(spec, text, ctx):
    missing = [s for s in spec["items"] if s not in text]
    return not missing, f"missing: {missing}" if missing else "all substrings present"


def check_fenced_block(spec, text, ctx):
    lang = spec.get("lang")
    pat = rf"```{re.escape(lang)}\n" if lang else r"```[a-zA-Z0-9_+-]*\n"
    m = re.search(pat + r".*?```", text, re.DOTALL)
    return m is not None, f"{'found' if m else 'no'} fenced {lang or ''} block"


CHECKS = {
    "json": check_json,
    "json_keys": check_json_keys,
    "json_array_len": check_json_array_len,
    "json_field_set": check_json_field_set,
    "json_exact": check_json_exact,
    "json_tool_steps": check_json_tool_steps,
    "json_enum": check_json_enum,
    "contains_all": check_contains_all,
    "fenced_block": check_fenced_block,
}


def corruption_scan(text: str):
    """The repo's own corruption marker (////) + short-segment token loops."""
    issues = []
    if "////" in text:
        issues.append("//// marker present")
    n = len(text)
    for p in range(4, 41):
        seg_len = p * 8
        if n < seg_len:
            break
        for i in range(0, n - seg_len, p):
            seg = text[i:i + p]
            if seg * 8 == text[i:i + seg_len]:
                issues.append(f"loop period {p}: {seg[:40]!r} x8")
                return issues
    return issues


def run_checks(spec: dict, text: str):
    ctx = {}
    results = []
    for check in spec["checks"]:
        fn = CHECKS.get(check["type"])
        if fn is None:
            results.append({"check": check["type"], "pass": False, "detail": "unknown check type"})
            continue
        try:
            ok, detail = fn(check, text, ctx)
        except Exception as e:  # a check bug must fail the prompt, not the run
            ok, detail = False, f"check error: {e}"
        results.append({"check": check["type"], "pass": ok, "detail": detail})
    return results


# ── Benchmark runners ─────────────────────────────────────────────────────────

def run_warmup(model: str) -> None:
    log("warmup request (pays model load; excluded from stats)...")
    t0 = time.monotonic()
    r = stream_chat(model, "Reply with the single word: ok", max_tokens=8, timeout=900)
    log(f"warmup done in {time.monotonic() - t0:.0f}s "
        f"({len(r['content']) + len(r['reasoning'])} chars back)")


def run_throughput(model: str, args, out_path: Path) -> dict:
    data = {"reps": []}
    for i in range(args.reps):
        prompt = build_throughput_prompt(i % len(VARIANTS))
        log(f"throughput rep {i + 1}/{args.reps}: prompt {len(prompt)} chars, "
            f"generating up to {args.gen_tokens} tokens...")
        t0 = time.monotonic()
        r = stream_chat(model, prompt, max_tokens=args.gen_tokens, timeout=args.request_timeout)
        wall = time.monotonic() - t0
        usage, timings = r["usage"] or {}, r["timings"] or {}
        rep = {
            "rep": i + 1,
            "prompt_chars": len(prompt),
            "prompt_tokens": usage.get("prompt_tokens"),
            "cached_tokens": (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0),
            "completion_tokens": usage.get("completion_tokens"),
            "ttft_s": round(r["ttft_s"], 3) if r["ttft_s"] is not None else None,
            "wall_s": round(wall, 1),
            "prompt_tps": timings.get("prompt_per_second"),
            "decode_tps": timings.get("predicted_per_second"),
            "draft_n": timings.get("draft_n"),
            "draft_n_accepted": timings.get("draft_n_accepted"),
            "finish_reason": r["finish_reason"],
            "fingerprint": r["system_fingerprint"],
        }
        if rep["cached_tokens"]:
            log(f"  WARNING rep {i + 1}: cached_tokens={rep['cached_tokens']} — "
                f"KV prefix-cache hit; prefill number for this rep is suspect")
        data["reps"].append(rep)
        save_json(out_path, data)  # incremental: a crash never loses finished reps
        log(f"  rep {i + 1}: prefill {rep['prompt_tps']:.1f} t/s, decode {rep['decode_tps']:.1f} t/s, "
            f"TTFT {rep['ttft_s']:.2f}s, wall {wall:.0f}s, "
            f"draft {rep['draft_n_accepted']}/{rep['draft_n']}, finish={rep['finish_reason']}")
    return data


def run_eval(model: str, eval_specs: dict, args, out_path: Path) -> list:
    results = []
    for spec in eval_specs["prompts"]:
        log(f"eval {spec['id']} ({spec.get('kind', '?')})...")
        t0 = time.monotonic()
        r = stream_chat(model, spec["prompt"], max_tokens=args.gen_tokens,
                        temperature=0, seed=42, timeout=args.request_timeout)
        text = r["content"]
        checks = run_checks(spec, text)
        corr = corruption_scan(text)
        passed = all(c["pass"] for c in checks) and not corr
        results.append({
            "id": spec["id"],
            "kind": spec.get("kind"),
            "pass": passed,
            "checks": checks,
            "corruption": corr,
            "completion_tokens": (r["usage"] or {}).get("completion_tokens"),
            "ttft_s": round(r["ttft_s"], 3) if r["ttft_s"] is not None else None,
            "wall_s": round(time.monotonic() - t0, 1),
            "finish_reason": r["finish_reason"],
            "reasoning_chars": len(r["reasoning"]),
            "content_chars": len(text),
            "reasoning": r["reasoning"],
            "content": text,
        })
        save_json(out_path, results)  # incremental
        n_ok = sum(c["pass"] for c in checks)
        log(f"  eval {spec['id']}: {'PASS' if passed else 'FAIL'} "
            f"({n_ok}/{len(checks)} checks, {len(corr)} corruption, "
            f"{(r['usage'] or {}).get('completion_tokens')} tokens, "
            f"{time.monotonic() - t0:.0f}s)")
    return results


# ── Summary / history ─────────────────────────────────────────────────────────

def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def config_stats(data: dict) -> dict:
    reps = data.get("throughput", {}).get("reps", [])
    evs = data.get("eval", [])
    draft = [(r["draft_n_accepted"], r["draft_n"]) for r in reps
             if r.get("draft_n") is not None and r.get("draft_n_accepted") is not None]
    return {
        "prefill_tps": _mean([r["prompt_tps"] for r in reps]),
        "decode_tps": _mean([r["decode_tps"] for r in reps]),
        "ttft_s": _mean([r["ttft_s"] for r in reps]),
        "draft_accept": (sum(a for a, _ in draft) / sum(b for _, b in draft)) if draft else None,
        "eval_pass": (sum(1 for e in evs if e["pass"]) / len(evs)) if evs else None,
        "n_reps": len(reps),
        "n_eval": len(evs),
    }


def write_summary(outdir: Path, results: dict) -> None:
    lines = [
        "# eGPU A/B benchmark summary",
        "",
        f"Generated: {now_iso()}",
        "",
        "| config | image | model | prefill t/s | decode t/s | TTFT s | draft accept | eval pass | reps |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]

    def pct_delta(a, b):
        """Relative % of b vs a; None if either is missing."""
        if a is None or b is None or a == 0:
            return None
        return (b - a) / a * 100

    def fmt_pct(x):
        return f"{x:+.1f}%" if x is not None else "\u2014"

    def fmt_val(x, spec):
        return format(x, spec) if x is not None else "\u2014"

    stats = {}
    for name, data in results.items():
        s = config_stats(data)
        stats[name] = s
        lines.append(
            f"| {name} | {data['image']} | {data['model']} "
            f"| {fmt_val(s['prefill_tps'], '.1f')} | {fmt_val(s['decode_tps'], '.1f')} | {fmt_val(s['ttft_s'], '.2f')} "
            f"| {fmt_val(s['draft_accept'], '.3f')} | {fmt_val(s['eval_pass'], '.0%')} | {s['n_reps']} |"
        )

    # ── Deltas vs vanilla: one row per non-vanilla config, all metrics ──
    lines += ["", "## Deltas vs vanilla (llama-cpp-rocm:latest)", ""]
    if "vanilla" in stats:
        v = stats["vanilla"]
        lines.append("| config | decode t/s | \u0394 decode | prefill t/s | \u0394 prefill | TTFT s | \u0394 TTFT | draft acc | eval pass |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
        for name, s in stats.items():
            if name == "vanilla":
                continue
            lines.append(
                f"| {name} | {fmt_val(s['decode_tps'], '.1f')} | {fmt_pct(pct_delta(v['decode_tps'], s['decode_tps']))} "
                f"| {fmt_val(s['prefill_tps'], '.1f')} | {fmt_pct(pct_delta(v['prefill_tps'], s['prefill_tps']))} "
                f"| {fmt_val(s['ttft_s'], '.2f')} | {fmt_pct(pct_delta(v['ttft_s'], s['ttft_s']))} "
                f"| {fmt_val(s['draft_accept'], '.3f')} | {fmt_val(s['eval_pass'], '.0%')} |"
            )
    else:
        lines.append("(vanilla config not in this run \u2014 nothing to compare against)")

    # ── Within-rdna matrix: lower triangle, row = baseline, cell = \u0394 decode % ──
    rdna_names = [n for n in stats if n != "vanilla"]
    if len(rdna_names) >= 2:
        lines += ["", "## Within-rdna decode t/s deltas (row = baseline, cell = % delta)", ""]
        lines.append("| baseline | " + " | ".join(rdna_names) + " |")
        lines.append("|---|" + "---:|" * len(rdna_names))
        for i, base in enumerate(rdna_names):
            row = [f"| {base}"]
            for j, other in enumerate(rdna_names):
                if j <= i:
                    row.append("\u2014")
                else:
                    row.append(fmt_pct(pct_delta(stats[base]["decode_tps"], stats[other]["decode_tps"])))
            lines.append(" | ".join(row) + " |")

    # ── Interpretation: labeled pairwise comparisons (print only when both sides exist) ──
    lines += ["", "## Interpretation (labeled)", ""]

    def delta(a, b, label):
        if a and b:
            pct = (b - a) / a * 100
            lines.append(f"- **{label}**: decode {pct:+.1f} %, prefill {(b / a - 1) * 100:+.1f} % "
                         f"(vs {a:.1f} t/s decode baseline)")

    if "vanilla" in stats and "rdna" in stats:
        delta(stats["vanilla"]["decode_tps"], stats["rdna"]["decode_tps"], "rdna vs vanilla (patch effect)")
    if "rdna" in stats and "rdna-adaptive" in stats:
        delta(stats["rdna"]["decode_tps"], stats["rdna-adaptive"]["decode_tps"],
              "rdna-adaptive vs rdna (adaptive MTP controller)")
        if stats["rdna"]["draft_accept"] is not None and stats["rdna-adaptive"]["draft_accept"] is not None:
            lines.append(f"- draft acceptance: rdna {stats['rdna']['draft_accept']:.3f} "
                         f"-> adaptive {stats['rdna-adaptive']['draft_accept']:.3f}")
    if "rdna-adaptive" in stats and "rdna-adaptive-nmax9" in stats:
        delta(stats["rdna-adaptive"]["decode_tps"], stats["rdna-adaptive-nmax9"]["decode_tps"],
              "rdna-adaptive-nmax9 vs rdna-adaptive (spec-draft-n-max 9 vs 3)")
        if stats["rdna-adaptive"]["draft_accept"] is not None and stats["rdna-adaptive-nmax9"]["draft_accept"] is not None:
            lines.append(f"- draft acceptance: adaptive {stats['rdna-adaptive']['draft_accept']:.3f} "
                         f"-> nmax9 {stats['rdna-adaptive-nmax9']['draft_accept']:.3f}")
    if "rdna-adaptive-nmax9-p9" in stats and "rdna-adaptive-nmax9" in stats:
        delta(stats["rdna-adaptive-nmax9-p9"]["decode_tps"], stats["rdna-adaptive-nmax9"]["decode_tps"],
              "adaptive-nmax9 vs pinned9 (controller value at depth 9; ~2% gap expected per the tuning record)")
    if "rdna-adaptive-nmax9-p6" in stats and "rdna-adaptive-nmax9" in stats:
        delta(stats["rdna-adaptive-nmax9-p6"]["decode_tps"], stats["rdna-adaptive-nmax9"]["decode_tps"],
              "adaptive-nmax9 vs pinned6 (depth effect: 9 vs fixed 6)")
    (outdir / "summary.md").write_text("\n".join(lines) + "\n")
    log(f"summary written: {outdir / 'summary.md'}")


def append_history(outdir: Path, results: dict) -> None:
    hist = outdir.parent / "history.csv"
    new = not hist.exists()
    with hist.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["timestamp", "config", "image", "model", "prefill_tps", "decode_tps",
                        "ttft_s", "draft_accept", "eval_pass", "n_reps", "gen_tokens"])
        for name, data in results.items():
            s = config_stats(data)
            w.writerow([now_iso(), name, data["image"], data["model"],
                        f"{s['prefill_tps']:.2f}" if s["prefill_tps"] else "",
                        f"{s['decode_tps']:.2f}" if s["decode_tps"] else "",
                        f"{s['ttft_s']:.3f}" if s["ttft_s"] else "",
                        f"{s['draft_accept']:.4f}" if s["draft_accept"] is not None else "",
                        f"{s['eval_pass']:.2f}" if s["eval_pass"] is not None else "",
                        s["n_reps"], data.get("gen_tokens", "")])
    log(f"history appended: {hist}")


# ── Preflight / selftest ──────────────────────────────────────────────────────

def preflight(configs) -> None:
    p = subprocess.run(["docker", "info"], capture_output=True)
    if p.returncode != 0:
        sys.exit("ERROR: docker daemon not reachable")
    if not ACTIVE_INI.is_symlink():
        sys.exit(f"ERROR: {ACTIVE_INI} is not a symlink. Create it: "
                 f"ln -sfn models-egpu-vanilla.ini models-egpu.ini (in llamacpp/)")
    for f in (INI_VANILLA, INI_RDNA):
        if not f.exists():
            sys.exit(f"ERROR: preset file missing: {f}")
    for img in sorted({c["image"] for c in configs}):
        if not docker_image_exists(img):
            sys.exit(f"ERROR: image {img} not found. Rebuild it first:\n  {IMAGE_REBUILD_CMDS.get(img, '(unknown image)')}")
    if not ENV_FILE.exists():
        sys.exit(f"ERROR: {ENV_FILE} not found")
    if not any(l.startswith(ENV_KEY + "=") for l in ENV_FILE.read_text().splitlines()):
        sys.exit(f"ERROR: {ENV_KEY} not set in {ENV_FILE}")
    if not COMPOSE_FILE.exists():
        sys.exit(f"ERROR: {COMPOSE_FILE} not found")
    log("preflight ok (docker, images, .env, compose file)")


def selftest() -> int:
    """Exercise the scoring machinery offline (no server, no docker)."""
    failures = []

    def t(name, cond):
        print(f"  {'PASS' if cond else 'FAIL'}  {name}")
        if not cond:
            failures.append(name)

    print("selftest: JSON extraction")
    txt = 'prose before {"a": [1, 2], "b": "x{y}"} and prose after [3, 4] tail'
    vals = extract_json_values(txt)
    t("two top-level values", len(vals) == 2)
    t("object first", vals and vals[0] == {"a": [1, 2], "b": "x{y}"})
    t("array last", vals and vals[-1] == [3, 4])
    txt2 = 'broken {not json} then good {"ok": true}'
    vals2 = extract_json_values(txt2)
    t("skips unparseable, finds valid", vals2 == [{"ok": True}])

    print("selftest: check types")
    ctx = {}
    ok, _ = CHECKS["json"]({"which": "first", "expect": "object"}, '{"steps": []}', ctx)
    t("json check stores ctx", ok and ctx["json"] == {"steps": []})
    ok, _ = CHECKS["json_keys"]({"keys": ["steps"]}, "", ctx)
    t("json_keys present", ok)
    ctx2 = {}
    CHECKS["json"]({"which": "first", "expect": "array"}, '[{"ts": "a"}, {"ts": "b"}]', ctx2)
    ok, _ = CHECKS["json_array_len"]({"len": 2}, "", ctx2)
    t("json_array_len", ok)
    ok, _ = CHECKS["json_field_set"]({"field": "ts", "expected": ["b", "a"]}, "", ctx2)
    t("json_field_set (order-insensitive)", ok)
    ctx3 = {}
    CHECKS["json"]({"which": "last", "expect": "object"},
                   'noise {"x": 1} final {"src": ["b.py", "a.py"], ".": ["n.txt"]}', ctx3)
    ok, _ = CHECKS["json_exact"](
        {"expected": {".": ["n.txt"], "src": ["a.py", "b.py"]}}, "", ctx3)
    t("json_exact (sorted lists, last span)", ok)
    ctx4 = {}
    CHECKS["json"]({"which": "first", "expect": "object"},
                   '{"steps": [{"tool": "grep", "args": {"p": "x"}, "purpose": "find"}]}', ctx4)
    ok, _ = CHECKS["json_tool_steps"]({"allowed": ["grep"], "max": 6}, "", ctx4)
    t("json_tool_steps valid", ok)
    ok, _ = CHECKS["json_tool_steps"]({"allowed": ["read_file"], "max": 6}, "", ctx4)
    t("json_tool_steps rejects bad tool", not ok)
    ctx5 = {}
    CHECKS["json"]({"which": "first", "expect": "object"}, '{"confidence": "high"}', ctx5)
    ok, _ = CHECKS["json_enum"]({"field": "confidence", "values": ["high", "medium", "low"]}, "", ctx5)
    t("json_enum", ok)
    ok, _ = CHECKS["contains_all"]({"items": ["tar", "-mtime +14"]}, "use tar with -mtime +14", {})
    t("contains_all", ok)
    ok, _ = CHECKS["fenced_block"]({"lang": "bash"}, "```bash\necho hi\n```", {})
    t("fenced_block bash", ok)
    ok, _ = CHECKS["fenced_block"]({"lang": "bash"}, "```python\nprint(1)\n```", {})
    t("fenced_block rejects other lang", not ok)

    print("selftest: corruption scan")
    t("clean text", corruption_scan("The quick brown fox jumps over the lazy dog. " * 5) == [])
    t("//// marker", any("////" in i for i in corruption_scan("fine text //// more")))
    t("token loop", any("loop" in i for i in corruption_scan("intro " + "abcd " * 12 + " outro")))
    t("no false loop on prose",
      corruption_scan("The meeting was productive. We agreed on the plan and the next steps for the team. " * 3) == [])

    print("selftest: throughput prompt builder")
    p0, p1 = build_throughput_prompt(0), build_throughput_prompt(1)
    t("variants differ", p0 != p1)
    t("no unfilled braces", "{" not in p0)
    t("length ~4k tokens (12k-24k chars)", 12000 <= len(p0) <= 24000)
    t("5 variants", len({build_throughput_prompt(i) for i in range(5)}) == 5)

    if failures:
        print(f"\nselftest: {len(failures)} FAILURE(S): {failures}")
        return 1
    print("\nselftest: all passed")
    return 0


# ── Main ──────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--configs", default="vanilla,rdna-adaptive",
                   help="comma-separated subset of: vanilla,rdna-adaptive")
    p.add_argument("--no-switch", action="store_true",
                   help="benchmark only the currently running image/model (no .env edits, no recreations)")
    p.add_argument("--reps", type=int, default=5, help="throughput reps (default 5)")
    p.add_argument("--gen-tokens", type=int, default=16384,
                   help="max_tokens cap for throughput and eval (default 16384)")
    p.add_argument("--request-timeout", type=float, default=1200,
                   help="per-request timeout seconds (default 1200)")
    p.add_argument("--skip-eval", action="store_true")
    p.add_argument("--skip-throughput", action="store_true")
    p.add_argument("--omp-passive", metavar="CONFIG",
                   help="after the main run, re-run the throughput reps of one "
                        "config (e.g. rdna) with OMP_WAIT_POLICY=PASSIVE "
                        "KMP_BLOCKTIME=0 in the container env. Self-diagnostic "
                        "for host-mapped input embeddings: a jump in MTP t/s "
                        "means the confound was present. Results land in "
                        "config-<name>-omp.json.")
    p.add_argument("--out", default=None,
                   help="output dir (default scripts/bench-results/<timestamp>)")
    p.add_argument("--dry-run", action="store_true", help="print the plan; no side effects")
    p.add_argument("--selftest", action="store_true", help="test the scoring machinery offline")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if args.selftest:
        return selftest()

    eval_specs = json.loads(EVAL_PROMPTS_FILE.read_text())
    wanted = [c.strip() for c in args.configs.split(",") if c.strip()]
    by_name = {c["name"]: c for c in CONFIGS}
    unknown = [w for w in wanted if w not in by_name]
    if unknown:
        sys.exit(f"ERROR: unknown config(s) {unknown}; valid: {list(by_name)}")
    configs = [by_name[w] for w in wanted]

    outdir = Path(args.out) if args.out else \
        Path(__file__).resolve().parent / "bench-results" / datetime.now().strftime("%Y%m%d-%H%M%S")
    outdir.mkdir(parents=True, exist_ok=True)

    n_switches = 0
    prev_img = None
    for c in configs:
        if c["image"] != prev_img:
            n_switches += 1
            prev_img = c["image"]

    print("=" * 72)
    print("eGPU A/B benchmark plan")
    print("=" * 72)
    print(f"  output dir   : {outdir}")
    if configs:
        print(f"  preset swap  : {ACTIVE_INI.name} symlink -> "
              f"{ini_for_image(configs[0]['image']).name} for config 1, per-image thereafter")
    else:
        print("  preset swap  : (none — OMP-only run, no main configs)")
    print(f"  reps         : {args.reps}  (gen cap {args.gen_tokens} tokens)")
    print(f"  eval prompts : {len(eval_specs['prompts'])}  ({'skipped' if args.skip_eval else 'on'})")
    print(f"  throughput   : {'skipped' if args.skip_throughput else 'on'}")
    omp_note = f" + OMP passive pass on {args.omp_passive} (2 extra recreations)" if args.omp_passive else ""
    print(f"  recreations  : {n_switches if not args.no_switch else 0}{omp_note}  ({'no-switch mode' if args.no_switch else ''})")
    for i, c in enumerate(configs, 1):
        print(f"  {i}. {c['name']:<23} {c['image']:<24} {c['model']}")
    print()
    if args.dry_run:
        print("dry run — nothing was changed.")
        return 0

    if not args.no_switch:
        log("WARNING: this run will recreate the llamacpp-egpu container "
            f"{n_switches} time(s). Any pi session inside it will be dropped.")
    preflight(configs)
    if args.no_switch:
        cur = docker_current_image()
        c = configs[0]
        if cur != c["image"]:
            sys.exit(f"ERROR: --no-switch but container is on {cur}, not {c['image']}")
        if active_ini_target() != ini_for_image(c["image"]).name:
            log(f"NOTE: active preset is {active_ini_target()} but {c['image']} expects "
                f"{ini_for_image(c['image']).name} — the running container was created with "
                f"whatever preset was active at its creation; benchmarking the current "
                f"registered model set as-is")
        if c["model"] not in list_models():
            sys.exit(f"ERROR: model {c['model']} not registered on the running server")

    original_env = ENV_FILE.read_text()
    original_compose = COMPOSE_FILE.read_text()
    original_ini = active_ini_target()
    results = {}
    try:
        for c in configs:
            log(f"=== config: {c['name']} ({c['image']} / {c['model']}) ===")
            if not args.no_switch:
                switch_to(c["image"])
            models = list_models()
            if c["model"] not in models:
                log(f"ERROR: model {c['model']} not registered; skipping config "
                    f"(registered: {sorted(models)})")
                continue
            out_path = outdir / f"config-{c['name']}.json"
            data = {"config": c["name"], "image": c["image"], "model": c["model"],
                    "preset": active_ini_target(),
                    "gen_tokens": args.gen_tokens, "started": now_iso()}
            save_json(out_path, data)
            run_warmup(c["model"])
            if not args.skip_throughput:
                data["throughput"] = run_throughput(c["model"], args, out_path)
            if not args.skip_eval:
                data["eval"] = run_eval(c["model"], eval_specs, args, out_path)
            data["ended"] = now_iso()
            save_json(out_path, data)
            results[c["name"]] = data
            log(f"=== config {c['name']} done ===")

        # ── OMP self-diagnostic pass (optional, one config) ─────────────────
        if args.omp_passive:
            oc = by_name.get(args.omp_passive)
            if oc is None:
                log(f"ERROR: --omp-passive config {args.omp_passive} unknown; skipping")
            elif oc["image"] != "llama-cpp-rocm:rdna":
                log(f"ERROR: --omp-passive only makes sense for an rdna (MTP) config, "
                    f"got {oc['image']}; skipping")
            else:
                log(f"=== OMP passive pass: {oc['name']} "
                    f"(OMP_WAIT_POLICY=PASSIVE KMP_BLOCKTIME=0) ===")
                if not args.no_switch:
                    switch_to(oc["image"])
                if oc["model"] not in list_models():
                    log(f"ERROR: model {oc['model']} not registered; skipping OMP pass")
                else:
                    compose_omp_env(True)
                    compose_up()
                    if not wait_health(300):
                        raise RuntimeError("server not healthy after OMP env recreation")
                    out_path = outdir / f"config-{oc['name']}-omp.json"
                    data = {"config": oc["name"] + "-omp", "image": oc["image"],
                            "model": oc["model"], "preset": active_ini_target(),
                            "omp": {"OMP_WAIT_POLICY": "PASSIVE", "KMP_BLOCKTIME": "0"},
                            "gen_tokens": args.gen_tokens, "started": now_iso()}
                    save_json(out_path, data)
                    run_warmup(oc["model"])
                    data["throughput"] = run_throughput(oc["model"], args, out_path)
                    data["ended"] = now_iso()
                    save_json(out_path, data)
                    results[oc["name"] + "-omp"] = data
                    compose_omp_env(False)
                    compose_up()
                    if not wait_health(300):
                        log("WARNING: server not healthy after OMP env removal")
                    log(f"=== OMP passive pass done: {oc['name']} ===")
    except KeyboardInterrupt:
        log("interrupted — saving what we have and restoring .env")
    except Exception as e:
        log(f"ERROR: {e} — restoring .env")
    finally:
        if ENV_FILE.read_text() != original_env:
            ENV_FILE.write_text(original_env)
            log(f".env restored to original ({ENV_KEY} line reverted)")
        if COMPOSE_FILE.read_text() != original_compose:
            COMPOSE_FILE.write_text(original_compose)
            log("docker-compose.yml restored to original (OMP vars removed)")
        # Restore the preset symlink to match the restored .env image, so the
        # on-disk state is consistent for the next manual `docker compose up -d`.
        try:
            env_img = next((l.split("=", 1)[1].strip() for l in original_env.splitlines()
                            if l.startswith(ENV_KEY + "=")), None)
            if env_img:
                set_active_ini(env_img)
        except SystemExit:
            pass
        if results and configs:
            write_summary(outdir, results)
            append_history(outdir, results)
            log(f"results: {outdir}")
        elif results:
            # OMP-only run (--configs ""): append the history row but leave
            # any existing summary.md untouched.
            append_history(outdir, results)
            log(f"OMP-only results: {outdir} (summary.md left untouched)")
        running = docker_current_image()
        if running:
            log(f"NOTE: container is now on {running}. If that differs from your "
                f"intended production image, set {ENV_KEY} in .env and run: "
                f"docker compose up -d {SERVICE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
