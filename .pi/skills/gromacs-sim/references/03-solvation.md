# Phase 3 — Solvation & ions

Entry: phase 2 checks done. Work in `<sim>/03_solvation/`.

## Steps (one transient container, batched)

```bash
docker run --rm -w /work/projects/<sim>/03_solvation -v "$PWD/gromacs/work":/work \
  gromacs-hip-gfx1100:latest bash -c '
    set -e
    cd /work/projects/<sim>/03_solvation
    cp ../01_prep/protein.gro ../01_prep/protein.top ../01_prep/posre.itp .
    # 1. box: center, cubic, 1.0 nm margin (Tier A: box type/margin)
    gmx editconf -f protein.gro -c -bt cubic -d 1.0 -o newbox.gro
    # 2. solvate — -cs site count MUST match the water model (see note below):
    #    3-site (SPC/E, TIP3P) -> spc216.gro ; 4-site (OPC, TIP4P) -> tip4p.gro
    gmx solvate -cp newbox.gro -cs spc216.gro -o solv.gro -p protein.top
    # 3. test grompp with the IONS MDP (plain cutoff, no PME — avoids the
    #    net-charge warning on the non-neutral pre-ion system)
    gmx grompp -f ions.mdp -c solv.gro -p protein.top -o solv.tpr
    # 4. ions: neutralize + 0.15 M (Tier A: concentration); group = SOL
    #    (number from the prompt list — print it, never hardcode 13)
    gmx genion -s solv.tpr -p protein.top -o ions.gro -neutral -conc 0.15
    # 5. final test grompp (this is what check_solvation.sh re-runs)
    gmx grompp -f em.mdp -c ions.gro -p protein.top -o _test.tpr && rm _test.tpr
    mv protein.top topol.top
  '
```

Copy `assets/ions.mdp` and a rendered `assets/em.mdp` into the phase dir
first (see SKILL.md "MDP templates").

## 2026.3 interface facts (verified against the local build)

- **Water box site count must match the water model** (a mismatch → grompp
  atom-count failure, e.g. 4-site box + 3-site SPC/E). 3-site models (SPC/E,
  TIP3P) → `-cs spc216.gro`. 4-site models (OPC, TIP4P) → `-cs tip4p.gro`
  (the only 4-site box in `$GMXLIB`; no `opc.gro` ships in this build). OPC is
  a 4-site SETTLE water (OW, HW1, HW2 + mass-0 `MW`, `[ settles ]` in
  `amber14sb.ff/opc.itp`). KB 00.6/01.3.
- `solvate` takes `-cp` (coordinates of protein) — `-f` is gone. `-p <top>`
  appends the SOL line to `[ molecules ]` automatically — always pass `-p`.
- `editconf` box distance is `-d` (not `-distance`).
- `genion -s` takes a **`.tpr`** (not `.gro`) and updates the topology
  **in place** (no `topol.top` rename — do it yourself if you want that name).
- `genion` group selection is interactive: print the group list, pick SOL by
  name, never by memorized number.
- Pre-genion grompp on the non-neutral system needs `ions.mdp` (plain
  `coulombtype = cutoff`, no PME) — PME + net charge is a hard grompp
  failure with default `maxwarn = 0`.

## Gate

```bash
scripts/check_solvation.sh <sim_dir>
```

Checks: grompp test with `em.mdp` (also proves top↔gro consistency),
`rvdw`/`rcoulomb` < ½·min(box), grompp reports no net-charge problem,
ion molecules present.

KB: `01.3` (solvation/ions/box), `00.6` (water models). Failure modes: `01.9`.
