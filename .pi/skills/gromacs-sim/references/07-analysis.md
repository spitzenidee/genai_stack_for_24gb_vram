# Phase 7 — Analysis

Entry: `06_production/` passed its gate. Work in `<sim>/07_analysis/`.
Transient containers, any stack mode.

## One command

```bash
scripts/analyze.sh <sim_dir> <prod_time_ps>
```

`prod_time_ps` is **required** — pass it (from Tier A / `state.json`), else
REPORT.md shows "Production length: unknown".

The script:
1. **gromacs container** (one transient run): `make_ndx` (group numbers
   discovered by name, never hardcoded) → two-step `trjconv` (2026.3: `-pbc
   mol` and `-fit rot+trans -center` are incompatible in one call) →
   `clean.xtc` (whole system: PBC-unwrapped, fit on Backbone, centered on
   Protein) → the 8-item suite → 10 `.xvg` files:

   | # | Quantity | Command | Output |
   |---|----------|---------|--------|
   | 1 | Energies/T/P/V/density | `gmx energy` (7 terms) | `energies.xvg` |
   | 2 | RMSD (backbone fit → backbone & CA) | `gmx rms` ×2 | `rmsd_backbone.xvg`, `rmsd_ca.xvg` |
   | 3 | RMSF per residue | `gmx rmsf -res` | `rmsf.xvg` |
   | 4 | Radius of gyration | `gmx gyrate` | `gyrate.xvg` |
   | 5 | SS fractions | `gmx dssp -num` (`-o dssp.dat` + generic `num.xvg`, copied to `dssp.xvg`) | `dssp.xvg` |
   | 6 | H-bonds over time | `gmx hbond -num` (`-o hbond.ndx` + generic `hbnum.xvg`, copied to `hbond.xvg`) | `hbond.xvg` |
   | 7 | MSD → diffusion (water + protein, collective) | `gmx msd -trestart 100` ×2 on `msd_unwrapped.xtc` (unwrapped, **unfit**, from `md.xtc`) | `msd_water.xvg`, `msd_protein.xvg` |
   | 8 | Density profile (z) | `gmx density -o` | `density.xvg` |

2. **md-prep sidecar**: `scripts/plot_report.py` → one `.png` per `.xvg` +
   `REPORT.md` (T/P/density last-50% mean±sd, RMSD plateau + time, Rg, SS,
   Einstein D, drift, caveats). If the `md-prep` image is missing: all
   `.xvg` + minimal REPORT.md are produced, plots flagged `SKIP` — **not a
   gate failure**.
   - The `docker run` **must** use `-i` (stdin is the script) and pass the
     **container** path (`$CPATH/07_analysis`), not the host path. Without `-i`,
     `python3 -` reads empty stdin and exits 0 silently → a false `PASS|plots`
     with stale plots/REPORT.

Gate = script exit 0 (all `.xvg` + `clean.xtc` + plots/REPORT present).

KB: `01.8` (analysis). 2026.3 interface changes (verified against the local
build):
- `gmx energy -f <.edr>` directly (no `-if`); term selection is interactive —
  the script discovers term numbers by name. The term list is **multi-term per
  line, no colons** (e.g. `14  Temperature`), so discovery uses an unanchored
  `grep -oE`. Term names: `Potential`, `Kinetic-En.`, `Total-Energy` (hyphenated).
- `gmx trjconv`: `-fitgroup`/`-centergroup` removed (groups via stdin, order
  fit → center → output); `-pbc mol` and `-fit rot+trans` are **incompatible in
  one call** — split into two `trjconv` steps.
- `gmx msd`: `-com` removed. **`-mol` OOMs** (`Killed`) on the full
  trajectory even with `-trestart 100`, and on a subsampled file the
  `-dt <= -trestart` constraint makes per-molecule fits non-independent
  (D scatters, incl. negative entries) — use the **collective** MSD (no
  `-mol`). `-trestart` (default 10 ps) must be ≥ `-dt` (frame spacing);
  the script uses `-trestart 100` on a 2 ps trajectory to bound memory.
  2026.3 `gmx msd` **no longer prints the fitted D** — `plot_report.py`
  fits it from the curve (D = slope/6 over the linear regime: 100-2000 ps
  for water, 1000-5000 ps for a protein in a 10 ns run).
- **MSD needs unwrapped but NOT fitted**: the script derives
  `msd_unwrapped.xtc` directly from `md.xtc` (`gmx trjconv -pbc nojump`,
  System in/out) — **not** from `clean.xtc`. A per-frame-fit trajectory
  contaminates water MSD (verified D 2.87e-5 → 8.9e-5 cm²/s, 3× inflation)
  and removes protein COM diffusion. 2026.3: unwrap = `-pbc nojump`
  (old `-pbc no -ur` gone; `-ur` is now the unit-cell enum).
- `gmx energy` density term is in **kg/m³** (see the xvg yaxis label), not
  g/cm³ — REPORT.md labels it kg/m³ (1013 kg/m³ ≈ 1.01 g/cm³).
- `gmx density`: output flag is `-o` (not `-od`).
- `gmx dssp`: there is **no `-ss` flag**. Without the external DSSP binary in
  the image, `-num` reports the *count* of secondary-structure elements, not
  per-residue fractions (install DSSP in the image for per-residue SS).
  2026.3: `-o` requires the **`.dat`** extension (a `.xvg` target fatales);
  `-num` writes the numerical series to a **separate generic `num.xvg`**
  (the `-o` target holds the per-frame SS string) — the script copies
  `num.xvg` → `dssp.xvg` in the same run (a second dssp run in the dir
  would overwrite `num.xvg`).
- `gmx hbond`: 2026.3: `-o` requires the **`.ndx`** extension (a `.xvg`
  target fatales); `-num` writes the count series to a **separate generic
  `hbnum.xvg`** — the script copies `hbnum.xvg` → `hbond.xvg` in the same
  run. Two group selections via stdin (reference then target; `-r`/`-t`
  select specific groups).
- **Group numbering**: `make_ndx`'s listing numbers match the trjconv/rms/msd
  selection numbers for the default groups (Protein=1, C-alpha=3, Backbone=4,
  Water=12 here), so discovery by name is reliable. The `System` group
  (`0`) is selectable in `trjconv` — the MSD unwrap step uses it for
  System in/out (verified on the 2026.3 build).
