# Phase 6 — Production MD

Entry: `05_equil/` passed both gates. Work in `<sim>/06_production/`.
**Requires gromacs mode** — run `preflight.sh <sim> --gpu` first (exit 2 +
`PI_PROVIDER` has `:8093` → `make gromacs`, re-run preflight; on the eGPU →
hard-stop). Detached run (D11 — no tmux).

## Steps

```bash
cp <sim>/05_equil/npt.gro <sim>/03_solvation/topol.top <sim>/06_production/
# render assets/md.mdp — REF_T/REF_P from state.json (Tier A; the asset's
# 300 K / 1.0 bar are placeholders, NOT the plan), nsteps from the Tier A
# production length (SKILL.md "MDP templates"); NO posre:
scripts/render_mdp.sh .pi/skills/gromacs-sim/assets/md.mdp <sim>/state.json 5000000 <sim>/06_production/md.mdp

docker compose exec -w /work/projects/<sim>/06_production gromacs-rocm bash -c '
  set -e
  cd /work/projects/<sim>/06_production
  gmx grompp -f md.mdp -c npt.gro -p topol.top -o md.tpr
'
# verify planned run length from the .tpr that will actually run (see 01.7),
# and the GPU-profile pre-check (SKILL.md "GPU profile selection"):
docker compose exec -w /work/projects/<sim>/06_production gromacs-rocm \
  gmx dump -s md.tpr | grep -E '^[[:space:]]*(nsteps|dt)[[:space:]]*='
VS="$(docker compose exec -w /work/projects/<sim>/06_production gromacs-rocm \
  gmx dump -s md.tpr 2>/dev/null | awk '/[Vv]irt.*site/{i=1;next} \
    i&&/nr:/{t=$0;gsub(/[^0-9]/,"",t);s+=t+0;i=0} END{print s+0}')"
# nsteps/dt must match the Tier A plan; a mismatch means the MDP was edited
# without re-running grompp (stale .tpr) — re-run grompp before mdrun.
# guard: no duplicate/orphan mdrun (hard rule 2)
bash .pi/skills/gromacs-sim/scripts/check_running.sh <sim>
# detached — survives session end.
# default (VS==0) = gpu_full; if VS>0 use gpu_safe (swap "-update gpu" for
# "-update cpu"); record the profile in RUNLOG.md:
docker compose exec -d gromacs-rocm bash -c \
  "cd /work/projects/<sim>/06_production && gmx mdrun -deffnm md -cpt 0.1 -ntmpi 1 -nb gpu -pme gpu -bonded gpu -update gpu > md.log 2>&1"
```

Canonical flags — never improvise: full offload
(`-nb gpu -pme gpu -bonded gpu -update gpu`) — **except** when the
virtual-site pre-check says `VS>0`, then use `-update cpu` (gpu_safe; see
SKILL.md "GPU profile selection") — `-cpt 0.1` (minutes ≈ every 100 ps at
2 fs), `-ntmpi 1`. Confirm the log says update/constrain on GPU (or on CPU
when gpu_safe).

## Monitoring (see `monitoring.md`)

```bash
docker compose exec gromacs-rocm pgrep -f "mdrun.*-deffnm md"   # alive?
docker compose exec gromacs-rocm tail -30 /work/projects/<sim>/06_production/md.log
docker compose exec gromacs-rocm rocm-smi                        # VRAM
```

pgrep empty but NO clean end (final step < nsteps, no end-marker) = silent
death — not a crash to debug in the log. NOTE the end-marker VARIES by run:
some logs end with `Finished mdrun`, others with `GROMACS reminds you` /
`Writing final coordinates` — do NOT treat a missing `Finished mdrun` as a
death (lysozym's completed NPT runs end with the quote, not `Finished mdrun`).
Common causes of a real silent death on this stack: **GPU memory access
fault** (`Memory access fault by GPU node-1 ... Page not present` — transient
eGPU driver/hardware fault, seen twice on lysozym NPT), OOM, or host kill.
Capture the post-mortem BEFORE relaunch and record it in RUNLOG.md:

```bash
docker compose exec gromacs-rocm bash -c 'grep -E "Memory access fault|Panic" /work/projects/<sim>/06_production/md.log; dmesg 2>/dev/null | tail -20; rocm-smi; ps aux | grep -c defunct'
```

## Gate (after completion)

```bash
scripts/check_prod.sh <sim_dir>
```

Checks: `md.tpr` nsteps == `md.mdp` nsteps (stale-`.tpr` check), final step ==
nsteps (read from the `.tpr`), no constraint/range-check warnings, checkpoint
present, xtc frame count == expected (±1), total-energy drift (first-10% vs
last-10% mean) < 5%.

KB: `01.6` (production), `03.5` (GPU/MTS). Failure modes: `01.9`.

> **Provenance (Pymacs)**: the GPU profile ladder (full → `-update cpu` →
> nb-only → CPU), the virtual-site pre-check, and the `gmx dump` run-length
> verification are adapted from the Pymacs automation suite (Schulz, Reynolds,
> Schürer, *Eur. J. Med. Chem.* (2026) 316:119038, doi:10.1016/j.ejmech.2026.119038;
> code: https://github.com/schurerlab/Pymacs), re-verified against the local
> 2026.3 HIP build.
