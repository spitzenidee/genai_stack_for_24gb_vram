# Phase 1 — Prep (PDB → pdb2gmx)

Entry: `input/` contains the user PDB; Tier A decisions made (FF, water, pH,
what to delete/keep). Work in `<sim>/01_prep/`.

## Steps (one transient container, batched)

```bash
docker run --rm -w /work/projects/<sim>/01_prep -v "$PWD/gromacs/work":/work \
  gromacs-hip-gfx1100:latest bash -c '
    set -e
    cd /work/projects/<sim>/01_prep
    # 1. curate: strip crystal waters (RCSB PDBs include them as HETATM),
    #    resolve alt-loc (keep A / first), drop unneeded chains — Tier A first
    grep -v "^HETATM" ../input/<name>.pdb > clean.pdb
    # 2. build topology + coords
    gmx pdb2gmx -f clean.pdb -ff <ff> -water <water> \
        -i posre.itp -o protein.gro -p protein.top > pdb2gmx.log 2>&1
  '
```

2026.3 notes (verified):
- `pdb2gmx` needs an explicit `-p <top>` — the default name is `topol.top`.
- RCSB PDBs contain crystal waters (e.g. 1LYZ: 101 HETATM) — `pdb2gmx`
  silently includes them as SOL. Strip HETATM first (Tier A: user decides
  which waters to keep).
- `-ss` is a boolean in 2026.3 (no `-ss` value); histidine protonation is
  assigned automatically from the H-bond network (check the log for
  `Will use HISD/HISE/HISP for residue N`).

## Gate

```bash
scripts/check_prep.sh <sim_dir>
```

Checks: pdb2gmx log clean (no missing atoms/fatal), cumulative charge integer
at every residue, `.gro` ↔ `.top` atom counts equal, `posre.itp` present.

KB: `01.1` (prep), `00.3` (PDB curation). Failure modes: `01.9`.
