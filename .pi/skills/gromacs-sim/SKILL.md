---
name: gromacs-sim
description: >
  State machine + deterministic gates for end-to-end GROMACS MD simulations on
  this stack (2026.3 HIP build). Use for any simulation: prep, topology,
  solvation, EM, equilibration, production, analysis, cleanup.
---

# gromacs-sim

End-to-end GROMACS MD workflow: PDB → solvated system → EM → NVT → NPT →
production → analysis report → cleanup. The workflow is a **state machine**: each phase
has an entry condition, actions (see `references/<phase>.md`), a **gate
script**, and a state update. A failed gate = stop, diagnose via KB
`01.9`/`03.4`, fix, re-gate. Never skip a gate.

## Skill assets (how to find them)

Every relative path in this skill resolves against this skill's own
directory — the directory containing this SKILL.md file. Determine it as
`<skill_dir>` using standard pi skill locations, in this order:

1. The available-skills list in your system prompt shows this skill's
   `SKILL.md` location — use its parent directory.
2. Otherwise check the standard pi locations:
   - `<project>/.pi/skills/gromacs-sim/`  (project scope, `<project>` = the
     directory pi was launched from)
   - `~/.pi/skills/gromacs-sim/`          (user scope)

Verify with `ls` before first use. If the directory is not found in a
standard location, stop and report it — do not guess other paths (e.g. a
`gromacs/skills/` directory does not exist).

- Runbooks: `<skill_dir>/references/<phase>.md`
- Gate scripts: `<skill_dir>/scripts/<name>`
- MDP templates: `<skill_dir>/assets/*.mdp`

Domain knowledge (commands, MDP options, FF/water facts, error catalog) lives
in this skill's `knowledge/` directory (sibling of `references/`, `scripts/`,
`assets/`) — this skill never duplicates it. The local 2026.3 build is the
gold standard over any web doc.

## Phases

```
0 preflight → 1 prep → 2 topology → 3 solvation → 4 EM
→ 5a NVT → 5b NPT → 6 production → 7 analysis → 8 cleanup → done
```

| Phase | Mode | Runbook | Gate |
|-------|------|---------|------|
| 0 preflight | any (cpu) / gromacs (gpu) | `references/00-preflight.md` | `preflight.sh <sim> --cpu\|--gpu` |
| 1 prep | transient | `references/01-prep.md` | `check_prep.sh <sim>` |
| 2 topology | transient | `references/02-topology.md` | folded into solvation gate |
| 3 solvation | transient | `references/03-solvation.md` | `check_solvation.sh <sim>` |
| 4 EM | transient CPU (GPU for large systems, Tier B) | `references/04-em.md` | `check_em.sh <sim>` |
| 5a NVT | **live GPU** | `references/05-equilibration.md` | `check_equil.sh <sim> nvt` |
| 5b NPT | **live GPU** | `references/05-equilibration.md` | `check_equil.sh <sim> npt` |
| 6 production | **live GPU** | `references/06-production.md` | `check_prod.sh <sim>` |
| 7 analysis | transient + md-prep | `references/07-analysis.md` | `analyze.sh <sim> <prod_ps>` |
| 8 cleanup | host-side (no container) | `references/08-cleanup.md` | `cleanup.sh <sim> --apply` |

Phase 8 is **mandatory** — a sim is not `done` until the cleanup gate passes.
`cleanup.sh` (no args after the sim dir) is a dry-run; only `--apply` deletes.
It removes only whitelisted transient artifacts (GROMACS `#*.N#` auto-backups,
`*.cpt` checkpoints, two derived intermediates) — never `md.xtc`, `clean.xtc`,
results, or parameters (KB `01.10`).

Run `scripts/check_templates.sh` at phase 0 (mandatory — includes a grompp smoke
test that catches real asset bugs, e.g. the I-85 T-coupling defect). PASS/FAIL per
template; FAIL = stop and report.

## Container invocation (verbatim)

```bash
# CPU work — transient container, any stack mode (phases 1-4, 7 gmx suite)
docker run --rm -w /work/projects/<sim>/<phase> -v "$PWD/gromacs/work":/work \
  gromacs-hip-gfx1100:latest <cmd>

# GPU dynamic run — live container, gromacs mode only (phases 5-6)
docker compose exec -w /work/projects/<sim>/<phase> gromacs-rocm <cmd>

# long run — detached, survives session end
docker compose exec -d gromacs-rocm bash -c \
  "cd /work/projects/<sim>/<phase> && gmx mdrun -deffnm <run> ... > <run>.log 2>&1"

# is it running? / inspect / VRAM / abort
docker compose exec gromacs-rocm pgrep -f "mdrun.*-deffnm <run>"
docker compose exec gromacs-rocm tail -30 /work/projects/<sim>/<phase>/<run>.log
docker compose exec gromacs-rocm rocm-smi
docker compose exec gromacs-rocm pkill -TERM -f "mdrun.*-deffnm <run>"   # clean checkpoint

# plotting + REPORT.md — md-prep sidecar, any mode
docker run --rm -v "$PWD/gromacs/work":/work md-prep:latest python3 - <args> < scripts/plot_report.py
```

Batch related CPU commands into one `docker run` (`bash -c 'cmd1 && cmd2'`).
The launching session must be on the iGPU (user's responsibility); the agent
self-checks `PI_PROVIDER` contains `:8093` before any autonomous mode switch.

**Files created in the container are root-owned on the host** (the container
runs as root; the `/work` bind mount does not remap ownership). Consequences:
- The host user cannot `chmod`/`chown` them, and overwriting an existing
  root-owned file in place fails (`cp new old` → permission denied on the
  inode). Replace with `rm <file> && cp <new> <file>` — deletion works because
  the *directory* is user-owned (only the file inode is root-owned).
- To delete/fix a root-owned file from inside the container:
  `docker run --rm -v "$PWD/gromacs/work":/work gromacs-hip-gfx1100:latest rm <path>`.
- `cleanup.sh` is unaffected (host-side `rm -f` on user-owned directories).

## Hard rules (mdrun launch)

Before launching **any** `mdrun` (phases 4-6), all three must hold:
1. **Preflight** — `preflight.sh <sim> --cpu|--gpu` for the phase passed.
2. **Running-check** — `check_running.sh <sim>` passed: no mdrun already
   running and no orphaned gromacs container. A **timed-out tool call does NOT
   kill the container** — the `docker run`/`compose exec` client dies but the
   container (and its mdrun) keeps running. Always re-check before every launch.
3. **Correct mode** — phases 5-6 run in the **live** `gromacs-rocm` container
   (gromacs mode). Never launch a phase-5/6 mdrun in a transient CPU container.

**Long runs must be detached.** Any run that may exceed ~2 min (all of phases
5-6) uses `docker compose exec -d ... > <run>.log 2>&1`, then is monitored by
`tail`-ing the log + `pgrep` — never by a blocking foreground call (a
foreground call that hits the tool timeout leaves an orphan; see rule 2).

## GPU profile selection (phases 5-6)

Full offload (`-nb gpu -pme gpu -bonded gpu -update gpu`) is fastest, but
`-update gpu` is **not supported with virtual sites** (nor FEP, replica
exchange, Ewald surface correction, constraint pulling, orientation
restraints, triangle constraints — KB `03.5`). Select the profile
**deterministically** after grompp, before mdrun — do not guess:

```bash
# after grompp, before mdrun (phase dir + run name per phase).
# gmx dump always prints empty "Virtual site N:" headers (nr: 0), so sum the
# nr: counts — 0 means no virtual sites (a text grep would false-positive):
VS="$(docker compose exec -w /work/projects/<sim>/<phase> gromacs-rocm \
  gmx dump -s <run>.tpr 2>/dev/null | awk '/[Vv]irt.*site/{i=1;next} \
    i&&/nr:/{t=$0;gsub(/[^0-9]/,"",t);s+=t+0;i=0} END{print s+0}')"
```

**Ladder** (top-down; a failed attempt exits at startup in seconds — GROMACS
validates GPU task assignment before integrating, so each attempt is cheap):

| # | Profile | Flags | Use when |
|---|---------|-------|----------|
| 1 | `gpu_full` | `-nb gpu -pme gpu -bonded gpu -update gpu` | default (`VS == 0`) |
| 2 | `gpu_safe` | same, but `-update cpu` | `VS > 0` (virtual sites) |
| 3 | `gpu_nb_only` | `-nb gpu` only | profile 2 also fails at startup |
| 4 | `cpu` | (no GPU flags) | all GPU profiles fail |

Record the chosen profile in `RUNLOG.md`. The mdrun log must confirm the
assignment (KB `03.5` "Confirming the GPU is engaged"); a silent CPU fallback
fails the phase gate. Phase 4 (EM) does **not** use this ladder — see
`references/04-em.md` (`-nb gpu` only, Tier B).

## Script catalog

All scripts: `set -euo pipefail`, sim dir as `$1`, one
`PASS|FAIL|<check>|<detail>` line per check, exit `0` pass / `1` fail /
`2` environment error. No LLM judgment in any check.

| Script | Purpose |
|--------|---------|
| `preflight.sh <sim> --cpu` | image, transient gmx, sim dir, disk (any mode) |
| `preflight.sh <sim> --gpu` | + gromacs-rocm running, VRAM idle, HIP/gfx1100. Exit 2 + `MODE` line if not in gromacs mode |
| `check_prep.sh <sim>` | pdb2gmx log clean, residue charges integer, gro↔top atom count, posre |
| `check_solvation.sh <sim>` | grompp test (em.mdp), cutoffs < ½·min(box), net charge, ions > 0 |
| `check_em.sh <sim>` | Fmax < emtol, Epot band, no LINCS/SHAKE/panic |
| `check_equil.sh <sim> [nvt\|npt]` | last-20% T ±5 K, P within ±15 bar of ref (npt), density stable (std<1%) in 950–1050 kg/m³ (KB 01.5), no 3× energy spike |
| `check_prod.sh <sim>` | final step == nsteps, log clean, checkpoint, xtc frames, drift |
| `analyze.sh <sim> <prod_ps>` | 8-item suite → .xvg, then md-prep → .png + REPORT.md |
| `cleanup.sh <sim> [--apply]` | phase-8 gate: pre-gates (REPORT.md, state phase ≥ 7, no live mdrun), whitelisted deletion of `#*.N#`/`.cpt`/derived intermediates, post-verification. Dry-run without `--apply`. Host-side, no container. |
| `check_templates.sh` | assets/*.mdp vs KB 03.2 drift check + grompp smoke test vs protein+water |
| `check_running.sh <sim>` | no mdrun in live container + no orphaned gromacs container (mandatory before any mdrun launch) |

## State & resume

Project layout (per simulation):

```
gromacs/work/projects/<sim>/
├── state.json  RUNLOG.md  input/  cleanup_report.txt
├── 01_prep/  03_solvation/  04_em/  05_equil/  06_production/  07_analysis/
```

**Resume protocol:** read `state.json` → locate `phase`/`phase_status` →
verify the phase's last artifact exists → continue from there. A `running`
production run: check `pgrep` (alive → monitor; dead → read log tail →
diagnose via KB 01.9/03.4 → resume with `-cpi state.cpt` if checkpointed).
A project at phase 7-completed resumes by running phase 8
(`cleanup.sh <sim> --apply`; idempotent — 0 bytes freed if already clean).
Update `state.json` + append `RUNLOG.md` after **every** completed step.

## MDP templates

`assets/{em,cg,nvt,npt,md,ions}.mdp` — executable copies of KB 03.2 with
`<<<KEY:default>>>` placeholders. Render into the phase dir before use —
**the sed defaults are fallbacks, never the plan**: `REF_T`/`REF_P` come
from `state.json` (Tier A), `NSTEPS` from the Tier B plan, then the rest fall
to defaults. **Always use `scripts/render_mdp.sh`** — it reads REF_T/REF_P
from state.json internally and self-checks the rendered file (values match
state.json, no unrendered placeholders). Do NOT re-type the sed pattern by
hand: a re-render in a fresh shell with unset variables renders EMPTY
REF_T/REF_P and grompp fatales (RCA issue 8, lysozym 2026-09-25):

```bash
scripts/render_mdp.sh .pi/skills/gromacs-sim/assets/nvt.mdp <sim>/state.json 50000 <sim>/05_equil/nvt.mdp
# -> PASS|render|<sim>/05_equil/nvt.mdp (ref_t=310 ref_p=n/a nsteps=50000)
```

Placeholders per asset: `em`/`cg` → `NSTEPS` only; `nvt` → `NSTEPS`, `REF_T`
(incl. `gen-temp`); `npt`/`md` → `NSTEPS`, `REF_T`, `REF_P`. (A run rendered
with the 300 K default while `state.json` says 310 K is a Tier A violation —
issues_agent_run, lysozym 2026-09-25.)

`ions.mdp` is for the pre-genion test grompp only (plain cutoff, no PME) —
never a simulation MDP.

> **Provenance (Pymacs)**: the GPU profile ladder (full → `-update cpu` →
> nb-only → CPU) and the virtual-site pre-check are adapted from the Pymacs
> automation suite (Schulz, Reynolds, Schürer, *Eur. J. Med. Chem.* (2026)
> 316:119038, doi:10.1016/j.ejmech.2026.119038; code:
> https://github.com/schurerlab/Pymacs), re-verified against the local 2026.3
> HIP build.
