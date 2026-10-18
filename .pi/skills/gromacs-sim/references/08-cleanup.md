# Phase 8 — Cleanup

Entry: `07_analysis/` passed its gate (`analyze.sh` exit 0, `REPORT.md`
written). Host-side only — **no container needed**, any stack mode.

Mandatory last phase: a simulation is not `done` until this gate passes.

## One command

```bash
scripts/cleanup.sh <sim_dir>            # dry-run: report what would be deleted
scripts/cleanup.sh <sim_dir> --apply    # execute
```

The agent runs `--apply` autonomously (the plan approval covers it) and
appends the dry-run/apply output to `RUNLOG.md`. The script refuses
(exit 2, nothing deleted) if `REPORT.md` is missing, `state.json` phase < 7,
or an mdrun/orphaned container is detected (`check_running.sh`).

## What is deleted (whitelist — nothing else is ever touched)

| Tier | Pattern | Why transient |
|------|---------|---------------|
| T1 | `#*.N#` files in all phase dirs | GROMACS auto-backups: any tool that re-writes an existing output renames the old one to `#name.1#`, `#name.2#`… Re-running the analysis suite leaves N−1 stale copies of every ~GB trajectory (lysozyme: 5 suite runs → 5.03 GB, 71 % of the project). |
| T2 | `*.cpt` in `05_equil/`, `06_production/` | Checkpoints exist only to resume an interrupted run. Both runs are complete. |
| T3 | `07_analysis/step1.xtc`, `07_analysis/msd_unwrapped.xtc`, `07_analysis/{dssp.dat,hbond.ndx,num.xvg,hbnum.xvg}` | Derived intermediates, regenerable from `06_production/md.xtc` (two `trjconv` steps, ~10 min) / the analysis suite. |

## What is kept (forever)

- `06_production/md.xtc` — the **source trajectory**; everything else derives
  from it. Never deleted.
- `07_analysis/clean.xtc` — policy decision: kept so re-analysis does not
  require re-running `trjconv` on the full trajectory.
- All `.mdp`/`.top`/`.tpr`/`.gro` (reproducibility chain), the 10 `.xvg` +
  10 `.png` + `REPORT.md` + `index.ndx` (results), all logs, `input/`,
  `state.json`, `RUNLOG.md`.
- Gray zone (kept, small, diagnostic value): `05_equil/*.xtc`,
  `04_em/em.log`, `07_analysis/md.gro`.

Reference size (lysozyme, 10 ns, 34 k atoms): **6.6 GB raw → ~1.3 GB
cleaned** (5.32 GB / 58 files freed).

## Regeneration (if a kept file is ever lost)

`clean.xtc` from `md.xtc` (2026.3 two-step, see `07-analysis.md`):
`gmx trjconv -pbc mol` → `step1.xtc`, then `-fit rot+trans -center` →
`clean.xtc`. `msd_unwrapped.xtc`: `gmx trjconv -s md.tpr -f md.xtc -pbc nojump
-o msd_unwrapped.xtc` (System in/out; **no fit** — MSD needs unwrapped, not
fitted; see the 07-analysis.md MSD row).

## After re-analysis

`analyze.sh` re-creates `#*.N#` backups of the previous outputs. Re-run
`cleanup.sh <sim_dir> --apply` — it is idempotent (0 bytes freed on an
already-clean project).

## State update

`state.json`: `phase: 8`, `phase_status: "completed"`,
`gates.cleanup: { "status": "pass", "at": "<utc>", "freed_gb": <n>,
"files": <n> }`. Append to `RUNLOG.md`: files/bytes freed, before/after size.

KB: `01.10` (cleanup & retention).
