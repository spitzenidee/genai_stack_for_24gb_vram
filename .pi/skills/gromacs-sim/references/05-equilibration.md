# Phase 5 — Equilibration (NVT → NPT)

Entry: `04_em/` passed its gate. Work in `<sim>/05_equil/`. **Requires
gromacs mode** (live GPU container) — run `preflight.sh <sim> --gpu` first. Exit 2
+ `PI_PROVIDER` has `:8093` (you're on the iGPU) → run `make gromacs`, re-run
preflight. On the eGPU → hard-stop (the switch would kill your LLM).

Before launching NVT, state the Tier B plan (nsteps per run, posre on/off with
rationale, extension strategy) and get user confirmation — the nsteps values in
this runbook are placeholders for that plan, not an approval.

## 5a — NVT

```bash
cp <sim>/04_em/em.gro <sim>/03_solvation/topol.top <sim>/05_equil/
# render assets/nvt.mdp — REF_T from state.json (Tier A; the asset's 300 K is
# a placeholder, NOT the plan), nsteps per Tier B plan (SKILL.md "MDP templates"):
scripts/render_mdp.sh .pi/skills/gromacs-sim/assets/nvt.mdp <sim>/state.json 50000 <sim>/05_equil/nvt.mdp

scripts/check_running.sh <sim_dir>   # HARD: no mdrun running / no orphan before launch
docker compose exec -w /work/projects/<sim>/05_equil gromacs-rocm \
  gmx grompp -f nvt.mdp -c em.gro -p topol.top -o nvt.tpr
# GPU profile selection (SKILL.md "GPU profile selection"): virtual-site
# pre-check -> pick flags from the ladder:
VS="$(docker compose exec -w /work/projects/<sim>/05_equil gromacs-rocm \
  gmx dump -s nvt.tpr 2>/dev/null | awk '/[Vv]irt.*site/{i=1;next} \
    i&&/nr:/{t=$0;gsub(/[^0-9]/,"",t);s+=t+0;i=0} END{print s+0}')"
# NVT is long (100+ ps) -> DETACHED (survives the tool timeout; a foreground
# call that times out leaves an orphan — see SKILL.md hard rules):
# default (VS==0) = gpu_full; if VS>0 use gpu_safe (swap "-update gpu" for
# "-update cpu"); record the profile in RUNLOG.md:
docker compose exec -d gromacs-rocm bash -c \
  "cd /work/projects/<sim>/05_equil && gmx mdrun -deffnm nvt -ntmpi 1 -nb gpu -pme gpu -bonded gpu -update gpu > nvt.log 2>&1"
# monitor (do NOT block on the exec): pgrep alive? + tail the log
docker compose exec gromacs-rocm pgrep -f "mdrun.*-deffnm nvt"
docker compose exec gromacs-rocm tail -30 /work/projects/<sim>/05_equil/nvt.log
# when pgrep is empty AND the log shows a clean end (final step == nsteps;
# end-marker varies: "Finished mdrun" OR "GROMACS reminds you"/"Writing final
# coordinates"):
scripts/check_equil.sh <sim_dir> nvt
# pgrep empty but NO clean end (final step < nsteps, no end-marker) = silent
# death. NOTE the end-marker VARIES by run: some logs end with "Finished
# mdrun", others with "GROMACS reminds you" / "Writing final coordinates" —
# do NOT treat a missing "Finished mdrun" as a death (lysozym's completed NPT
# runs end with the quote, not "Finished mdrun"). Common causes of a real
# silent death on this stack: GPU memory access fault ("Memory access fault
# by GPU node-1 ... Page not present" — transient eGPU driver/hardware fault,
# seen twice on lysozym NPT), OOM, or host kill. BEFORE relaunch: grep the
# run's log for the fault, then capture the post-mortem; record both in
# RUNLOG.md:
docker compose exec gromacs-rocm bash -c 'grep -E "Memory access fault|Panic" /work/projects/<sim>/05_equil/nvt.log; dmesg 2>/dev/null | tail -20; rocm-smi; ps aux | grep -c defunct'
```

## 5b — NPT

```bash
cp <sim>/05_equil/nvt.gro <sim>/05_equil/
# render assets/npt.mdp — REF_T/REF_P from state.json (Tier A; the asset's
# 300 K / 1.0 bar are placeholders, NOT the plan), nsteps per Tier B plan
# (SKILL.md "MDP templates"; C-rescale; refcoord-scaling = com).
# KB 01.5: plan 1000 ps MINIMUM for a solvated protein at 310 K (500 ps
# often fails the pressure gate — see 5c below):
scripts/render_mdp.sh .pi/skills/gromacs-sim/assets/npt.mdp <sim>/state.json 250000 <sim>/05_equil/npt.mdp

scripts/check_running.sh <sim_dir>   # HARD: no mdrun running / no orphan before launch
docker compose exec -w /work/projects/<sim>/05_equil gromacs-rocm \
  gmx grompp -f npt.mdp -c nvt.gro -p topol.top -o npt.tpr
# GPU profile selection (SKILL.md "GPU profile selection"): virtual-site
# pre-check -> pick flags from the ladder:
VS="$(docker compose exec -w /work/projects/<sim>/05_equil gromacs-rocm \
  gmx dump -s npt.tpr 2>/dev/null | awk '/[Vv]irt.*site/{i=1;next} \
    i&&/nr:/{t=$0;gsub(/[^0-9]/,"",t);s+=t+0;i=0} END{print s+0}')"
# NPT is long (500+ ps) -> DETACHED, same pattern as phase 6:
# default (VS==0) = gpu_full; if VS>0 use gpu_safe (swap "-update gpu" for
# "-update cpu"); record the profile in RUNLOG.md:
docker compose exec -d gromacs-rocm bash -c \
  "cd /work/projects/<sim>/05_equil && gmx mdrun -deffnm npt -ntmpi 1 -nb gpu -pme gpu -bonded gpu -update gpu > npt.log 2>&1"
# monitor: pgrep alive? + tail the log (never a blocking foreground call)
docker compose exec gromacs-rocm pgrep -f "mdrun.*-deffnm npt"
docker compose exec gromacs-rocm tail -30 /work/projects/<sim>/05_equil/npt.log
# when pgrep is empty AND the log shows a clean end (final step == nsteps;
# end-marker varies: "Finished mdrun" OR "GROMACS reminds you"/"Writing final
# coordinates"):
scripts/check_equil.sh <sim_dir> npt
# pgrep empty but NO clean end (final step < nsteps, no end-marker) = silent
# death. NOTE the end-marker VARIES by run: some logs end with "Finished
# mdrun", others with "GROMACS reminds you" / "Writing final coordinates" —
# do NOT treat a missing "Finished mdrun" as a death (lysozym's completed NPT
# runs end with the quote, not "Finished mdrun"). Common causes of a real
# silent death on this stack: GPU memory access fault ("Memory access fault
# by GPU node-1 ... Page not present" — transient eGPU driver/hardware fault,
# seen twice on lysozym NPT), OOM, or host kill. BEFORE relaunch: grep the
# run's log for the fault, then capture the post-mortem; record both in
# RUNLOG.md:
docker compose exec gromacs-rocm bash -c 'grep -E "Memory access fault|Panic" /work/projects/<sim>/05_equil/npt.log; dmesg 2>/dev/null | tail -20; rocm-smi; ps aux | grep -c defunct'
```

Both gates must pass before production. NPT gate checks: **GPU offload** (log
must not show `GPU detection failed` — a CPU run fails the gate), last-20% mean T
±5 K, mean P within ±15 bar of ref, density stable over the last 20% (std < 1%)
inside 950–1050 kg/m³ (KB 01.5: pressure is noisy — do not chase the exact
value; solvated protein+ion density runs above bulk water), no energy spike
> 3× median in the last 10%.

## 5c — NPT pressure gate failure (recovery)

If `check_equil.sh <sim> npt` fails on pressure (last-20% mean P outside
±15 bar of ref) — common at the 500 ps placeholder (KB 01.5: plan 1000 ps
minimum for a solvated protein at 310 K):

1. **Do NOT use `-cpi npt.cpt`** to extend: after a *completed* run the
   checkpoint is the final state, not a resumable mid-run state — mdrun
   exits immediately.
2. Re-render `npt.mdp` from the asset with **2× nsteps** (500 ps → 1000 ps →
   2000 ps) via `render_mdp.sh` (REF_T/REF_P from state.json internally —
   SKILL.md "MDP templates"), and re-run **from `nvt.gro`** (the NVT output),
   not from the failed NPT end state:
   ```bash
   scripts/render_mdp.sh .pi/skills/gromacs-sim/assets/npt.mdp <sim>/state.json 500000 <sim>/05_equil/npt.mdp
   docker compose exec -w /work/projects/<sim>/05_equil gromacs-rocm \
     gmx grompp -f npt.mdp -c nvt.gro -p topol.top -o npt.tpr
   # then the same detached mdrun + monitor pattern as 5b
   ```
3. If 1000 ps still fails, extend to 2000 ps (same pattern, nsteps 1000000).
4. Record the extension (old → new nsteps, gate P before/after) in RUNLOG.md.

Evidence: lysozym 310 K (2026-09-25): 500 ps failed (last-20% mean P = 45.5
bar), 1000 ps passed (P = 3.5 bar); a 300 K run needed 4000 ps. See
`work/projects/lysozym/POST_SIM_RCA.md` Issue 1.

KB: `01.5` (equilibration), `03.5` (GPU offload). Failure modes: `01.9`.

> **Provenance (Pymacs)**: the virtual-site pre-check before enabling
> `-update gpu` is adapted from the Pymacs automation suite (Schulz, Reynolds,
> Schürer, *Eur. J. Med. Chem.* (2026) 316:119038, doi:10.1016/j.ejmech.2026.119038;
> code: https://github.com/schurerlab/Pymacs), re-verified against the local
> 2026.3 HIP build.
