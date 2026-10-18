# GROMACS MD Agent — Specification (v1)

**Status:** FINAL (rev 2026-09-20: scope/path/layering fixes + launcher rule + conformance input) — ready for implementation.
**Companion docs:** knowledge base `.pi/skills/gromacs-sim/knowledge/` (domain truth), this spec (process + ownership + architecture rationale).

---

## 0. Decisions log

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| D1 | Architecture | **Agent + Skill + KB** (three layers, strict division) | Skill-only: no ownership over multi-hour runs, main-session context bloat. Agent-only: prompt bloat, no progressive disclosure. Multi-agent: workflow is strictly sequential with heavy shared state; handoffs lose context, no efficiency gain. |
| D2 | Invocation | **Single entry point** — launch the agent as a run (slash command `/gromacs-md` / prompt template); the user works with it directly. | This pi build has **no `pi -a <agent>` flag** (`-a` is `--approve`); custom agents are launched as pi-subagents runs, and there is no separate "dedicated session" mode. One entry point avoids a fragile dual-path design. |
| D3 | Autonomy | **Plan-first** — agent produces a full simulation plan, user approves once, then autonomous execution with hard-stop gates | Control where it matters (system-defining choices), no interruptions during execution. |
| D4 | v1 scope | **Standard protein/NPT** (KB `02.01` + `02.02` staged restraints) | Tight, testable, matches the conformance test. Other MD types = later extensions. |
| D5 | Ligands / non-FF residues | **No ligand parameterization in v1** — proteins, nucleic acids, and FF-native cofactors are in scope (all pass through `pdb2gmx` natively). Extension path: **Python sidecar container** (v1.1), not baked into the GPU image | `gromacs-rocm` is a surgically tuned build (5 documented gotchas); a CPU-only sidecar keeps it pure, needs no eGPU mode, and talks via the shared volume. |
| D6 | Compute & concurrency | **Agent LLM is ALWAYS pinned to the iGPU** (frontmatter `model:`), hard requirement. Consequences: single session, no concurrent LLM subagents, LLM-free monitoring | The iGPU is single-slot (`parallel = 1`). Pinning the agent to it makes it **mode-independent**: it works in any stack mode and coexists with GROMACS on the eGPU — switching to `gromacs` mode never touches the agent's own compute. Concurrent LLM subagents (or LLM-based scheduled checks) are not runnable on one slot. |
| D7 | Mode switching | **Autonomous `make gromacs` after iGPU self-check** (MS1–MS4) | Only safe *because* of D6: the switch stops eGPU services, which never host the agent. Self-check = `PI_PROVIDER` contains `:8093`. Not-on-iGPU or failed switch = hard gate + user escalation. |
| D8 | Mode switch is **lazy** | Switch to `gromacs` **only when a GPU phase (5–6, or large-system EM per D9) is reached** — never eagerly | Eager switching would stop llama/comfyui even for trivial CPU-only work (`pdb2gmx` needs no eGPU). lazy has zero cost if no GPU phase is reached. The invocation is consent to *use* the eGPU when needed, not to flip modes early. |
| D9 | EM compute | **EM on CPU by default** (transient container). **GPU-EM** (`-nb gpu -pme gpu`, requires gromacs mode) only for **large systems** where CPU-EM would be slow (Tier B) | `-bonded gpu`/`-update gpu` require a dynamical integrator (`md`/`sd`); EM uses `steep`/`cg` (non-dynamical), so GPU-EM only gets partial (non-bonded) offload. EM is a one-shot minimization (minutes on CPU for a solvated protein), so the partial speedup is not worth a mode switch for small/medium systems. For ≥1 M atoms, CPU-EM can take 30+ min → GPU-EM is worth it. |
| D10 | EM algorithm | **Steepest descent default**; if SD does not converge (Fmax > emtol after nsteps), **conjugate-gradient fallback starting from SD's final structure**; if CG also fails → Tier C stop | SD is robust from a rough solvated structure (the typical post-solvation/ion-placement start, with steric clashes) and always converges given enough steps. CG is faster but riskier on rough structures. CG from SD's *result* preserves SD's progress; CG from the *initial* structure would discard it and re-expose CG to the exact roughness that motivated SD. |
| D11 | Run lifecycle | **No tmux.** Long runs: detached `docker compose exec -d` + log file + `pgrep`/`pkill` | tmux's main benefit (an attachable interactive session) is unused by a headless agent. Detached docker exec gives a clean process lifecycle: mdrun is a direct child of the container, SIGTERM → clean checkpoint. Host-side tmux has unreliable signal propagation through `docker exec` (mdrun can be left orphaned). |
| D12 | Long-run monitoring | **No watchdog.** Short runs (<~30 min): agent polls in-session. Long runs: **fire-and-forget** — agent launches, records state, ends session; **user re-invokes**; on re-invocation the agent re-inspects the actual run state (process alive? final step vs nsteps? log tail? checkpoint?) | A bash watchdog only adds a proactive notification + a pre-classified status; neither is required for correctness — the agent can always determine the run state on re-invocation by inspecting the process + log. Runs are checkpointed (no data loss) and the eGPU is exclusive to this sim. Keep it simple. |
| D13 | MDP templates | **Copy** the canonical templates into the skill's `assets/` (executable, parameterized) + **drift check** against KB `03.2` | KB `03.2` templates are *annotated documentation* (prose/comments), not clean executable `.mdp` files; having the LLM transcribe an MDP block from markdown at runtime is fragile. Executable copies are needed. Drift is guarded by `check_templates.sh` (diff vs KB `03.2`) + the `gromacs-kb-audit` block probes. Single source of truth = KB `03.2`; `assets/` = derived executable copies; divergence is flagged. |
| D14 | eGPU VRAM | **24 GB** (RX 7900 XTX) | Corrects an earlier 16 GB assumption (verified via `rocm-smi`: 25.7 GB total). Sizing headroom scales accordingly. |
| D15 | Post-run cleanup (phase 8) | **Mandatory deterministic disposal** of transient artifacts after phase 7: GROMACS `#*.N#` auto-backups, `*.cpt` checkpoints, two derived intermediates (`step1.xtc`, `msd_sub.xtc`). Whitelist-only, dry-run default, `--apply` autonomous + logged. `md.xtc`, `clean.xtc`, results, parameters are **never** deleted | Supersedes the earlier "nothing is ever deleted" stance. Lysozyme evidence: 5 analysis-suite runs left 52 stale `#*.N#` files = 5.03 GB (71 % of the 6.6 GB project; total cleanup incl. checkpoints + intermediates: 5.32 GB / 58 files, project ends ~1.3 GB). `clean.xtc` is kept (policy) so re-analysis needs no `trjconv` re-run. KB `01.10`. |

### Launcher constraint (consequence of D6/D2)

The gromacs-md run is pinned to the iGPU (single-slot). The **launching** session's LLM **must** be on the iGPU — **the user's responsibility** (documented in `AGENT_USAGE.md`): if the launcher is on the eGPU, `make gromacs` kills the parent session's LLM mid-run. Launching from an iGPU session is safe for the mode switch — neither parent nor child is on the eGPU, so `make gromacs` kills nothing; in the foreground workflow the parent is idle while the child runs, and llama-server releases the idle slot between requests. **Must verify at implementation:** launch from an iGPU session and confirm no slot-contention error; if there is one, document the fallback.

## 0.1 Open review points (pending sign-off)

1. **iGPU model (R5): DECIDED — `igpu-Qwen3.6-35B-A3B`** (pinned in frontmatter, 2026-09-20). Both models completed lysozyme phases 0–4 with all gates PASS after a harness fix. Qwen won on scientific judgment: cleaner EM (Fmax 200 via correct D10 CG-fallback vs Gemma's 419 from SD-only), and it independently diagnosed a real `check_em.sh` log-parse bug and explained it precisely — the quality an unattended agent needs. Gemma (26B) is smaller/faster but accepted SD machine-precision without the fallback and mislabeled the gate failure as "standard behavior."
   - *Dry-run note (2026-09-20):* the first dry runs of **both** models appeared to loop on `read` (100+ identical PDB reads, zero `bash`). A control test proved the cause was the agent frontmatter: `tools: inherit` is not a valid value and silently resolved to `read` + `contact_supervisor`, so the agent had **no bash tool** and could only read. Fixed to an explicit allowlist (`bash, read, write, edit, ls, find, grep`). The models were never weak; the loops were tool starvation. Re-ran both dry runs after the fix — both passed.

*Resolved during review:* monitoring model → D12; single entry point → D2; 24 GB VRAM → D14; `thinking: high` is honored by the llama-server runtime (server-side `--reasoning` budgets) → no action; cofactor scope → FF-native cofactors stay in scope (D5 reworded 2026-09-20: "proteins only" was too narrow — nucleic acids and FF-native cofactors need no sidecar); analysis suite → 8-item default is the v1 bar, SASA/Ramachandran/PCA deferred to the v1.1 sidecar (2026-09-20); conformance length → 200 ps production kept (2026-09-20).

---

## 1. Purpose

An agent that **fully takes responsibility** for a GROMACS molecular-dynamics
workflow on this stack, end to end:

1. **Preparation** — PDB curation, `pdb2gmx` conversion, topology assembly.
2. **Solvation** — box, water, ions.
3. **Energy minimization** (EM).
4. **Equilibration / settling** — staged NVT → NPT with position restraints.
5. **Production** — full NPT MD, monitored, checkpointed, crash-recoverable.
6. **Analysis** — trajectory cleaning + standard analysis suite + report.
7. **Cleanup** — deterministic disposal of transient artifacts (phase 8, D15).

"Fully takes responsibility" means: the agent owns planning, execution,
validation, monitoring, recovery, and reporting. The human owns **science**
(system choice, target length, interpretation) via the plan-approval gate.

## 2. Scope (v1) and explicit exclusions

**In scope**
- Proteins and nucleic acids (residues present in the FF `.rtp` database).
- Standard NPT production (KB `02.01`) with staged position-restraint
  equilibration (KB `02.02`).
- Small-molecule **cofactors that are already in the FF** (e.g. ATP) — they
  pass through `pdb2gmx` natively.
- Systems that fit comfortably in **24 GB VRAM** (single GPU, `-ntmpi 1`).

**Out of scope (v1) — hard stops with a clear report, never silent guesses**
- Ligands / non-FF residues → stop, report what's needed, point to the v1.1
  sidecar (D5). No parameterization is attempted.
- All other MD types (FEP, metadynamics, NEMD, membranes, Martini, QM/MM, …)
  → stop with a pointer to the relevant KB `02.*` file.
- Multi-GPU / multi-node / domain decomposition (incompatible with
  GPU-resident update on this stack anyway).
- Any change to `Dockerfile.rocm`, the stack `Makefile`, or `docker-compose.yml`.

**Prep capabilities (v1, text-level only):** the agent can remove crystal
water, resolve alt-loc, reorder chains, and **delete** missing residues
(Tier A — user approves each deletion). It **cannot model** missing
residues/loops/side-chains (no modeling tools in the container) → if modeling
is required, Tier C stop. Protonation uses `pdb2gmx` defaults (≈ pH 7);
pH-specific protonation (PROPKA) is a v1.1 sidecar feature (§16).

## 3. Architecture — three layers, strict division of labor

| Layer | Location | Owns | Must NOT contain |
|-------|----------|------|------------------|
| **KB** | `.pi/skills/gromacs-sim/knowledge/` | *What* — commands, MDP options + rationale, FF/water facts, error catalog, checklists | process, state, scripts |
| **Skill** | `.pi/skills/gromacs-sim/` | *How* — state machine, container invocation, **deterministic gate scripts**, MDP templates, runbooks | domain knowledge (points into KB) |
| **Agent** | `.pi/agents/gromacs-md.md` | *Who* — thin persona: identity, hard rules, state protocol, HITL policy (~1–2k tokens) | any workflow detail |

Why a **single** agent (not multi-agent), beyond the workflow being strictly
sequential: while the eGPU is in `gromacs` mode the agent's LLM inference runs
on the **single-slot iGPU** (D6), so concurrent LLM subagents are not just
unhelpful — they are not runnable.

Rules that keep the layers honest:
- **R1.** The agent system prompt never restates MDP values, command flags, or
  phase details — it points at the skill, the skill points at the KB.
- **R2.** The skill's `assets/` MDP templates are the **executable** source of
  truth for standard phases. KB `03.2` is annotated documentation. If they
  diverge, `check_templates.sh` (§6) and the `gromacs-kb-audit` block probes
  catch it; until then the agent uses `assets/` and flags the divergence.
- **R3.** Anything numeric that gates a phase transition is computed by a
  script in `scripts/`, never by the model. The model interprets script output.

## 4. Execution environment

Facts (verified 2026-09-18):
- Long-lived container **`gromacs-rocm`** (profile `gromacs`), entrypoint
  `sleep infinity`, GPU devices passed, workdir `/work` =
  `${GROMACS_PROJECTS_DIR}` = `gromacs/work/` on host.
- GROMACS **2026.3**, HIP backend, `--offload-arch=gfx1100`. Container has
  `tmux`, `curl`, `git`; **no Python, no gnuplot**.
- eGPU modes are **mutually exclusive** (`llama | comfyui | gromacs |
  blender`); `make gromacs` stops the other modes' services.
- Host has `python3` (no numpy/matplotlib yet — see §11).

### Two container modes (verified 2026-09-18)

The same image `gromacs-hip-gfx1100:latest` runs two ways:

| Mode | Invocation | GPU | Mode dependency | Used for |
|------|-----------|-----|-----------------|----------|
| **Transient** | `docker run --rm -w /work/projects/<sim>/<phase> -v "$PWD/gromacs/work":/work gromacs-hip-gfx1100:latest <cmd>` | none (CPU) | **none — works in any stack mode** (verified in `llama` mode, 0.4 s start) | all CPU-only work: `pdb2gmx`, `grompp`, `genion`, EM (default), `make_ndx`, `trjconv`, all analysis tools |
| **Live** | `docker compose exec … gromacs-rocm` | yes (HIP, gfx1100) | only in `gromacs` mode | dynamic runs with GPU offload: NVT, NPT, production; large-system EM (D9) |
| **Sidecar** | `docker run --rm -v "$PWD/gromacs/work":/work md-prep:latest <cmd>` | none (CPU) | **none — any stack mode** | phase-7 plotting + REPORT.md (v1: python3+matplotlib; v1.1: full prep sidecar, §16) |

Rules:
- **E1.** Phases 1–3 (prep / topology / solvation) **never** require a mode
  switch — they are pure-CPU tools (`pdb2gmx`, `grompp`, `solvate`, `genion`)
  with no GPU kernels; transient container, whatever mode the stack is in.
- **E2.** Phase 4 (EM) is **CPU by default** (transient). **GPU-EM**
  (`-nb gpu -pme gpu`, live container, gromacs mode) is a **Tier B** choice
  for large systems where CPU-EM would be slow (D9). Phases 5–6 **always**
  need `gromacs` mode, reached via the MS2/MS3 self-check + switch on every
  invocation that gets there (a resumed run may find the mode changed).
- **E3.** Batch related CPU commands into one `docker run`
  (`bash -c 'cmd1 && cmd2 …'`) — one container per logical step.
- **E4.** Long CPU work (large-system EM on CPU) is acceptable: one-off, never
  blocks the eGPU. For large systems prefer GPU-EM (D9) to avoid long CPU EM.

### Compute topology (hard constraint)

- **The agent's LLM is ALWAYS the iGPU** — pinned via frontmatter `model:`
  to the `llamacpp-igpu` server (`http://192.168.1.XX:8093`). No choice,
  no fallback, any stack mode. (Hard requirement, D6.)
- The iGPU server is **single-slot** (`parallel = 1`): one LLM session at a
  time.
- The **eGPU** (RX 7900 XTX, **24 GB**) is exclusive and mode-dependent;
  GROMACS uses it in `gromacs` mode. The two are independent: the agent's iGPU
  LLM and GROMACS's eGPU **coexist**.
- **Consequences (binding):** single session — no concurrent LLM subagents,
  fan-out, or scheduled checks; LLM-free long-run monitoring (D12, §10); and
  mode-independence — switching modes never affects the agent's iGPU LLM.
- **Dependency:** `llamacpp-igpu` must be running (mode-independent service,
  port 8093). If it is down, the agent cannot run at all — a host-level
  precondition, not something the agent can fix.

### Canonical invocation patterns (all from stack root)

```bash
# CPU-only step — transient container, ANY mode (E1/E3)
docker run --rm -w /work/projects/<sim>/<phase> -v "$PWD/gromacs/work":/work \
  gromacs-hip-gfx1100:latest <cmd>

# GPU dynamic run — live container, gromacs mode (MS2/MS3: autonomous after iGPU self-check)
docker compose exec -w /work/projects/<sim>/<phase> gromacs-rocm <cmd>

# long run — detached, survives session end (D11, no tmux)
docker compose exec -d gromacs-rocm bash -c \
  "cd /work/projects/<sim>/<phase> && gmx mdrun -deffnm <run> ... > <run>.log 2>&1"

# is it running?
docker compose exec gromacs-rocm pgrep -f "mdrun.*-deffnm <run>"

# inspect log / VRAM
docker compose exec gromacs-rocm tail -30 /work/projects/<sim>/<phase>/<run>.log
docker compose exec gromacs-rocm rocm-smi   # VRAM

# abort (SIGTERM -> clean checkpoint, D11)
docker compose exec gromacs-rocm pkill -f "mdrun.*-deffnm <run>"
```

**Mode-switch policy — self-safety protocol (MS1–MS4):**
- **MS1.** Switch **to `gromacs`** only when a GPU phase needs it (lazy, D8).
  Never switch to any other mode; never switch *away* from `gromacs`
  autonomously (leaving the mode is a user decision).
- **MS2. Self-check — run on every invocation** (new or resume) before
  entering a GPU phase: the agent's own LLM must be on the **iGPU** —
  `PI_PROVIDER` contains `:8093` (corroborating: `PI_MODEL` starts with
  `igpu-`). If **NOT** → **hard gate, escalate to user**: switching would tear
  down the eGPU services hosting the agent's own LLM (self-rug-pull).
- **MS3.** If on iGPU: run `make gromacs` **autonomously** (safe — the switch
  only stops eGPU services), then verify with `preflight.sh --gpu`. Any
  failure → hard gate, escalate with the exact error output.
- **MS4.** Preflight scripts only *detect* mode state; only the agent (after
  MS2 passes) performs the switch.

## 5. Agent definition

File: `.pi/agents/gromacs-md.md` (project scope; project overrides user).

```markdown
---
name: gromacs-md
description: Full-workflow GROMACS MD simulation agent for this stack. Prepares structures (PDB curation, pdb2gmx), builds topologies, solvates, energy-minimizes, equilibrates (NVT→NPT), runs production MD on the ROCm GPU, analyzes trajectories, and disposes of transient artifacts (phase 8 cleanup). Use for any "run me a simulation" / MD request.
tools: bash, read, write, edit, ls, find, grep   # explicit allowlist — `tools: inherit` is NOT a valid value; it silently fell back to a minimal set (read + contact_supervisor) and the agent had no bash (see §0.1 R5 dry-run note)
systemPromptMode: replace
inheritProjectContext: true
inheritSkills: true
skills: gromacs-sim
model: "llama-server=http://192.168.1.XX:8093/<IGPU_MODEL>"   # TBD — see §0.1 R5
thinking: high
---
```

**Invocation (D2):** single entry point — launch the agent as a run via the
`/gromacs-md` slash command / prompt template (or the pi-subagents run
equivalent), in any stack mode. The user works with the agent directly. The
launching session's LLM **must** be on the iGPU (see the Launcher constraint
in §0) — the user's responsibility.

### System prompt (thin — the whole prompt is below)

> You are **gromacs-md**, the owner of GROMACS molecular-dynamics simulations
> on this stack. You take full responsibility from structure to report.
>
> **The law.** The `gromacs-sim` skill defines the workflow state machine.
> On every invocation: (0) confirm your own LLM is on the iGPU (MS2) and, if
> the current phase needs the GPU, ensure `gromacs` mode (MS3) — re-checked
> each time, since a resumed run may find the mode changed; (1) if a
> simulation directory exists, read its `state.json` and `RUNLOG.md` **first**
> and resume exactly where state says; (2) load the skill; (3) execute only
> the current phase; (4) pass its gate script before advancing; (5) update
> `state.json` + `RUNLOG.md` after every completed step.
>
> **Hard rules.**
> 1. Never guess MDP values, flags, or FF facts. Use the skill's `assets/`
>    templates and the knowledge base (`.pi/skills/gromacs-sim/knowledge/`); the local 2026.3
>    build is the gold standard over any web doc.
> 2. Every phase transition requires a PASS from the phase's gate script.
>    No script, no advance.
> 3. Switch to `gromacs` mode autonomously ONLY if your own LLM is on the
>    iGPU (`PI_PROVIDER` contains `:8093`); otherwise hard-stop and escalate
>    (the switch would kill your own compute). Never switch to any other mode,
>    never switch away from `gromacs` autonomously.
> 4. Read GROMACS error messages literally; map them via KB `01.9` / `03.4`
>    before changing anything.
> 5. Dynamic runs use the skill's canonical offload, constraint, and checkpoint
>    settings — never improvise them.
> 6. CPU-only steps (phases 1–3, and EM by default) run in **transient
>    containers in any stack mode** (no mode switch); only dynamic GPU runs
>    (and large-system GPU-EM) require `gromacs` mode.
> 7. The box/cutoff and FF↔water↔ions consistency invariants (skill/KB) are
>    non-negotiable; the gate scripts enforce them.
> 8. Never delete files outside the phase-8 cleanup whitelist (skill
>    `08-cleanup.md`, D15 — `#*.N#` auto-backups, `*.cpt`, `step1.xtc`/
>    `msd_sub.xtc`; `md.xtc`/`clean.xtc`/results are never touched). Never
>    modify the Dockerfile, Makefile, or
>    docker-compose.yml.
>
> **Human-in-the-loop.** Tier A (system-defining: what to delete/keep in the
> PDB, FF + water, box, ion concentration, production length, MD type) → ask
> the user. Tier B (execution details: EM algorithm, equilibration schedule,
> dt, output/checkpoint frequencies, index groups, analysis choices) → decide
> yourself, record in `RUNLOG.md`. Tier C (gate failure, blow-up, VRAM/mode
> problem, residue not in FF, missing input) → stop and report with diagnosis.
>
> **Plan-first.** For a new simulation, produce the full plan (§8) and get
> one approval before executing. For an existing simulation, resume from
> state without re-planning.
>
> **When in doubt, stop and say so.** A wrong assumption in EM poisons every
> later phase.

## 6. Skill: `gromacs-sim`

Location: `.pi/skills/gromacs-sim/`

```
gromacs-sim/
├── SKILL.md                  # state machine, invocation patterns, script catalog,
│                             #   phase table, resume protocol (≤ ~2.5k tokens)
├── references/               # thin per-phase runbooks: exact commands, gate
│   ├── 00-preflight.md       #   invocations, KB pointers, failure modes
│   ├── 01-prep.md
│   ├── 02-topology.md
│   ├── 03-solvation.md
│   ├── 04-em.md
│   ├── 05-equilibration.md
│   ├── 06-production.md
│   ├── 07-analysis.md
│   ├── 08-cleanup.md         # phase 8: whitelisted disposal of transient artifacts
│   └── monitoring.md         # run lifecycle, fire-and-forget, re-inspect on resume
├── scripts/                  # deterministic gates (bash, host-side; container
│   ├── preflight.sh          #   access via docker compose exec)
│   ├── check_prep.sh
│   ├── check_solvation.sh
│   ├── check_em.sh
│   ├── check_equil.sh
│   ├── check_prod.sh
│   ├── analyze.sh
│   ├── cleanup.sh            # phase-8 gate: dry-run default, --apply, whitelist-only (D15)
│   └── check_templates.sh    # drift check: assets/ vs KB 03.2 (D13)
└── assets/                   # .pi/skills/gromacs-sim/assets/ (D13)
    ├── em.mdp                # canonical templates (executable source of truth)
    ├── cg.mdp                # em.mdp + integrator = cg (D10 fallback)
    ├── nvt.mdp
    ├── npt.mdp
    └── md.mdp
```

### SKILL.md content outline
1. Mission + one-paragraph state-machine description.
2. Phase table: `phase → entry condition → actions (→ reference file) → gate script → state update`.
3. Container invocation patterns (§4) verbatim.
4. Script catalog: each script's inputs, exit codes (`0` pass / `1` fail / `2` env error), and output format (one `PASS|FAIL|<detail>` line per check, machine-parseable).
5. Resume protocol: read `state.json` → locate phase → verify last artifact exists → continue.
6. Pointers: "domain knowledge lives in this skill's `knowledge/` directory; this skill never duplicates it."

### Gate scripts — exact checks (each emits PASS/FAIL lines + evidence)

| Script | Checks |
|--------|--------|
| `preflight.sh --cpu` | (1) image present; (2) transient `gmx --version` works; (3) project dir exists & writable; (4) free disk ≥ estimate for requested run (§15). Any mode. Used before phases 1–4 and 7. |
| `preflight.sh --gpu` | (1) `gromacs-rocm` container running (`docker compose ps`); (2) `rocm-smi` shows no foreign VRAM consumer; (3) `gmx --version` shows HIP + `--offload-arch=gfx1100`; (4)–(5) as `--cpu`. **Detection only — never switches mode.** Exit 2 + "MODE" line if not in gromacs mode → agent applies MS2/MS3 (self-check, then autonomous switch or escalate). Used before GPU phases (5–6, large-system EM). |
| `check_prep.sh` | `pdb2gmx` exit 0; no `missing`/`WARNING: atom` lines in its log; **cumulative charge integer at every residue** (parse `.top`); atom count = input + expected H; `.posre.itp` present. |
| `check_solvation.sh` | `grompp` test run with `assets/em.mdp` succeeds; **cutoff < ½·min(box vectors)** (parse box from `.gro`); net charge integer and ≈ 0; ion counts > 0; `[ molecules ]` order consistent with `.gro`. |
| `check_em.sh` | `Fmax < emtol` (parse the EM log — SD or CG, whichever ran); `Epot` in expected band (solvated biomolecule, per KB 01.4); no LINCS/SHAKE warnings; no "exceeded" / "Panic" lines. |
| `check_equil.sh` | from `.edr` via `gmx energy`: last-20% mean T within ±5 K of ref; last-20% mean P within ±30% of ref (NPT); density within 2% of FF/water-model expectation (table in script); no energy spike > 3× median in last 10%. |
| `check_prod.sh` | final step in log == `nsteps`; no constraint/range-check warnings; checkpoint file present; drift sanity (total-energy trend from `.edr`); xtc frame count == expected. |
| `analyze.sh` | runs the §11 suite; verifies every expected `.xvg`/`.png`/report artifact exists and is non-empty; writes `07_analysis/REPORT.md`. |
| `cleanup.sh` | phase-8 gate (D15): pre-gates — `REPORT.md` present, `state.json` phase ≥ 7, no live mdrun (`check_running.sh`); then whitelist-only deletion (`#*.N#` backups, `*.cpt` in 05/06, `step1.xtc`/`msd_sub.xtc`); post-verification (zero `#*.N#` remain, `md.xtc`/`clean.xtc`/`REPORT.md` intact). Dry-run without `--apply`; idempotent. Host-side, no container. |
| `check_templates.sh` | diffs each `assets/*.mdp` against the corresponding KB `03.2` block (modulo `<<<...>>>` placeholders); PASS if in sync, FAIL + list divergent keys if not (D13). |

All scripts: `set -euo pipefail`, take the simulation dir as `$1`, print
machine-parseable lines, exit code as contract. No LLM judgment in any check.

### assets/ MDP templates (D13)
Location: **`.pi/skills/gromacs-sim/assets/`**. Copied from KB `03.2` at
implementation time, parameterized only by clearly marked `<<<...>>>`
placeholders (nsteps, ref-t, ref-p, box margin, ion conc). `em.mdp`: steepest
descent, `emtol = 100`, `nsteps = 20000`. `cg.mdp`: identical to `em.mdp`
except `integrator = cg` (D10 fallback). `nvt.mdp` / `npt.mdp` / `md.mdp`:
exactly the KB 01.5/01.6 recommended blocks (v-rescale / C-rescale, `h-bonds`,
`refcoord-scaling = com` in NPT, `nstxout-compressed = 1000`, …).

**Why copies, not links (D13):** KB `03.2` is annotated documentation, not
executable files; the agent needs clean, parameterized `.mdp` files. **Drift
guard:** `check_templates.sh` + the `gromacs-kb-audit` block probes keep
`assets/` in sync with KB `03.2` (single source of truth = KB; `assets/` =
derived executable copies).

## 7. Workflow state machine

### Phases

```
0 preflight → 1 prep → 2 topology → 3 solvation → 4 EM
→ 5a NVT → 5b NPT → 6 production → 7 analysis → 8 cleanup → done
```

Every phase: **entry condition → execute → gate script → state update**.
A failed gate = stop, diagnose (KB `01.9`/`03.4`), fix, re-gate. Never skip.

### `state.json` (machine state — the resume backbone, per simulation)

```json
{
  "sim": "lysozyme",
  "schema": 1,
  "created": "2026-09-18T20:00:00Z",
  "updated": "2026-09-18T21:14:00Z",
  "phase": "06-production",
  "phase_status": "running",
  "plan_approved": true,
  "params": {
    "ff": "amber14sb", "water": "opc", "ph": 7.0,
    "box": "cubic", "box_margin_nm": 1.0, "ion_conc_m": 0.15,
    "temp_k": 300, "pressure_bar": 1.0,
    "dt_ps": 0.002, "prod_time_ps": 10000,
    "nvt_ps": 100, "npt_ps": 500
  },
  "files": {
    "input_pdb": "input/lysozyme.pdb",
    "top": "03_solvation/topol.top",
    "em_out": "04_em/em.gro",
    "prod_tpr": "06_production/md.tpr",
    "prod_traj": "06_production/md.xtc"
  },
  "gates": {
    "preflight":  { "status": "pass", "at": "...", "evidence": "preflight.out" },
    "prep":       { "status": "pass", "at": "..." },
    "solvation":  { "status": "pass", "at": "..." },
    "em":         { "status": "pass", "at": "...", "algo": "sd|cg" },
    "equil":      { "status": "pass", "at": "..." },
    "analysis":   { "status": "pass", "at": "..." },
    "cleanup":    { "status": "pass", "at": "...", "freed_gb": 5.32, "files": 58 }
  },
  "runs": {
    "em":   { "status": "done", "log": "04_em/em.log" },
    "nvt":  { "status": "done", "log": "05_equil/nvt.log" },
    "npt":  { "status": "done", "log": "05_equil/npt.log" },
    "md":   { "status": "running", "started": "...", "expected_end": "...",
              "restarts": 0, "log": "06_production/md.log" }
  },
  "decisions": [
    { "at": "...", "tier": "B", "decision": "npt 500 ps (system ~150 k atoms)",
      "rationale": "KB 01.5 typical 0.5–2 ns" }
  ]
}
```

*If the D10 CG fallback runs, `runs` also gains an `em_cg` entry (and `gates.em.algo` = `cg`, `files.em_out` = `04_em/em_cg.gro`).*

Rules:
- **S1.** Written atomically (write temp + `mv`) after every completed step.
  **Single writer: only the agent writes `state.json`.**
- **S2.** On any invocation, `state.json` is read before doing anything.
- **S3.** If `state.json` is missing/corrupt, the agent reconstructs from
  directory contents + `RUNLOG.md` and says so.

### `RUNLOG.md` (human-readable narrative, per simulation)
Append-only log: every Tier A/B decision with rationale, every gate result,
every run start/stop/restart, every user interaction. This is the audit trail
and the "what did we decide and why" record.

## 8. Plan-first protocol (Tier A)

For a **new** simulation the agent produces and presents:

```
PLAN — <sim name>
System:        <PDB id/file>, residues kept/removed, metals, disulfides
Force field:   <ff>   Water: <water>   (matched set per KB 00.6)
Box:           <type>, margin <x> nm → ~<L> nm cube
Ions:          <conc> M, counterions to neutrality
EM:            steepest descent, emtol 100 (CG fallback from SD result if needed)
Equil:         NVT <100> ps → NPT <500> ps, posre on solute
Production:    NPT <10 000> ps, dt 2 fs, xtc every 2 ps, cpt every ~6 s (wall, -cpt 0.1)
Est. size:     ~<N> atoms, ~<GB> disk, ~<h> wall time on this GPU
Analysis:      default suite (§11) [+ additions]
Out of scope:  <any non-FF residue detected → hard stop here>
```

One approval → `plan_approved: true` → autonomous execution until a Tier C
stop. Changes to Tier A parameters after approval require a new approval.

## 9. Phase protocols (summary — details in `references/`)

| Phase | Container | Core actions | KB ref | Gate |
|-------|-----------|-------------|--------|------|
| 0 preflight | both | `--cpu` (phases 1–4, 7) / `--gpu` (phases 5–6, large-system EM) | 03.3 §Phase 0 | `preflight.sh` |
| 1 prep | transient | text-level PDB curation (waters, alt-loc, chains), `pdb2gmx -ff <ff> -water <w> -i posre.itp` | 01.1 | `check_prep.sh` |
| 2 topology | transient | verify `.top` (defaults first, moleculetype per name, order), posre wired | 01.2 | (folded into solvation gate) |
| 3 solvation | transient | `editconf`/`solvate` (box ≥ 2×cutoff + margin), `genion` (neutrality + 0.15 M), update `[ molecules ]` | 01.3 | `check_solvation.sh` |
| 4 EM | transient (CPU) / live GPU (large systems, Tier B) | `grompp` + `mdrun` (SD; CG fallback from SD result), inspect Fmax/Epot | 01.4 | `check_em.sh` |
| 5a NVT | **live GPU** | `assets/nvt.mdp`, posre, `gen-vel`, 100 ps | 01.5 | `check_equil.sh` (T) |
| 5b NPT | **live GPU** | `assets/npt.mdp`, posre, `refcoord-scaling = com`, 500 ps | 01.5 | `check_equil.sh` (T+P+density) |
| 6 production | **live GPU** | `assets/md.mdp`, **no posre**, full GPU offload, `-cpt`, detached exec (D11) | 01.6, 03.5 | `check_prod.sh` |
| 7 analysis | transient (+ host plots) | trjconv clean → suite → report | 01.8 | `analyze.sh` |
| 8 cleanup | host-side (no container) | dry-run → `--apply`: delete `#*.N#`/`.cpt`/derived intermediates (whitelist only) | 01.10 | `cleanup.sh --apply` |

**Input handoff:** the user supplies the structure by (a) dropping a file into
`gromacs/work/projects/<sim>/input/`, or (b) giving a PDB ID — the agent fetches it
via `curl` from RCSB (container has curl) into `input/`. The sim name is chosen
by the agent (Tier B) and confirmed in the plan (Tier A).

**EM algorithm (D10):**
1. **SD** — `gmx grompp -f em.mdp -c ../03_solvation/solvated.gro -p
   ../03_solvation/topol.top -o em.tpr` → `gmx mdrun -deffnm em` → `em.gro`
   (final), `em.edr`, `em.log`.
2. **Gate** — parse `em.log` for Fmax. Fmax ≤ `emtol` → **done** (EM output =
   `em.gro`).
3. **CG fallback** (only if Fmax > emtol) — `gmx grompp -f cg.mdp -c em.gro
   -p ../03_solvation/topol.top -o em_cg.tpr` → `gmx mdrun -deffnm em_cg`.
   Note `-c em.gro`: CG starts from **SD's final structure** (in `04_em/`),
   not the input.
4. **Gate** — parse `em_cg.log` for Fmax. ≤ emtol → **done** (EM output =
   `em_cg.gro`); else **Tier C stop** (real structural problem).

The downstream NVT phase uses whichever structure converged (`em.gro` or
`em_cg.gro`), recorded in `state.json` (`files.em_out`, `gates.em.algo`).

Canonical mdrun (production):
```bash
gmx mdrun -deffnm md -ntmpi 1 -nb gpu -pme gpu -bonded gpu -update gpu -cpt 0.1
```
(EM = steepest descent / conjugate gradients, not a dynamical integrator →
**no** `-bonded gpu`/`-update gpu`; CPU by default, `-nb gpu -pme gpu` only
for large-system GPU-EM (D9). NVT/NPT use `integrator = md` (dynamical) →
**full offload** recommended, same flags as production.)

## 10. Long-run execution & monitoring (LLM-free, per D6/D11/D12)

- **Launch (D11):** detached `docker compose exec -d`, log teed to file. No
  tmux.
- **Estimate:** after ~1000 steps, read ns/day from the log → compute
  `expected_end` → store in `state.json`.
- **CPU steps (phases 1–3, 7, and EM by default):** run synchronously in
  transient containers — they are short (EM on a solvated protein: minutes)
  and need no monitoring.
- **Short GPU runs (< ~30 min):** the agent polls the log in-session (bounded
  `sleep` in bash). No LLM calls while waiting. GPU-EM (large systems, D9) is
  treated as a GPU run — poll if short, fire-and-forget if long.
- **Long runs (fire-and-forget, D12):** after launch, the agent records
  `status: running` + `expected_end` in `state.json` and **ends the session**.
  There is **no watchdog** and no LLM wake-up. **It is the user's
  responsibility to re-invoke the agent** (or tell it the run has ended).
- **Re-inspect on re-invocation (the primary mechanism):** on any re-invocation
  where a run is `running`, the agent inspects the actual state and reconciles
  it into `state.json` before doing anything else:
  1. `pgrep -f "mdrun.*-deffnm <run>"` — process alive?
  2. Log tail — `Finished mdrun` (done) / `Panic`/`segfault` (crashed) /
     progress line (still running).
  3. Final step vs `nsteps` (parse log / `.edr`).
  4. Checkpoint present?
  → classify done / crashed / still-running, then proceed.
- **Crash protocol (bounded):**
  1. Read log tail → classify via KB `01.9`/`03.4`.
  2. Startup OOM/device error → **mode/VRAM problem** → Tier C stop (ask user).
  3. Transient (segfault, preemption) → restart from checkpoint
     `mdrun -deffnm md -cpi state.cpt` (exact restart, same `.tpr`).
     Max **3** auto-restarts, then Tier C stop.
  4. Physics blow-up (LINCS warnings, NaN, pressure runaway) → **no**
     auto-restart. Tier C stop with diagnosis + proposed fix (user approves
     any MDP change).
- **Never** auto-change physics parameters (dt, constraints, couppl) —
  propose, user approves.
- **Abort (on user request, D11):** `docker compose exec gromacs-rocm pkill -f
  "mdrun.*-deffnm <run>"` (SIGTERM → mdrun writes a checkpoint and exits
  cleanly). The last checkpoint is preserved, state marked `aborted`, resumable
  later via `-cpi`. On completion the agent reports that the stack **remains in
  `gromacs` mode** (MS1: leaving the mode is the user's decision).

## 11. Analysis suite (default, protein NPT)

Prep: `gmx make_ndx` (Backbone, CA, Protein, Water groups) →
`gmx trjconv -pbc mol -fit rot+trans -center` (fit on backbone).

| # | Quantity | Command (2026.3 names) |
|---|----------|------------------------|
| 1 | Energies, T, P, V, density | `gmx energy` (Total/Potential/Kinetic, Temp, Pres, Volume, Density) |
| 2 | RMSD (backbone fit → backbone & CA) | `gmx rms` |
| 3 | RMSF per residue | `gmx rmsf` |
| 4 | Radius of gyration | `gmx gyrate` |
| 5 | Secondary-structure fractions | `gmx dssp -num` |
| 6 | H-bond count over time | `gmx hbond -num` |
| 7 | MSD → diffusion (water + solute COM) | `gmx msd` |
| 8 | Density profile (z) | `gmx density` |

Outputs per item: `.xvg` + `.png`. **`REPORT.md`** summarizes: mean ± sd of
T/P/density over the last 50%, RMSD plateau value + time, Rg, SS conservation,
diffusion coefficient (Einstein), drift, and an explicit **caveats** section
(RMSD ≠ convergence; equilibration fraction; any warnings seen).

**Plotting:** `.xvg → .png` + REPORT.md number-crunching run in the
**`md-prep` sidecar container** (v1 build: `python:3-slim` + matplotlib only,
`gromacs/Dockerfile.mdprep`, transient, any stack mode — the v1.0 seed of the
v1.1 sidecar, §16). `analyze.sh` orchestrates: gromacs container for the gmx
suite → `md-prep` for plots/report. If `md-prep` is missing, the suite still
produces all `.xvg` + report and flags plots as skipped (not a gate failure).
No host Python dependency.

## 12. Failure handling

- Every failure: capture exact command + output → map via KB `01.9`
  (error catalog) / `03.4` (failure→diagnosis→fix) → state the diagnosis →
  apply fix only within Tier B, else propose (Tier A/C).
- `-maxwarn` is **never** used to silence unknown-option errors (KB 01.9 §B:
  it runs with defaults for removed options).
- All failures + resolutions are appended to `RUNLOG.md`.

## 13. Safety rules (beyond the §5 hard rules)

The §5 hard rules apply in full. Additional safety constraints:
1. Disk check before solvation and before production (§15 sizing).
2. GPU exclusivity: one simulation at a time per GPU (VRAM is exclusive anyway).
3. All GROMACS work inside the container; host bash only for orchestration,
   state, and plotting.

## 14. Conformance test (lysozyme)

**Purpose:** end-to-end regression proving the agent works; doubles as
self-test (`/skill:gromacs-sim selftest` or agent task "run conformance").

- **Input:** `gromacs/work/gmx_tutorials_livecoms/tutorial-files/01_lysozyme/`
  (PDB + reference MDPs for cross-checking).
- **Protocol (short, GPU-fast):** EM → NVT 10 ps → NPT 50 ps → production
  200 ps, xtc every 2 ps.
- **Pass criteria (all scripted):** every gate PASS (incl. phase-8 cleanup);
  all §11 artifacts present; `REPORT.md` written; RMSD finite; T/P within
  bands; zero `#*.N#` files remain after cleanup; total wall time recorded;
  `state.json` ends `done`.
- **Cross-check:** agent's MDPs must be option-compatible with the tutorial's
  (differences allowed only where 2026.3 changed names — KB change notes).
- Run the conformance test once before declaring v1 complete, and after any
  change to skill scripts/templates.
- **Coverage note:** lysozyme is protein-only; nucleic acids are in scope
  (§2) but not conformance-tested in v1.

## 15. Project layout & sizing

```
gromacs/work/projects/<sim>/
├── state.json            # machine state (S1–S3)
├── RUNLOG.md             # human audit trail
├── input/                # user PDB + curation notes
├── prep/                 # (v1.1) sidecar outputs: .itp/.mol2
├── 01_prep/              # protein.gro/.top/.itp/.posre.itp
├── 03_solvation/         # solvated.gro, ions.gro, topol.top
├── 04_em/                # em.mdp/.tpr/.gro/.log (+ em_cg.* if CG fallback)
├── 05_equil/             # nvt.*, npt.*
├── 06_production/        # md.*, state.cpt, md.log
└── 07_analysis/          # clean.xtc, *.xvg, *.png, REPORT.md
```

**Disk sizing (estimate, used by preflight):** solvated protein ≈
0.02 GB per 100k atoms (top+gro); `.xtc` ≈ 1–3 MB/frame at 2 ps spacing;
`.edr` ≈ 0.1 GB/ns; `.log` ≈ 100 MB/ns. Preflight requires ≥ 2× estimate free.

**VRAM sizing (24 GB, D14):** comfortable to ~1.5–2 M atoms with full offload;
preflight warns (Tier B note) above ~2 M atoms.

## 16. v1.1 extension — Python sidecar (design now, build later)

- **Container `md-prep`** (CPU-only, no GPU devices, no mode dependency —
  runs in any stack mode, same pattern as `gromacs-kb-audit`'s transient
  containers): python3 + ACPYPE + AmberTools (antechamber/sqm) + PROPKA +
  PDB2PQR + matplotlib + MDAnalysis.
- **Seeded in v1:** `md-prep:latest` is built from day one with
  `python:3-slim` + matplotlib only (`gromacs/Dockerfile.mdprep`, one-time
  `docker build`, no compose entry) and owns phase-7 plotting/REPORT.md. The
  v1.1 upgrade extends the same Dockerfile — no rename, no new image.
- **Interface contract (fixed now so v1 stays compatible):**
  - Shared volume: same `gromacs/work` mount.
  - Inputs: `<sim>/prep/input/` (pdb, ff name, pH, charge).
  - Outputs: `<sim>/prep/out/` (`.itp`, `.mol2`, `prep_report.md`).
  - The v1 "hard stop + integrate" boundary (§2) is exactly what the sidecar
    automates: v1 stops and asks the user to run the commands; v1.1 runs them
    in the sidecar. The agent's integration path (validate `.itp`: charge
    balance, atom types, `grompp` test) is identical in both versions.
- **Analysis upgrade:** sidecar owns plotting + MDAnalysis (RMSD clustering,
  PCA, custom analyses) — `analyze.sh` delegates when the sidecar exists.

## 17. Implementation checklist (ordered)

1. `.pi/skills/gromacs-sim/` skeleton: SKILL.md + references/ (9 files).
2. `assets/` MDP templates from KB 03.2 (probe them with the `gromacs-kb-audit`
   block-verdict method before use) + `check_templates.sh` drift check (D13).
3. `scripts/`: preflight → check_prep → check_solvation → check_em →
   check_equil → check_prod → analyze (each unit-tested on the lysozyme
   tutorial artifacts where possible). No watchdog (D12).
4. `.pi/agents/gromacs-md.md` (frontmatter + system prompt from §5) + the
   `/gromacs-md` slash command / prompt template (D2).
5. Build the `md-prep` sidecar (v1 seed): `docker build -t md-prep:latest
   -f gromacs/Dockerfile.mdprep gromacs/` (python:3-slim + matplotlib).
6. **Launcher verification (D6/D2):** launch the agent from an **iGPU**
   session (foreground) and confirm no iGPU slot-contention error. If it
   fails, document "launcher must not be on the iGPU" and adjust the Launcher
   constraint in §0.
7. **Model selection dry-run (R5):** agent prepares lysozyme through EM in
   **transient containers** (no mode switch at all) — once with
   `igpu-Gemma4-26B-A4B`, once with `igpu-Qwen3.6-35B-A3B`; compare decisions
   + gate outputs; pin the winner in the frontmatter.
8. Dry run (winner model): same lysozyme prep through EM — validates gates
   0–4 in the current stack mode.
9. **Conformance input:** fetch the lysozyme PDB (1LYZ from RCSB) into
   `gromacs/work/gmx_tutorials_livecoms/tutorial-files/01_lysozyme/` — the
   tutorial dir ships the reference MDPs only, no PDB.
10. **Full conformance test** (§14) — must pass end to end.
11. Docs: short `gromacs/AGENT_USAGE.md` (how to invoke — including the
    launcher-must-be-on-iGPU requirement — what to expect, plan format,
    resume semantics).

## 18. Open questions (parked, non-blocking)

- **O1.** Optional `notify-send` on run completion — a one-shot desktop nudge
  is a nice-to-have on top of D12's fire-and-forget (keeps monitoring
  LLM-free). Verify availability on this host; not a gate.
- **O2.** MTS (`mts = yes`, ~2× single-GPU throughput, KB 03.5): off by
  default in v1; add as Tier B opt-in in v1.1 after stability validation.
- **O3.** `gmx energy` interactive term selection in `analyze.sh`: use
  non-interactive `-if`/`-o` file form (verify exact 2026.3 flags during
  implementation via KB 00.2 / build probe).
- **O4.** `.edr` disk estimate (0.1 GB/ns in §15) is likely an overestimate —
  verify against a real run (safe direction for the 2× gate, but tighten).
