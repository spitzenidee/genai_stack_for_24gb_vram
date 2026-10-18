# Monitoring & run lifecycle

Applies to any detached GPU run (phases 5–6).

## State checks

```bash
# alive?
docker compose exec gromacs-rocm pgrep -f "mdrun.*-deffnm <run>"
# progress (last table row = current step)
docker compose exec gromacs-rocm tail -30 /work/projects/<sim>/<phase>/<run>.log
# VRAM (exclusive: one simulation per GPU)
docker compose exec gromacs-rocm rocm-smi
```

## Resume on re-invocation

1. `state.json` says `running` + `pgrep` finds mdrun → **monitor only**;
   update `runs.<run>.expected_end` if it is stale; do not touch the run.
2. `state.json` says `running` + `pgrep` finds nothing → the run ended or
   died. Read the log tail:
   - final step == nsteps → completed: run the phase gate, advance.
   - last step < nsteps, log ends cleanly (SIGTERM) → checkpoint exists:
     resume with `gmx mdrun -deffnm <run> -cpi state.cpt` (detached, same
     flags). Increment `runs.<run>.restarts`.
   - error in log → diagnose via KB `01.9`/`03.4`; fix within Tier B only.
3. After any resume: update `state.json` + `RUNLOG.md`.

## Abort (only on user request or hard failure)

```bash
docker compose exec gromacs-rocm pkill -TERM -f "mdrun.*-deffnm <run>"
```

SIGTERM → mdrun writes a clean checkpoint and exits. Mark state `aborted`;
resumable via `-cpi`.

## Reporting

After a run completes: report progress + gate result. After a GPU phase
finishes: state that the stack **remains in `gromacs` mode** (leaving the
mode is the user's decision — MS1).
