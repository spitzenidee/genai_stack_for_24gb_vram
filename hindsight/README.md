[Back to main README](../README.md)

# Hindsight memory integration

Persistent, per-repo long-term memory for the AI agents on this stack, backed by
[Vectorize Hindsight](https://hindsight.vectorize.io/) (v0.4.x+). It gives the agent
`retain` / `recall` / `reflect` over a local memory bank — so hard facts about the
stack (single-slot GPU rule, architecture decisions, conventions) are remembered
across sessions instead of being re-stated by hand every time.

Runs **fully local, no API key**: the LLM is our existing iGPU llama.cpp server
(OpenAI-compatible), and the embedder + reranker run on CPU inside the image.

> **Safety first:** Hindsight is a *pure HTTP client*. It never kills or restarts the
> llama servers. The iGPU is single-slot per model, so the one rule that matters is:
> **never restart the llama instance behind an active agent session** (you would kill
> your own session). See [Troubleshooting](#troubleshooting).

---

## What is running

| Thing | Where | Notes |
|---|---|---|
| `hindsight` service | `docker-compose.yml` (no profile — **always-on**) | API `:8888`, control-plane UI `:9999` |
| Data (Postgres/pg0) | `${APP_ROOT}/hindsight/data` → `/home/hindsight/.pg0` | bind mount, owned by UID 1000 |
| LLM | iGPU `llamacpp-igpu:8093` (OpenAI-compatible) | pinned via `${LLAMA_IGPU_MODEL}` |
| Embedder / reranker | local CPU (BGE-small / MiniLM) inside the image | no extra LLM |
| pi integration | `~/.pi/agent/settings.json` (extension) + `~/.pi/agent/skills/hindsight-coding-agent` | native tools, no MCP |
| pi config | `~/.hindsight/coding-agent.json` | opt-in, concise, cost-tuned |

Always-on (no profile) on purpose: memory must persist across GPU work-modes, and the
iGPU it depends on is itself always-on. The eGPU is behind the `llama` profile (down in
gromacs/blender/comfyui modes), so it **cannot** be the default LLM.

---

## The compose service

```yaml
hindsight:
  image: ghcr.io/vectorize-io/hindsight:latest
  container_name: hindsight
  depends_on:
    - llamacpp-igpu
  ports:
    - "8888:8888"    # API
    - "9999:9999"    # control-plane UI
  volumes:
    - ${APP_ROOT}/hindsight/data:/home/hindsight/.pg0
    - /etc/localtime:/etc/localtime:ro
  environment:
    # LLM -> iGPU slot exclusively (OpenAI-compatible; key unused by llama.cpp)
    - HINDSIGHT_API_LLM_PROVIDER=openai
    - HINDSIGHT_API_LLM_BASE_URL=http://llamacpp-igpu:8093/v1
    - HINDSIGHT_API_LLM_MODEL=${LLAMA_IGPU_MODEL}
    - HINDSIGHT_API_LLM_API_KEY=not-needed
    - HINDSIGHT_API_LLM_REASONING_EFFORT=high    # user decision: memory quality before latency
    # iGPU is single-slot per model -> cap concurrency
    - HINDSIGHT_API_LLM_MAX_CONCURRENT=1
    - HINDSIGHT_API_RETAIN_LLM_MAX_CONCURRENT=1
    - HINDSIGHT_API_CONSOLIDATION_LLM_MAX_CONCURRENT=1
    - HINDSIGHT_API_WORKER_ID=hindsight             # stable worker identity
    # local CPU embedder + reranker (no extra LLM)
    - HINDSIGHT_API_EMBEDDINGS_PROVIDER=local
    - HINDSIGHT_API_RERANKER_PROVIDER=local
  restart: unless-stopped
```

### Env vars, explained

| Var | Value | Why |
|---|---|---|
| `HINDSIGHT_API_LLM_PROVIDER` | `openai` | OpenAI-compatible client (llama.cpp speaks it) |
| `HINDSIGHT_API_LLM_BASE_URL` | `http://llamacpp-igpu:8093/v1` | pin to the always-on iGPU |
| `HINDSIGHT_API_LLM_MODEL` | `${LLAMA_IGPU_MODEL}` | the iGPU model **alias** (single source of truth in `.env`) |
| `HINDSIGHT_API_LLM_API_KEY` | `not-needed` | llama.cpp ignores it; the field is required |
| `HINDSIGHT_API_LLM_REASONING_EFFORT` | `high` | **user decision: memory quality before latency.** Sent as-is to the model; valid values e.g. `none`/`low`/`medium`/`high`/`xhigh`. `none` removes the thinking block on self-hosted models. |
| `HINDSIGHT_API_LLM_MAX_CONCURRENT` | `1` | iGPU is single-slot per model — no bursty parallel LLM calls |
| `HINDSIGHT_API_RETAIN_LLM_MAX_CONCURRENT` | `1` | cap retain (fact-extraction) concurrency |
| `HINDSIGHT_API_CONSOLIDATION_LLM_MAX_CONCURRENT` | `1` | cap background consolidation concurrency |
| `HINDSIGHT_API_WORKER_ID` | `hindsight` | stable worker identity across restarts |
| `HINDSIGHT_API_EMBEDDINGS_PROVIDER` | `local` | CPU BGE-small embedder (~130 MB), no LLM |
| `HINDSIGHT_API_RERANKER_PROVIDER` | `local` | CPU MiniLM cross-encoder (~85 MB), no LLM |

Background LLM work (all on the iGPU): `retain` on session end, observation
**consolidation** (background worker), **knowledge-page synthesis** (cron),
**mental-model refresh**, git ingest, cold-repo survey. The concurrency caps +
`concise` extraction + `optInOnly` keep the iGPU token load bounded.

---

## Model switching

The iGPU model is configured **server-side**, in exactly one place — the `.env` var
`LLAMA_IGPU_MODEL` (the model **alias**, i.e. the `id` reported by `/v1/models`). The pi
`coding-agent.json` only carries the server URL, no model field.

To switch the iGPU model Hindsight uses:

1. Update `LLAMA_IGPU_MODEL` in `.env` (and make the model the active one in
   `llamacpp/models-igpu.ini`).
2. `docker compose up -d hindsight` (recreates the container with the new env).

**No compose edit needed.** Per-operation overrides
(`HINDSIGHT_API_{RETAIN,REFLECT,CONSOLIDATION,MENTAL_MODEL_REFRESH}_LLM_MODEL`) exist if
you later want a different model for one operation.

> **Single-slot model swap:** if the iGPU currently has a *different* model loaded than
> `LLAMA_IGPU_MODEL`, Hindsight's first request triggers a one-time model swap (the
> in-flight request completes first; the next waits for the load). That is a latency hit,
> **not** a session kill. Pinning Hindsight to one model (as we do) avoids repeated swaps.

---

## iGPU `parallel = 2`

`llamacpp/models-igpu.ini` (`[*]` defaults) sets `parallel = 2` (was `1`). Each loaded
model gets **two KV slots**, so `gromacs-sim` (agent brain on the iGPU) and Hindsight
(background memory work) run **concurrently** on the same model — no swap, no unload, no
cancel. `sleep-idle-seconds` only sleeps the model when *all* slots are idle, so an idle
Hindsight slot never forces a sleep while gromacs-sim is active.

Each parallel slot carries its own KV cache (q8_0). This was raised with system-RAM
headroom verified; go to `3` only if headroom is confirmed in the llama.cpp load logs.

---

## pi integration (host pi)

Installed with the official vendor installer:

```bash
npx @vectorize-io/hindsight-coding-agents install pi --server self-hosted \
  --api-url http://localhost:8888
```

That wrote:
- an **extension** entry in `~/.pi/agent/settings.json` (`~/.hindsight/coding-agents/dist/pi.js`),
- a companion **skill** at `~/.pi/agent/skills/hindsight-coding-agent` (the full reference),
- `~/.hindsight/coding-agent.json` (the config, below).

Native tools, no MCP. On a **sandboxed** pi (not yet on this host) the same extension
works — point `apiUrl` at the host (`http://host.docker.internal:8888` or the VM IP); the
sandbox only needs network reach to `:8888`.

### `~/.hindsight/coding-agent.json` (this host)

```json
{
  "serverMode": "self-hosted",
  "apiUrl": "http://localhost:8888",
  "optInOnly": true,
  "optInPaths": ["/home/<user>/docker/genai_stack"],
  "retainExtractionMode": "concise",
  "defaultBankConfig": {
    "mental_model_min_refresh_interval_seconds": 86400
  },
  "pages": {
    "Core concepts": false,
    "Initiatives and enhancements": false
  },
  "pageTriggerCron": "0 3 * * *"
}
```

| Field | Value | Why |
|---|---|---|
| `optInOnly` | `true` | memory runs **only** in opted-in projects; everything else is inert (no bank, nothing retained) |
| `optInPaths` | the stack root | prefix match — every repo under the stack is approved, each keeps its own `coding-agent::<repo>` bank; nothing outside the stack is remembered |
| `retainExtractionMode` | `concise` | fewer tokens per retain than `verbose`/`verbatim` (cost control) |
| `defaultBankConfig.mental_model_min_refresh_interval_seconds` | `86400` | mental-model refresh at most once/day (cost control) |
| `pages` | 2 of 5 disabled | keep the 3 most useful for this stack (`Component map`, `Conventions and patterns`, `Key decisions and rationale`); drop `Core concepts` + `Initiatives and enhancements` (each page = one LLM synthesis per refresh) |
| `pageTriggerCron` | `0 3 * * *` | knowledge pages refresh daily at 03:00 UTC (default is hourly) |

Config is read at process start — **restart the pi agent** after editing it to apply.

---

## Bank seeding

Each repo resolves to a bank `coding-agent::<gitProject>` (here `coding-agent::genai_stack`).
The bank was seeded with the user's hard facts so they are recalled every session:

- **Bank directive** (hard rule, always applied): *"Never kill or restart the llama
  instance behind an active session"* — the single-slot rule, with the targeted-restart
  guidance.
- **Mental model** (living summary, refreshed from the bank): *"GPU single-slot
  architecture & session-safety rule."*
- **Retained facts**: the single-slot architecture, "the agent runs on one of these
  slots," the never-kill-your-own-fabric rule, GPU work-modes (iGPU always-on vs eGPU
  profile-gated), and the Hindsight setup itself.

To add more hard facts later, either tell the agent *"remember this in hindsight"*
(captured at session end) or use the control-plane UI / API (below).

---

## Operations

### Health

```bash
curl -s localhost:8888/health
# {"status":"healthy","database":"connected",...}
```

### Control-plane UI

`http://localhost:9999` — browse banks, review/prune memories, edit directives and
mental models, watch consolidations. (No API key configured = public access on this host.)

### Retain / recall / reflect (API)

Base: `http://localhost:8888/v1/default/banks/<bank_id>`.

```bash
B=coding-agent::genai_stack

# Retain a fact (sync)
curl -s -X POST localhost:8888/v1/default/banks/$B/memories \
  -H 'Content-Type: application/json' \
  -d '{"items":[{"content":"...the fact...","tags":["my:tag"]}],"async":false}'

# Recall (fast, hybrid search)
curl -s -X POST localhost:8888/v1/default/banks/$B/memories/recall \
  -H 'Content-Type: application/json' \
  -d '{"query":"...what do I need to know?","budget":"low","max_tokens":2000}'

# Reflect (deep, agentic — SLOW on the iGPU, see Troubleshooting)
curl -s -X POST localhost:8888/v1/default/banks/$B/reflect \
  -H 'Content-Type: application/json' \
  -d '{"query":"...why did we decide X?","budget":"low","max_tokens":1200}'
```

The pi agent uses these through the native `hindsight_*` tools
(`hindsight_search_knowledge_pages`, `hindsight_reflect`, `hindsight_ingest_document`,
`hindsight_capture_initiative`, …) — see the installed skill for the full tool guide.

### Day-to-day commands

```bash
docker compose up -d hindsight          # start (targeted — safe)
docker compose logs -f hindsight        # logs
docker compose restart hindsight        # restart just hindsight (safe; never touches llama)
docker compose stop hindsight           # stop
```

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `curl :8888/health` fails | container down → `docker compose up -d hindsight`; check `docker logs hindsight`. It depends on `llamacpp-igpu` being up. |
| Retain/reflect slow or times out | Expected on the iGPU. `reflect` is agentic (multi-iteration) and can take 1–5 min; the server wall-timeout is 300 s (`HINDSIGHT_API_REFLECT_WALL_TIMEOUT`). The pi auto-inject uses a low budget with a 20 s timeout and **falls back** to page search → recall, so a session is never blocked. Lower `budget` or simplify the query for faster reflects. |
| `reasoning_effort` rejected | The value is sent as-is. If a future model rejects `high`, fall back to `medium`/`low`/`none` in the compose env and note it here. `none` is valid on self-hosted models (removes the thinking block). |
| Data not persisting | The bind dir `${APP_ROOT}/hindsight/data` must be writable by the container user (UID 1000). The stack runs `UID=1000`/`GID=1000`, so no `chown` is expected; verify ownership if it fails. |
| Model swap latency on first call | The iGPU had a different model loaded than `LLAMA_IGPU_MODEL`. One-time swap (latency, not a kill). Keep Hindsight pinned to one model. |
| **NEVER** restart `llamacpp-egpu`/`llamacpp-igpu` to "fix" Hindsight | Hindsight is a pure HTTP client — restarting the llama servers to fix it is wrong and, if a session is running on that slot, **kills your own session**. Fix Hindsight by restarting *hindsight* only. |
| pi tools not appearing | restart the pi agent (config is read at process start); confirm the extension entry in `~/.pi/agent/settings.json` and the skill dir exist. |

---

## Undo / remove

```bash
docker compose stop hindsight && docker compose rm -f hindsight
docker rmi ghcr.io/vectorize-io/hindsight:latest
# data stays at ${APP_ROOT}/hindsight/data until you delete it
# remove the extension entry from ~/.pi/agent/settings.json + ~/.pi/agent/skills/hindsight-coding-agent
# remove ~/.hindsight/coding-agent.json
```

## Related

- The always-on iGPU it depends on (LLM backend, single-slot rule):
  [llamacpp/README.md](../llamacpp/README.md)
- The agent skills that consume the memory (board workers, GROMACS):
  [.pi/README.md](../.pi/README.md)
- Services & ports, GPU work modes: main README ([../README.md](../README.md))

[Back to main README](../README.md)
