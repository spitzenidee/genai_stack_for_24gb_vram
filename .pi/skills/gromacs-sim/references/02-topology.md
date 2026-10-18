# Phase 2 — Topology verification

Entry: `01_prep/` passed its gate. Work in `01_prep/` (topology stays there
until solvation copies it forward).

## Checks (no separate gate — folded into `check_solvation.sh`)

1. `[ molecules ]` section: one entry per molecule, counts correct.
2. `#include` lines present: FF (`amber14sb.ff/forcefield.itp`), water
   (`<ff>/<water>.itp`), ions (`<ff>/ions_<water>.itp`), posre (inside
   `#ifdef POSRES`).
3. Position restraints wired: `posre.itp` included; `define = -DPOSRES` in
   EM/equilibration MDPs only (never in production — D: production runs
   without posre).
4. Water model in the topology include **is** the water model (the include
   sets the model; `solvate` only supplies coordinates).

The final topology after `genion` is kept as `03_solvation/topol.top`.

KB: `01.2` (topology), `00.6` (FF/water).
