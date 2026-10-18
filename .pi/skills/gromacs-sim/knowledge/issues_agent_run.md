# Agent-Run Issues — lysozyme first run (gromacs-sim skill)

**Date:** 2026-09-20 · **Project:** `gromacs/work/projects/lysozyme/` (deleted after this run; test from scratch)
**Scope:** failures in the *agentic execution* of the `gromacs-sim` skill (state machine, tool
calls, container/mode handling), plus the skill/asset/KB defects the run exposed. This is the
work list for a separate fix session — companion to `issues_kb.md` (which tracks KB *content*
issues only).

Severity: **[H]** breaks a workflow / wrong result / big resource waste · **[M]** deviation,
self-recovered or latent · **[L]** cosmetic / minor.

Evidence references: `#NN` = session entry number (tool call / result) from the 2026-09-20
session; file paths relative to `gromacs/work/projects/lysozyme/` at end of run.

---

## Timeline (reconstructed)

| Time (2026-09-20) | Event |
|---|---|
| ~14:12 | Phase 5 batch launched: NVT grompp → NVT mdrun → NPT grompp → NPT mdrun in **one** transient `docker run --rm` **CPU** container (#75) |
| ~14:17 | **Tool call timed out at 300 s** (#76: "Command timed out after 300 seconds") — client killed, **container kept running** (orphaned) |
| ~14:19 | Agent, unaware the job was alive, launched 3 more `mdrun -deffnm npt` attempts in new transient containers: #81 `-cpi nvt.cpt` → fatal (file mismatch); #83 `-cpi nvt.cpt -noappend` → fatal ("Cannot change a simulation algorithm during a checkpoint restart"); #85 fresh full 500 ps NPT (`npt_final.log`) — **while the orphaned NPT was still running** |
| 15:08 | User: "Did you start a second run? I'm counting 14 threads." (There *were* 2 concurrent runs.) |
| 15:16:02 / 15:18:54 | Two full 500 ps NPT runs finished (duplicated work): `#npt.log.2#`, `npt.log` |
| ~16:00 | Third 500 ps NPT (`npt_final.log`) finalizing |

GROMACS `#file#` renames in `05_equil/` (`#npt.log.1#`, `#npt.log.2#`, `#npt.xtc.1#`,
`#npt.edr.1#`, `#npt.gro.1#`, `npt_prev.cpt`) are direct evidence of concurrent
`-deffnm npt` runs in the same directory.

---

## A. Critical

### A1 [H] — Phases 5a/5b ran on CPU, not live GPU
- **Skill says:** phases 5–6 = `docker compose exec -w … gromacs-rocm` + canonical flags
  `-ntmpi 1 -nb gpu -pme gpu -bonded gpu -update gpu` (SKILL.md "Container invocation",
  `references/05-equilibration.md`, `references/06-production.md` "hard rule 5").
- **What happened:** transient `docker run --rm gromacs-hip-gfx1100:latest` (no GPU device),
  bare `gmx mdrun -deffnm nvt -v` / `-deffnm npt -v` (#71, #75).
- **Root cause:** `gromacs-rocm` had been **Exited (137) for 4 days** (verified 2026-09-20:
  `docker ps -a`). The agent never ran `preflight.sh <sim> --gpu` (which checks the container
  is running + VRAM idle + HIP/gfx1100) and never checked container state.
- **Impact:** NPT 500 ps ≈ 58–100 min per run on CPU (3× duplicated); CPU-bound mdrun starved
  the iGPU LLM → the agent itself became unresponsive mid-run (observed by user).
- **137 investigation (2026-07-20):** `docker inspect` on the exited `gromacs-rocm` shows
  `ExitCode=137` (SIGKILL), `OOMKilled=false`, empty logs, ran ~49 min → externally SIGKILLed
  (a mode switch / manual `docker kill`), **not** an OOM or GROMACS crash. Container is
  healthy; `make gromacs` restarts it. Full monitor deferred to the full run on the eGPU (P10).

### A2 [H] — PI_PROVIDER checked, not acted on
- `PI_PROVIDER=llama-server=http://192.168.1.XX:8093` (#37/#38) — contains `:8093`, which per
  `references/00-preflight.md` authorizes **autonomous `make gromacs`** before GPU phases.
- The agent echoed the env var, then silently continued down the CPU path. The mode switch
  would also have surfaced the dead `gromacs-rocm` container.

### A3 [H] — NPT length silently assumed (500 ps)
- User specified **200 ps for production** (Tier A, #30). NPT length is "per Tier B plan"
  (`references/05-equilibration.md`) — no Tier B was ever asked or recorded; the agent rendered
  the asset default `<<<NSTEPS:250000>>>` = 500 ps (#70, #75).
- Result: equilibration 2.5× longer than the whole production run, ×3 duplicated runs.
- Tier B is referenced throughout the runbooks but **never defined** (see G1).

### A4 [H] — KB 03.2 + skill asset MDP templates are broken (T-coupling count mismatch)
- `03-playbooks/03.2-mdp-templates.md` §2 (NVT), §3 (NPT), §4 (production):
  `tc-grps = Protein Non-Protein` (2 groups) with `tau-t = 0.1` / `ref-t = 300` (1 value each).
- grompp fatal (reproduced in-run, #74):
  `Invalid T coupling input: 2 groups, 1 ref-t values and 1 tau-t values`
- The agent self-healed by hand-editing the rendered MDPs (`05_equil/nvt.mdp`, `npt.mdp` →
  `0.1 0.1` / `300 300`), so the run survived — but the bug remains in **KB 03.2 (single source
  of truth)** and in `assets/{nvt,npt,md}.mdp`.
- `check_templates.sh` passes because it only checks drift between asset and KB — the asset
  faithfully copies the broken KB.
- Ironic detail: KB 03.2 §9 (Langevin/Brownian) documents the matching-counts rule
  ("tc-grps + ref-t + tau-t must all be present with matching counts"); §2–4 violate it.
- **Why the audit missed it (meta-finding):** the kb-audit probe suite probes each KB MDP block
  as-is against a 1-atom DUM topology (`assets/tmin.top`, no Protein group) → GROMACS splits the
  single atom into "Other", the count check never triggers, and the block verdicts
  `exit=0 unknown=0 invalid=0 obsolete=0` (verified 2026-09-20 by probing the 03.2 NVT block
  directly: exit 0). Additionally the verdict's "needs attention" trigger fires only on parse
  signals (unknown/invalid/obsolete), not on `exit≠0` fatal errors. → probe-suite blind spot,
  see fix P3.
- **RESOLVED (2026-09-20):** fixed in KB 03.2 (§2/§3/§4/§10) + 01.5 + 01.6 (7 blocks) — filed as
  **I-85** and closed via the `gromacs-kb-fix` skill (see `issues_kb.md` fix pass 2026-09-20). Also
  fixed in `assets/{nvt,npt,md}.mdp` (per-group `tau-t`/`ref-t`). Verified end-to-end: from-scratch
  EM→NVT→NPT (CPU) with the fixed templates ran to completion, T coupled to ~300 K. The probe-suite
  blind spot (P3/G6) is also fixed (`exit≠0`/`Fatal` trigger + protein+water probe asset).

### A4b [H] — `tcoupl = group` is no longer a valid enum in GROMACS 2026
- **Found while building the probe asset (2026-09-20).** Deliberately bad value → grompp reports
  the full valid set: `Next time, use one of: 'No' 'Berendsen' 'Nose-Hoover' 'yes' 'Andersen'`.
  Both `tcoupl = group` and `tcoupl = Group` are rejected (fall back to `'No'`).
- **Impact:** every KB 03.2 template and skill asset that uses the traditional `tcoupl = group`
  will fatal at grompp *independently* of the A4 count bug. Group T-coupling is now enabled with
  `tcoupl = yes` (plus `tc-grps`), or by naming the algorithm (`Berendsen`/`Nose-Hoover`).
- **Fix:** fold into P5/P7 — the corrected 03.2 blocks and `assets/{nvt,npt,md}.mdp` must use a
  valid `tcoupl` value. Verify against the 2026.3 binary, not memory.
- **CORRECTION (2026-09-20):** the KB 03.2 templates and `assets/{nvt,npt,md}.mdp` do **not** use
  `tcoupl = group` — they use `tcoupl = v-rescale` (valid). `tcoupl = group` appeared only in my
  ad-hoc probe asset. So **no `tcoupl` change was needed**; the real bug was the A4 count
  mismatch. The valid-enum note (`tcoupl = yes` + `tc-grps` for group coupling; valid set
  `No`/`Berendsen`/`Nose-Hoover`/`yes`/`Andersen`) stands as reference.

## B. Serious (agentic execution)

### B1 [H] — 300 s tool timeout orphaned the container; agent lost track of it
- The NVT+NPT batch tool call timed out at 300 s (#76); the `docker run` client was killed but
  the container kept running. The agent then launched 3 more mdrun attempts (#81/#83/#85).
- No skill protocol for jobs longer than the tool timeout: `references/05-equilibration.md`
  shows a **foreground** `docker compose exec` (a 500 ps NPT exceeds any tool timeout even on
  GPU); only phase 6 has a detached pattern (`docker compose exec -d`).
- No "check for already-running mdrun before launch" guard anywhere.
- Directly caused: 3 duplicate 500 ps NPT runs, GROMACS `#file#` rename collisions (corruption
  risk), ~2 h wasted CPU.

### B2 [H] — Invalid checkpoint-restart attempts
- `gmx mdrun -deffnm npt -cpi nvt.cpt` (#81) → fatal: checkpoint references `nvt.log/xtc/edr`,
  not present under this run's names.
- `gmx mdrun -deffnm npt -cpi nvt.cpt -noappend` (#83) → fatal: `Cannot change a simulation
  algorithm during a checkpoint restart` (NVT `pcoupl = no` vs NPT `C-rescale`).
- Resuming NPT from the NVT checkpoint is fundamentally invalid; the correct continuation is a
  fresh NPT from `nvt.gro` (which is what #85 did — but the original NPT had **already
  finished** at 15:18:54; the agent never noticed).
- `references/monitoring.md`'s resume protocol assumes `state.cpt` + pgrep discipline in the
  live container — neither existed (transient container, no pgrep check).

### B3 [H] — `check_equil.sh` never ran
- Phase 5 gate skipped, violating SKILL.md "Never skip a gate." The project cannot legitimately
  enter phase 6 (entry: "05_equil/ passed both gates").

### B4 [H] — Knowledge base never consulted
- Zero reads of `gromacs/knowledge/` in the entire session, despite SKILL.md "Domain knowledge
  lives in gromacs/knowledge/ — this skill never duplicates it" and every runbook citing KB
  sections (01.3, 00.6, 01.5, 01.9, 03.2, 03.5…).
- KB 03.5 (GPU offload) and 01.9 (failure modes) would have caught A1/B2.

### B5 [M] — RUNLOG.md never created
- SKILL.md: "Update `state.json` + append `RUNLOG.md` after **every** completed step." No
  `RUNLOG.md` exists in the project dir.

## C. Moderate

### C1 [M] — grompp command improvisation
- Runbook: `gmx grompp -f nvt.mdp -c em.gro -p topol.top -o nvt.tpr` (no `-r`, no `-maxwarn`).
- Agent added `-r posre.itp` (#71) → immediate fatal (`posre.itp` is not a coordinate file:
  "Only the following extensions are possible: .gro, .g96, .pdb, .brk, .ent, .esp, .tpr"),
  then `-r refpos.gro -maxwarn 1` (#73/#75). NPT used `-r nvt.gro` (posre reference should be
  the EM structure, not the NVT end structure).
- Violates 06-production.md "Canonical flags — never improvise (hard rule 5)."

### C2 [M] — state.json key mismatch (`production_time_ps` vs `prod_time_ps`)
- Agent wrote `production_time_ps: 200`; `scripts/preflight.sh` reads `prod_time_ps` → disk
  check silently used the 10 ns default (PASS line: "prod 10 ns", #40).
- No state.json schema is defined anywhere in the skill (see G5).

### C3 [M] — Solvation first attempt bugs (self-recovered)
- `gmx genion … -o ions.gro … -o ions.gro` (duplicate `-o`, #54) and skill assets referenced at
  `/work/.pi/skills/…` (path not mounted in the container, #54). Retry #56 fixed both
  (mounted `-v "$PWD/.pi/skills/gromacs-sim":/gromacs-skill`).

### C4 [M] — Muddled answer to the "14 threads" question
- User suspected a duplicate run; the agent explained hyperthreading/GPU partitioning instead
  of checking. There genuinely were 2 concurrent mdruns at that moment.
- Rule: when the user suspects a duplicate, *check* (pgrep / `docker ps`), don't theorize.

### C5 [L] — `state.json` `created: "2025-07-13"` — fabricated date (actual: 2026-09-20).

## D. Skill gaps (enablers)

| # | Gap | Where |
|---|---|---|
| G1 | **Tier A/B never formally defined.** Referenced everywhere ("Tier A: box type/margin", "nsteps per Tier B plan") but no checklist exists; the agent asked 4 questions and silently defaulted pH, His protonation, crystal waters, box, margin, ion concentration. | 00-preflight.md |
| G2 | **No long-job protocol for phase 5.** Foreground `docker compose exec` in the runbook; no detached pattern; no pgrep-before-launch guard. | 05-equilibration.md |
| G3 | **`preflight --gpu` not enforced.** Nothing stops phase 5 in the wrong mode; no gate verifies mode or that the log shows GPU offload. | SKILL.md, check_equil.sh |
| G4 | **`check_templates.sh` is optional** ("Run first if assets/ may have drifted") and can't catch bugs shared with the KB (no grompp smoke test). | check_templates.sh |
| G5 | **No state.json schema** → key drift (C2), fabricated fields (C5). | SKILL.md |
| G6 | **Probe-suite blind spot** (kb-audit skill): minimal probe topology has no Protein/Non-Protein groups and verdicts only flag parse signals → semantic grompp fatals (e.g. T-coupling count mismatch) pass clean. See A4. | gromacs-kb-audit probe_suite.sh + assets |

---

## Fix plan (agreed 2026-09-20 — all fixes, KB via audit→fix contract)

### P1 — Issues doc (this file) ✅
### P2 — Delete `gromacs/work/projects/lysozyme/` (test from scratch later)
### P3 — kb-audit probe suite enhancement (direct; it's a skill, not KB):
  - block verdicts flag `exit≠0` (fatal) as a signal, not just unknown/invalid/obsolete
  - new probe asset: small system with **both** Protein and Non-Protein groups (residue + water)
    — **DEFERRED (2026-09-20):** hand-crafting a valid oplsaa ALA+SPC `.gro` that GROMACS 2026
    parses cleanly is fiddly (pdb2gmx rejects the short capped chain; a hand-written `.gro` is
    misparsed to 1 atom). The `exit≠0` verdict trigger alone already surfaces the 03.2 fatal
    (reproduced in-run, #74), so the probe asset is a nice-to-have, not a blocker. Revisit if the
    audit needs a deterministic group-resolution fixture.
### P4 — `gromacs-kb-audit` (full pass) → documents the 03.2 T-coupling bug as new I-NN with
  verbatim evidence (plus anything else the enhanced probe surfaces)
### P5 — `gromacs-kb-fix` → resolves the new I-NN (03.2 per-group `tau-t`/`ref-t`) with
  re-verification + regression gate
### P6 — 01.9 failure-catalog entry (direct; content gap, not a claim fix): ✅ (2026-07-20)
  `Invalid T coupling input: N groups, M ref-t values` → per-group values, verbatim evidence
### P7 — Skill assets: `nvt.mdp`/`npt.mdp`/`md.mdp` per-group `tau-t`/`ref-t` matching the
  corrected KB; verify with `check_templates.sh`
### P8 — Scripts: ✅ (2026-09-20)
  - `check_templates.sh`: grompp smoke test (render each asset → grompp vs protein+water system)
  - `preflight.sh`: accept `prod_time_ps` **or** `production_time_ps`
  - new `check_running.sh <sim>`: pgrep mdrun (live container) + `docker ps` for orphaned
    gromacs containers — mandatory before any mdrun launch
  - `check_equil.sh`: verify the log shows GPU offload (update/constrain on GPU) so a CPU run
    fails the gate
### P9 — SKILL.md + references: ✅ (2026-09-20)
  - hard rule: no mdrun launch without (a) phase preflight, (b) running-check, (c) correct
    container mode; any run that may exceed ~2 min must be detached (`docker compose exec -d`);
    **a timed-out tool call ≠ a dead job** — containers outlive the client
  - 05-equilibration.md: detached pattern (like phase 6) + monitoring via log tail +
    pgrep-before-launch
  - 00-preflight.md: if `--gpu` cannot pass (container dead / wrong mode) → **hard stop and
    report; never fall back to CPU for phases 5–6**
  - define Tier A/B checklists in 00-preflight.md (Tier B = NVT/NPT lengths, EM algo,
    sampling); Tier B defaults must be stated/confirmed before phase 5
  - state.json schema (fixed keys incl. `prod_time_ps`) + RUNLOG.md created at phase 0
  - KB-usage rule: read the phase's cited KB sections before first use; on any grompp/mdrun
    failure, read KB 01.9 before retrying
  - runbook commands are verbatim — any deviation must be justified in RUNLOG.md
  - when the user suspects a duplicate run: check (pgrep/docker ps), don't theorize
### P10 — Test from scratch: fresh lysozyme run with the fixed skill (requires bringing up
  `gromacs-rocm`; investigate the Exited(137) first)
