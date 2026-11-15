# gromacs-md — usage

The `gromacs-md` session runs a GROMACS MD simulation end to end:
PDB → prep → solvation → EM → NVT → NPT → production → analysis report →
cleanup. It owns its own state machine (the `gromacs-sim` skill), gates every
phase with deterministic scripts, and resumes exactly where it left off.

## Invoking

From the **stack root**, launch the dedicated gromacs-md session (a vanilla
pi session with the gromacs-md persona, pinned to the iGPU — see constraint
below):

```
./scripts/pi-gromacs
```

Then ask in plain language: "run me a 5 ns simulation of PDB 1ABC" (new
simulation), or name an existing project to resume it.

Projects live in `gromacs/work/projects/<sim>/` with `state.json`,
`RUNLOG.md`, and one directory per phase.

## ⚠️ Launcher constraint (read this first)

**The gromacs-md session runs on the iGPU — clear any eGPU session before a
GPU phase.**

The session's LLM is pinned to the iGPU llama-server (single slot), so the
run itself is safe from mode switches. But when a GPU phase needs `gromacs`
mode, the session runs `make gromacs`, which stops the eGPU services —
**including the LLM of any session running on the eGPU** (e.g. your main pi
session). If you have a session running on the eGPU, finish or pause it
before starting a GROMACS run, or the mode switch kills it mid-run.

## What to expect

1. **Tier A questions first** (once, up front): what to delete/keep in the
   PDB, force field + water model, box type/margin, ion concentration,
   production length, MD type. Answer these; everything after is
   autonomous.
2. **Phase reports.** After each phase the agent reports the gate result
   (`PASS/FAIL` lines) and moves on. A failed gate stops the run — the
   agent diagnoses via the knowledge base, fixes within its discretion
   (Tier B), and re-gates. It never skips a gate.
3. **GPU phases** (NVT, NPT, production) require `gromacs` mode. The agent
   switches to it autonomously (safe from an iGPU session) and **stays** in
   it afterwards — leaving the mode is your decision.
4. **Long runs are fire-and-forget.** Production runs detached; the agent
   (or you) can end the session. On the next invocation it reads
   `state.json`, checks whether the run is alive, and resumes — including
   checkpoint resume after a crash.
5. **End of run:** `07_analysis/` contains the trajectory, `.xvg`/`.png`
   plots, and `REPORT.md` (T/P/density, RMSD plateau, Rg, SS, diffusion,
   drift). Then **phase 8 (cleanup)** disposes of transient artifacts
   (GROMACS `#*.N#` auto-backups, `*.cpt` checkpoints, two derived
   intermediates) — whitelist-only, `md.xtc`/`clean.xtc`/results are never
   touched. A 10 ns project ends ~1.3 GB instead of ~6.6 GB. `state.json`
   ends `"done"`.

## Resume semantics

- `state.json` is the source of truth: `phase` + `phase_status` + file
  pointers. `RUNLOG.md` is the human-readable history.
- Any session can resume any project: `./scripts/pi-gromacs`, then name
  the project — the session reads state first, verifies the last artifact,
  continues.
- A `running` production run with a dead process: the agent reads the log,
  and resumes from `state.cpt` if a checkpoint exists (max lost time ≈
  checkpoint interval, ~100 ps).
- Only phase 8 (cleanup) deletes, and only the whitelisted transient classes
  (GROMACS `#*.N#` auto-backups, `*.cpt` checkpoints, `step1.xtc`/
  `msd_sub.xtc`). The source trajectory (`md.xtc`), `clean.xtc`, results,
  and all parameters are never deleted. Re-runs get new phase artifacts.

## What the agent will not do

- Parameterize ligands (v1: proteins, nucleic acids, FF-native cofactors).
- Change the stack (Dockerfile/Makefile/compose) or delete anything outside
  the phase-8 cleanup whitelist.
- Switch to any mode other than `gromacs`, or away from `gromacs`.
- Guess MDP values — templates + knowledge base only.
