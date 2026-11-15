# AGENTS.md — genai_stack

## Hard rule: never kill or restart the llama instance behind an active session

The llama.cpp servers on this stack (`llamacpp-egpu`, `llamacpp-igpu`) are **SINGLE-SLOT per model**
(`--models-max 1`); an AI agent session (including yours) occupies one slot as its LLM backend.

- **NEVER** kill, restart, or `docker compose down` a llama instance behind an active agent session — that kills your **OWN** session.
- This includes **indirect** restarts: bench/eval harnesses that recreate the llama container per config (e.g. `scripts/bench_egpu_ab.py`), `docker compose restart`, and broad `docker compose up -d` on the llama services.
- A worker whose task needs eGPU compute must **park the card in `AskUser`** with the exact run command for a human to run from a normal shell — never run the compute itself, and never treat "no pi session in the container" as a safety check (pi runs on the host; ask "is my own LLM backend the server this task will disturb?").
- **Hindsight and any other HTTP client must NEVER kill/restart the llama servers.**
- **The iGPU is always-on; the eGPU is behind the `llama` profile** (down in gromacs/blender/comfyui work-modes).
- Prefer targeted `docker compose up -d <service>` over broad restarts; always check what a restart affects before running it.

**Re-verify before any docker/llama operation:** re-query the bank directives and confirm this mirror is current:

`curl -s 'http://localhost:8888/v1/default/banks/coding-agent::genai_stack/directives'`

If the query fails (Hindsight server down), this mirror remains binding.

**Source:** Hindsight bank directive `Never kill or restart the llama instance behind an active session` (priority 1, `safety:hard-rule`, bank `coding-agent::genai_stack`). Mirrored because the coding-agent plugin (v0.8.5, latest as of 04.11.2026) does not inject bank directives. This file is the authoritative, harness-delivered copy — on disagreement, this file wins for sessions. Sync is the active re-verify step above. Remove the mirror once the plugin delivers directives natively.
