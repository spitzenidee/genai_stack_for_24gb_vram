# Tickets — Import of Lemkul GROMACS Tutorials (`gmx_tutorials_livecoms`)

**Purpose**: track the incorporation of valuable content from the external repo
`https://github.com/jalemkul/gmx_tutorials_livecoms` into this knowledge base.
This file is the ticketing system: one ticket per addition. When a ticket's
work is implemented **and validated**, mark it `RESOLVED` with the date.

**Assessment**: see the comparison assessment delivered 2026-09-15 (10 gaps
identified; items 1–5 high value, 6–10 medium; chat context — the tickets
below are self-contained). All 10 are in scope, plus housekeeping (T-11).

---

## Source & attribution (applies to ALL tickets)

**Primary source (attribute in every KB file that incorporates its content):**

> **Provenance**: adapted from J. A. Lemkul, *From Proteins to Perturbed
> Hamiltonians: A Suite of Tutorials for the GROMACS-2025 Molecular Simulation
> Package*, Living Journal of Computational Molecular Sciences 1(1):5068 (2019),
> doi:10.33011/livecoms.1.1.5068; GROMACS-2025 update:
> https://github.com/jalemkul/gmx_tutorials_livecoms (CC BY 4.0).

- License is **CC BY 4.0** — reuse is permitted with attribution. Attribution
  is required **even when content is paraphrased/re-implemented** (not copied
  verbatim), because the author invested substantial time maintaining it.
- Add the provenance line as a `> **Provenance**: ...` blockquote at the end
  of each modified/created KB file (or extend an existing provenance block).
- **Scripts**: do NOT copy script code verbatim. `water_deletor.pl` is
  GPL-3.0 (Lemkul); `inflategro.pl` is "(c) 2005-2007 Christian Kandt" with no
  explicit license; `setupUmbrella.py` (Harms) is Python 2 and unlicensed.
  Document the *algorithm and parameters* in KB style; cite the original
  (Kandt, Ash & Tieleman, *Methods* 41:475–488, 2007, for InflateGRO).
- Secondary literature cited inside tickets (Boresch 2024, Yeh & Hummer 2004,
  Shirts 2003, Kelly 2005, Anisimov 2007, Ghosh 2012, Yang & Zhong 2006,
  Kandt 2007, Berger 1997, Hub 2010, Lemkul 2010, Kandasamy 2006, Boresch
  2003) are standard citations — include them in the KB text where the
  science is used. All verified against the repo's `gmx-tutorials-refs.bib`
  on 2026-09-15.

## Source clone

Cloned at `gromacs/work/gmx_tutorials_livecoms/` (gitignored). **Do not delete
until all tickets are RESOLVED** (validation re-checks need it).

Key source paths (relative to the clone):
- `gmx_tutorials.tex` — the full article (sections per tutorial)
- `tutorial-files/01_lysozyme/`, `02_membrane_protein/`, `03_complex/`,
  `04-06_free_energy/{04_methane_water,05_etoh_water,06_complex}/`,
  `07_umbrella/`, `08_biphasic/`, `09_vsites/`

## Global rules (apply to every ticket)

1. **Adapt, don't transplant.** The repo targets **GROMACS-2025**; this KB is
   pinned to **2026.3** (build `gromacs-hip-gfx1100:latest`). Repo MDP values
   that conflict with KB conventions MUST be replaced with KB conventions:
   - `Nose-Hoover`/`Berendsen` → `v-rescale` (thermostat), `C-rescale` (barostat)
   - `constraints = all-bonds` → `h-bonds` (GPU-resident update on this stack)
   - `ns_type = grid` → **remove** (gone in 2026.3)
   - `cutoff-scheme = group` → **not supported** (Verlet only in 2026.3)
   - `sc-alpha` → `sc-function = beutler` + `sc-r-power` (2026.3 naming)
   - `gmx bar -f md*.xvg` (legacy xvg API) → current `gmx bar` reading `.edr`
   - `fourier_nx/ny/nz`, `optimize_fft` → probe before adopting (may be gone)
2. **Every MDP block added to the KB must be grompp-verified** against the
   build (validation protocol V1 below).
3. **Every ticket ends with the provenance line** in the target KB file(s).
4. **Known source defects — do NOT propagate:**
   - D1: Tutorial 7 text says "correction equal to $2k_BT\ln(4)$" — the
     equation and `correct_pmf.py` both use **ln(r)**; adopt ln(r).
   - D2: Tutorial 6 `correct_restraints.py` example: `r0 = 0.53` with a
     comment claiming "0.40 nm (4.0 Angstroms)"; the angle values carry
     similarly stale comments ("95.57 # 90 degrees", "74.45 # 75 degrees").
     The printed result (−30.5631 kJ/mol) matches the *values* (r0 = 0.53,
     θ_A = 95.57°, θ_B = 74.45°), not the comments.
   - D3: Tutorial 3 text: `sort_mol2_bonds.pl jz4.mo2` — filename typo
     (missing `l`).
   - D4: Umbrella mdp files carry a stale comment "Berendsen temperature
     coupling is on" above `Tcoupl = Nose-Hoover`.
   - D5: `setupUmbrella.py` is Python 2 (`raw_input`, bare `print`) — broken
     in py3; superseded by `find_windows.py`. Do not document it.
   - D6: `job.sh` scripts hardcode `/usr/local/gromacs/bin` (2018-era).
   - D7: Tutorial 6 (binding free energy) is **incomplete in the source**:
     red placeholder text, and `06_complex/` contains only
     `correct_restraints.py` (no mdp/topology/scripts referenced in the text).
   - D8: Tutorial 9 vsites: the equation prints
     `a = (0.213173+0.0184135)/0.213173 = 1.0851116`, but the stated inputs
     evaluate to **1.086378** (0.27 pm difference — negligible). Adopt the
     repo's value 1.0851116 (consistent with `topol.top`); note the slip.
   - D9: Tutorial 7 window count is internally inconsistent: the mdp comment
     says "29 windows (0..28)" over 0.2–3.0 nm, the text says "all 28
     windows", and `find_windows.py` uses `numpy.arange(0.2, 3.0, 0.1)` =
     **28 windows covering 0.2–2.9 nm**. Adopt the script (28 windows).
   - D10: Tutorials 4–5 FEP mdp files are **2018-era API** (`init_lambda_state`,
     `delta_lambda`) — the 2025 refresh did not modernize them. Modern
     equivalent: `init-lambda-state` (already in KB `03.2`); the lambda
     *vector values* are portable.

## Validation protocol

**Build access** (for fresh sessions): the gold-standard binary is the docker
image `gromacs-hip-gfx1100:latest` = GROMACS 2026.3-dev-20260625 (see
`issues_kb.md` header). Plain `docker run` works (the image's
`LD_LIBRARY_PATH` was fixed 2026-09-03):

```bash
docker run --rm -v /home/<user>/docker/genai_stack/gromacs/work:/work \
  gromacs-hip-gfx1100:latest gmx grompp -f /work/probe/em.mdp \
  -c /work/probe/spc216.gro -p /work/probe/box.top -o /work/probe/test.tpr
```

`gromacs/work/probe/` is an existing probe matrix (spc216.gro, box.gro/top,
`a1..wn3.mdp`) — reuse its coordinate/topology files; `work/smoketest.sh`
shows the full EM+NVT pattern. New probes: drop an `m*.mdp` into a fresh
`work/probe_<ticket>/` dir and grompp it.

- **V1 (MDP parse)**: run `gmx grompp` in the build with a minimal test
  system (pattern above). Acceptance: `unknown=invalid=obsolete=0` for the
  new block. Record the probe command + result in the ticket's resolution
  note.
- **V2 (CLI)**: verify every tool/flag claim with `gmx <tool> -h` in the
  build (and, where the claim is "flag X is gone", confirm absence).
- **V3 (science)**: cross-check formulas/values against (a) the repo's own
  worked examples (reproduce the arithmetic), and (b) the primary literature
  cited in the ticket. Record the reproduction.
- **V4 (consistency)**: all `→ file` cross-references resolve; README file
  map matches the directory (T-11).

## Status legend

`[ ] OPEN` · `[~] IN PROGRESS` · `[x] RESOLVED (YYYY-MM-DD)`

---

## Suggested order & dependencies

Cheap/low-risk first, grouped by target file to avoid edit conflicts;
reconstruction (T-01) and R&D (T-07) tickets later; housekeeping last.

| Order | Ticket | Target file(s) | Risk |
|-------|--------|----------------|------|
| 1 | T-08 | 01.8 | low |
| 2 | T-10 | 01.5, 01.8, 02.04 | low |
| 3 | T-02 | 02.04 | low |
| 4 | T-03 | 02.04 | low–med |
| 5 | T-05 | 00.6 | med |
| 6 | T-09 | 02.03, 03.2 | med |
| 7 | T-01 | 02.03 | med (reconstruction) |
| 8 | T-04 | 02.13 | med |
| 9 | T-06 | 02.15 (new) | low–med |
| 10 | T-07 | 02.16 (new) | **high (2026.3 R&D)** |
| 11 | T-11 | README.md | low |

---

## T-01 — Absolute binding free energy with Boresch-style orientation restraints

- **Status**: [x] RESOLVED (2026-09-15)
- **Target**: `02-md-types/02.03-alchemical-free-energy.md` — new section
  "Absolute binding free energy (Boresch-style restraints)"
- **Story**: As an agent asked for an *absolute* ΔG_bind of a ligand in a
  defined pose, I want the orientation-restraint workflow and the analytical
  end-point correction documented, so I can set up the complex leg with
  restraints, the solvent leg without, and combine them correctly.
- **Source**: repo Tutorial 6 (`gmx_tutorials.tex` §dgbind,
  `04-06_free_energy/06_complex/correct_restraints.py`) + Boresch,
  *J. Chem. Inf. Model.* 64(9):3605–3609 (2024) + the classical 5-restraint
  protocol (Boresch et al., *J. Phys. Chem. B* 107:9595–9607, 2003).
  **Note D7**: the repo section is incomplete — this ticket is a
  *reconstruction* from tex + script + literature; flag any choice the
  sources don't pin down.
- **Content spec** (what the section must contain):
  1. **When to use**: absolute binding free energy of a ligand held in a
     defined pose (vs. relative ΔΔG, which needs no restraints).
  2. **Restraint geometry**: 5 restraints on the ligand — 1 distance,
     2 angles, 2 dihedrals (Boresch convention). Typical force constants from
     the repo example: k_r = 500 kJ mol⁻¹ nm⁻², k_θ = k_φ =
     500 kJ mol⁻¹ rad⁻². Restraint atoms/sites: heavy-atom triplets of the
     ligand + one protein atom (the repo's §dgbind_vsites section shows
     virtual sites as a way to get stable reference triplets — mention the
     concept, cite Tutorial 9; do not require vsites).
  3. **Topology implementation**: ligand `.itp` sections
     `[ distance_restraints ]`, `[ angle_restraints ]`, `[ dihedral_restraints ]`;
     restraints are **scaled by `restraint-lambdas`** (fully on at λ=0, off
     at λ=1) — never deleted mid-calculation. Complex leg:
     `restraint_lambdas = 1 1 ... 0 0` across the λ vector. Solvent leg: no
     restraints at all.
  4. **Correction formula** (end-point, applied once):
     `ΔG_restraint = −k_BT·ln[ (2πV°/(r₀²·sinθ_A·sinθ_B)) ·
     (k_r·k_θA·k_θB·k_φA·k_φB/(2πk_BT)⁵)^½ ]`, with V° = 1.66054 nm³
     (1 M standard state), k_BT = 2.4789 kJ/mol at 298.15 K.
  5. **Cycle**: `ΔG_bind = ΔG_complex − ΔG_solv + ΔG_restraint`.
     ΔG_solv = full decoupling in solvent (per T-09). ΔG_complex =
     decoupling of the restrained complex.
  6. **Pitfalls**: restraints must be λ-scaled (not removed); the correction
     is an end-point correction (state function — apply at the final state
     only, with full B-state force constants); restraint geometry must match
     the bound pose; standard-state volume convention (1 M); do not confuse
     interaction energy with binding free energy.
- **Implementation steps**:
  1. Draft the section per the content spec (KB style: when-to-use → setup →
     MDP deltas → analysis → pitfalls).
  2. Build a minimal test: a restrained ligand `.itp` (5 restraints) +
     `restraint_lambdas` in an FEP mdp; verify grompp accepts it.
  3. Add provenance line (repo) + Boresch 2024/2003 citations.
- **Validation**:
  - V3: reproduce the repo's worked example: r₀ = 0.53 nm, θ_A = 95.57°,
    θ_B = 74.45°, all k = 500, T = 298.15 K → expect **−30.5631 kJ/mol**
    (−7.3048 kcal/mol) (note D2: use r₀ = 0.53, ignore the stale comment).
    Cross-check the formula structure against Boresch 2024.
  - V1: FEP mdp with `restraint_lambdas` + a test `.itp` containing the three
    restraint sections parses clean in the build.
  - V2: confirm restraint-section syntax (funct column) via grompp behavior.
- **Acceptance**: section present; arithmetic reproduced; MDP verified;
  provenance + citations in place.

- **Resolution (2026-09-15)**: Added "Absolute binding free energy
  (Boresch-style restraints)" to `02.03` (when-to-use; 5-restraint geometry
  1 dist + 2 angles + 2 dihedrals with k_r = k_θ = k_φ = 500; topology via
  `restraint-lambdas` scaling — complex leg `1 1 … 0 0`, solvent leg none;
  end-point correction formula with V° = 1.66054 nm³, k_BT = 2.4789 kJ/mol;
  cycle ΔG_bind = ΔG_complex − ΔG_solv + ΔG_restraint; pitfalls). **V3**:
  reproduced the repo worked example exactly — `06_complex/correct_restraints.py`
  prints **−30.5631 kJ/mol (−7.3048 kcal/mol)** for r0 = 0.53, θA = 95.57°,
  θB = 74.45°, all k = 500, T = 298.15 K (sensitivity check: stale 0.40 nm
  comment gives −31.9584, confirming r0 = 0.53 per D2). **V1/V2**: 5-restraint
  ligand `.itp` + FEP mdp with `restraint-lambdas` parses clean in 2026.3
  (`work/probe_t01/`, grompp exit 0). **New 2026.3 findings** (verified vs
  build): `[ angle_restraints ]` now takes **4 atom indices** (`ai aj ak al
  funct θ0 kc mult`, was 3); `[ dihedral_restraints ]` is `ai aj ak al funct
  φ0 Δφ k_dihr` (new Δφ column); the classic `[ distance_restraints ]` r0/fc
  form is **gone** — now NMR-style (`ai aj funct type label low up1 up2
  weight`, needs `disre = yes`); a simple harmonic distance restraint is
  `[ bonds ]` funct = 6 (r0, fc). Provenance + Boresch 2003/2024 citations
  added; D7 reconstruction caveats flagged (repo §dgbind incomplete — ZFUR
  restraint atom triplets not pinned down).

---

## T-02 — PMF volume-entropy correction

- **Status**: [x] RESOLVED (2026-09-15)
- **Target**: `02-md-types/02.04-pmf-umbrella.md` — extend the
  "Entropic effects" section
- **Story**: As an agent reporting a PMF for a 3-D distance RC, I want the
  spherical volume-entropy correction and the bulk-plateau convention, so my
  PMF values are physically meaningful (not off by the Jacobian term).
- **Source**: repo Tutorial 7 (`gmx_tutorials.tex` §pmf,
  `07_umbrella/correct_pmf.py`) + Ghosh, Uddin & Choi, *J. Phys. Chem. B*
  116:14254–14260 (2012) (reference system: methanol pair in water).
- **Content spec**:
  1. Formula: `ω(r) = ω_WHAM(r) + 2·k_B·T·ln(r)` — applies to **3-D COM
     distance RCs** (spherical symmetry: the 1-D histogram misses the
     4πr² Jacobian; the constant is absorbed in the baseline).
     **Does NOT apply** to dihedral/angle RCs.
  2. **Bulk-plateau shift**: after correction, subtract the mean of the
     plateau (r ≥ bulk cutoff — repo uses 2.0 nm) so the non-interacting
     limit is 0 kJ/mol.
  3. **WHAM zero-point convention**: `gmx wham` sets the leftmost window to
     0; shifting the whole curve is a systematic translation — ΔG values are
     unchanged.
  4. Note D1: the repo *text* says "2 k_BT ln(4)" — a typo; the equation and
     the script both use ln(r). Adopt ln(r).
- **Implementation steps**: extend the section; include a 3-line worked
  example (e.g. r = 0.5 nm, T = 298.15 K → correction = 2·kB·T·ln(0.5) =
  4.9578 × (−0.6931) ≈ **−3.44 kJ/mol**).
- **Validation**:
  - V3: reproduce `correct_pmf.py`'s arithmetic on a synthetic 2-column xvg
    (correction column = 2·kB·T·ln(r), bulk shift applied).
  - V4: cross-reference to T-03 window workflow.
- **Acceptance**: formula + applicability conditions + worked example present;
  arithmetic reproduced; provenance in place.

---

## T-03 — Umbrella window-generation workflow (SMD → windows → production)

- **Status**: [x] RESOLVED (2026-09-15)
- **Target**: `02-md-types/02.04-pmf-umbrella.md` — new section
  "Generating window starting configurations"
- **Story**: As an agent setting up umbrella sampling, I want a concrete
  recipe for producing the starting configuration of each window, so I don't
  have to invent the SMD + frame-extraction dance.
- **Source**: repo Tutorial 7 (`gmx_tutorials.tex` §pmf, `07_umbrella/`:
  `md_pull.mdp`, `md_umbrella.mdp`, `find_windows.py`, `get_distances.sh`,
  `setup-umbrella-script.tar.gz` — a tarball containing `run-umbrella.sh` +
  `setupUmbrella.py`) + Hub, de Groot & van der Spoel, *J. Chem. Theory
  Comput.* 6:3713–3720 (2010).
- **Content spec**:
  1. **SMD pull** to generate an RC trajectory: `pull-coord1-type = umbrella`
     (harmonic bias; the name is a synonym for the harmonic potential, not
     umbrella sampling), `geometry = distance`, `dim = N N Y` (repo: z-axis
     only; set per RC), `start = yes`, `rate = 0.01` nm/ps (= 10 nm/ns),
     `k = 1000` kJ mol⁻¹ nm⁻².
     **Rationale**: the spring rate is NOT the observed displacement — the
     spring builds force until restoring forces are overcome (check
     `pull_pullf.xvg` spring force and `pull_pullx.xvg` RC time series).
  2. **RC time series** (`get_distances.sh` pattern — `gmx distance` takes a
     *single structure*, not a trajectory): split the pull trajectory
     (`gmx trjconv -s pull.tpr -f pull.xtc -o conf.gro -sep` → 501 frames),
     then per frame:
     `gmx distance -s pull.tpr -f conf${i}.gro -n index.ndx -select 'com of group "Chain_A" plus com of group "Chain_B"' -oall dist${i}.xvg`
     (single quotes around the selection, double quotes around index-group
     names); compile frame→distance summary. **V2 probe**: check whether
     2026.3 `gmx distance` accepts a trajectory directly — if so, document
     the simpler one-shot form instead.
  3. **Window extraction**: for each target ξ (repo: **28 windows over
     0.2–2.9 nm**, Δξ = 0.1 nm — see D9 for the source's 28-vs-29
     inconsistency), pick the frame minimizing |d − ξ|; write it with
     `gmx trjconv -dump <t>`. (Algorithm = `find_windows.py`; document, don't
     copy.)
  4. **Per window**: short NPT equilibration (100 ps) under the umbrella
     anchored at the window's starting COM distance (`pull-coord1-start =
     yes`, `rate = 0`, `k = 1000`, `dim = N N Y` — the starting configuration
     was extracted at ξ, so `start = yes` places the umbrella at ξ), then
     production (repo: 10 ns).
  5. **Box-size rule**: the minimum-image convention must hold at the
     **maximum** RC value, not just the initial configuration (repo:
     dodecahedron 6.5 nm vectors for a 3.0 nm maximum COM distance).
  6. **Window spacing**: Δξ ≈ 0.1 nm typical; neighboring windows must
     overlap (WHAM validity — already in 02.04 pitfalls).
- **Implementation steps**:
  1. Draft the section with the two MDP blocks (SMD, umbrella window)
     **adapted to KB conventions** (v-rescale, h-bonds, no `ns_type`, no
     `fourier_nx/ny/nz`/`optimize_fft` unless they probe clean — note D4).
  2. Add provenance line.
- **Validation**:
  - V1: both MDP blocks parse clean (probe `optimize_fft`, `fourier_nx/ny/nz`
     separately; drop if unknown).
  - V2: `gmx distance -h` (selection language incl. `com of group ... plus`;
     trajectory vs single-structure input), `gmx trjconv -dump`/`-sep`,
     `gmx make_ndx` group naming.
  - V3: cross-check workflow order/values against the repo.
- **Acceptance**: section present with both verified MDP blocks; CLI claims
  verified; provenance in place.

---

## T-04 — Membrane-protein construction (iterative lipid packing)

- **Status**: [x] RESOLVED (2026-09-15)
- **Target**: `02-md-types/02.13-membranes.md` — new section "Building a
  membrane around a protein (iterative lipid packing)"
- **Story**: As an agent building a membrane-protein system, I want the full
  embedding + packing + equilibration recipe (the current file only says
  "manual or tools"), so I can produce a clash-free, equilibrated bilayer
  around a transmembrane protein.
- **Source**: repo Tutorial 2 (`gmx_tutorials.tex` §kalp,
  `02_membrane_protein/`: `inflategro.pl`, `water_deletor.pl`, mdp files) +
  Kandt, Ash & Tieleman, *Methods* 41:475–488 (2007) (InflateGRO) + Berger
  et al., *Biophys. J.* 72:2002–2013 (1997) (DPPC parameters) +
  Kandasamy & Larson (2006) (KALP₁₅ hydrophobic mismatch).
- **Content spec**:
  1. **Prerequisites**: protein helix axis aligned to z (`editconf -princ`
     aligns the longest axis to x; rotate 90° about y); a pre-equilibrated
     bilayer coordinate file; lipid FF matched to the protein FF/water
     (repo uses Berger + GROMOS53A6 for pedagogy — **state that production
     should use a modern matched set**, e.g. CHARMM36 lipids + TIP3P; the
     workflow is FF-agnostic).
  2. **InflateGRO cycle** (document the algorithm; cite Kandt 2007; do not
     copy the script):
     - inflate bilayer in xy by factor **4** (scaling > 1);
     - delete lipids with P–CA distance < **14 Å** (deletion only during
       inflation; set cutoff 0 for all shrinking steps);
     - EM with **strong protein posre** (`genrestr -fc 100000 100000 100000`,
       invoked via a second `#ifdef` block, e.g. `-DSTRONG_POSRES`);
     - rebuild broken lipids: `gmx trjconv -pbc mol` (write to a temp file —
       trjconv refuses in-place read+write);
     - shrink by **0.95**, EM, repeat — repo: **26 rounds** for KALP₁₅/DPPC;
     - stop at APL ≈ **71 Å²** (InflateGRO overestimates APL; experimental
       fluid DPPC ≈ 62 Å² — do not chase the exact experimental value).
  3. **Solvation**: `gmx solvate` (water will enter core voids), then delete
     core water: algorithm of `water_deletor.pl` (document; GPL — don't copy):
     reference atom = ester-region O (O33 in DPPC), middle atom = bilayer
     center (C50), delete waters whose OW falls between the two leaflet
     boundaries; `-nwater 3` for 3-site water.
  4. **Ions + EM**: standard `genion -neutral` (choose SOL group), standard
     EM.
  5. **NVT**: merged thermostat group `Protein_DPPC` (make_ndx `1 | 13`) +
     `Water_and_ions`; **rationale**: lipids and water diffuse on different
     timescales — one group would give spurious velocity scaling;
     `tau_t = 0.1` (NVT) / `0.5` (NPT); **T above the lipid T_m** (DPPC
     T_m ≈ 315 K → run 323 K; liquid-crystalline state; check FF-specific
     T_m error).
  6. **NPT**: `pcoupltype = semiisotropic` (xy vs z); KB recommends
     `C-rescale` (repo uses Parrinello-Rahman — note both, prefer KB
     convention); per-group COM removal: `comm-grps = Protein_DPPC
     Water_and_ions`, `comm-mode = Linear`, `nstcomm = 1`.
  7. **Production & convergence**: 1 ns is demo-only; **50–100 ns** typical
     for converged APL/box vectors; monitor Box-X/Box-Y time series and APL.
  8. **Analysis nuggets** (from assessment item 10, membrane part):
     - deuterium order parameter plateau ≈ 0.2 (carbons 4–8) =
       liquid-crystalline DPPC;
     - APL = (Box-X × Box-Y) / lipids per leaflet (pure membrane); for
       protein-containing systems use a grid method (GridMAT-MD) since the
       protein occupies lateral area;
     - lateral diffusion from `gmx msd -lateral z` is a **finite-size
       quantity D_PBC, not D_0** — Yeh & Hummer correction
       (*J. Phys. Chem. B* 108:15873–15879, 2004) for the infinite-system
       value.
- **Implementation steps**:
  1. Draft the section (KB style) with the strong-posre `#ifdef` pattern and
     the two mdp deltas (NVT groups, NPT semiisotropic + comm-grps).
  2. Add provenance line + citations (Kandt 2007, Berger 1997, Yeh 2004,
     Kandasamy 2006).
- **Validation**:
  - V1: mdp blocks (merged tc-grps, comm-grps, semiisotropic 2-value
     compressibility/ref-p) parse clean; `define = -DSTRONG_POSRES` +
     double-`#ifdef` topology pattern grompp-verified.
  - V2: `genrestr -fc`, `editconf -princ`, `trjconv -pbc mol -ur compact`,
     make_ndx merge syntax (`1 | 13`).
  - V3: T_m(DPPC) ≈ 315 K, APL(fluid DPPC) ≈ 62 Å², SCD plateau ≈ 0.2 —
     cross-check against the cited literature; InflateGRO parameters against
     Kandt 2007 / repo.
  - Optional (if time): short EM of a packed test system converges.
- **Acceptance**: section present; all values literature-checked; MDP
  verified; provenance in place.

- **Resolution (2026-09-15)**: Added "Building a membrane around a protein
  (iterative lipid packing)" to `02.13` (prerequisites: helix→z via `editconf
  -princ` + 90° y-rotation, pre-equilibrated bilayer, FF match; InflateGRO
  cycle: inflate xy ×4, delete P–CA < 14 Å only during inflation, strong posre
  EM via `genrestr -fc 100000` + second `#ifdef STRONG_POSRES` block, rebuild
  broken lipids `trjconv -pbc mol` to a temp file, shrink 0.95, 26 rounds,
  stop at APL ≈ 71 Å²; solvation + core-water deletion algorithm; ions + EM;
  NVT merged `Protein_DPPC`/`Water_and_ions` groups + rationale + tau-t + T >
  T_m; NPT `semiisotropic` + C-rescale + per-group comm-grps; 50–100 ns
  production; analysis nuggets SCD ≈ 0.2, APL, Yeh–Hummer D_PBC). **V1**:
  mdp blocks (merged tc-grps, comm-grps, semiisotropic 2-value
  compressibility/ref-p) + `define = -DSTRONG_POSRES` + double-`#ifdef`
  topology pattern parse clean in 2026.3 (`work/probe_t04/`, grompp exit 0,
  `npt.tpr` written; only harmless stub warnings). **V2**: `genrestr -fc`,
  `editconf -princ` (a `-[no]princ` flag), `trjconv -pbc mol -ur compact`,
  `msd -lateral z`, `order -d z`, make_ndx `1 | 13` merge all confirmed in
  2026.3. **V3**: T_m(DPPC) ≈ 315 K, APL(fluid DPPC) ≈ 62 Å², SCD plateau
  ≈ 0.2, InflateGRO params (×4 inflate, 14 Å cutoff, 0.95 shrink, 26 rounds,
  71 Å² stop) cross-checked vs repo §kalp + mdp files + cited literature. Provenance
  + Kandt 2007 / Berger 1997 / Yeh 2004 / Kandasamy 2006 citations added.

---

## T-05 — CGenFF ligand parameterization workflow

- **Status**: [x] RESOLVED (2026-09-15)
- **Target**: `00-foundations/00.6-force-fields-water.md` — expand the
  "Ligand / small-molecule parameterization" section (CHARMM/CGenFF route)
- **Story**: As an agent parameterizing a drug-like ligand for CHARMM, I want
  the complete CGenFF server workflow, quality metrics, and GROMACS topology
  integration rules, so the ligand `.itp` is correct on the first grompp.
- **Source**: repo Tutorial 3 (`gmx_tutorials.tex` §prot_lig,
  `03_complex/`: `jz4_UA_gromos54a7.itp`, `jz4.mol2`, `sort_mol2_bonds.pl`,
  `jz4.str`) + cgenff.com server docs.
- **Content spec**:
  1. **Input prep**: 3D structure (crystal ligand coordinates) → add
     hydrogens (Avogadro) → save `.mol2`; fix residue name (e.g. `JZ4`) and
     residue numbers for all atoms (incl. added H); **bonds must be in
     ascending numerical order** in `@<TRIPOS>BONDS` (sort step — CGenFF
     requirement; note D3 typo in repo text).
  2. **Server**: cgenff.com (free for academic use, registration required);
     upload the corrected mol2 → returns CHARMM stream file (`.str`) +
     GROMACS-format download.
  3. **Penalty-score interpretation** (quality gate):
     - **< 10**: reliable, use as-is;
     - **10–50**: validate (QM dihedral scans for bonded terms, QM water
       interactions for charges);
     - **> 50**: significant manual refinement/reparametrization required.
  4. **GROMACS integration** (server output needs surgery):
     - `jz4_fix_gmx.top` → `jz4_gmx.itp` (repo name; any name works);
     - remove the `#include "charmm36-feb2026_cgenff-5.0.ff/forcefield.itp"`
       line;
     - replace the `#include ".../jz4_ffbonded.itp"` with the file's
       *contents* (inline);
     - delete everything from `; Include water topology` to EOF;
     - rename `[moleculetype]` `Other` → ligand resname;
     - `posre.itp` → `posre_jz4.itp`.
  5. **System topology placement rules** (the subtle part):
     - ligand parameter file (`.prm`) must be `#include`d in `topol.top`
       **after** the force-field include (bonded parameters reference known
       atom types) and **before** any `[ moleculetype ]`;
     - `#include "jz4_gmx.itp"` in the topology body (after posre block);
     - append ligand coordinates to the system `.gro` (update atom count);
     - `[ molecules ]` += `JZ4 1`.
  6. **Ligand position restraints**: index group `0 & ! a H*` (heavy atoms) →
     `gmx genrestr -n index.ndx -fc 1000 1000 1000` → `posre_jz4.itp`
     (atom numbers are local 1..N, not global).
  7. **This build**: CHARMM36 is **not shipped** (only `charmm27`) — install
     the MacKerell-lab tarball (e.g. `charmm36-feb2026_cgenff-5.0.ff.tgz`)
     into `$GMXLIB` or the working dir; water `.itp` must be included from
     the FF directory (2026.3 rule, already in 00.6).
  8. **Validation of the result**: ligand heavy-atom RMSD vs the bound pose
     (plateau ≈ 0.15 nm over 10 ns = good; drift/dissociation ⇒ suspect
     topology); interaction-energy stability (→ T-08).
- **Implementation steps**: expand the section; add a compact worked-example
  checklist (numbered, like the repo's 5-step .itp surgery).
- **Validation**:
  - V3: cross-check every step against the repo (JZ4 example) and cgenff.com
    server documentation.
  - V1: a minimal test `.itp`/`.top` with the include structure (FF include →
    ligand `.prm` → `[moleculetype]`s) parses clean. Requires the CHARMM36
    tarball in the build; if unavailable, verify structurally (grompp with a
    stub FF dir) and flag the limitation in the resolution note.
  - V2: `genrestr -n` (index-file input) in the build.
- **Acceptance**: workflow + penalty table + placement rules present; test
  topology verified (or flagged); provenance in place.
- **Resolution (2026-09-15)**: expanded the "Ligand / small-molecule
  parameterization" section of `00.6` with a full CGenFF worked-example
  workflow (JZ4): input prep (mol2, resname, ascending bond sort + D3 typo
  note), server, penalty table (<10 / 10–50 / >50), 6-step `.itp` surgery,
  placement rules, `genrestr` restraints, this-build CHARMM36 note, and
  result validation. **New 2026.3 finding** (verified in build): top-level
  type-definition directives renamed `[bonds]`→`[bondtypes]`,
  `[angles]`→`[angletypes]`, `[dihedrals]`→`[dihedraltypes]`,
  `[pairs]`→`[pairtypes]`; `[system]` now required before `[molecules]`;
  `[defaults]` required before `[atomtypes]`. CGenFF GROMACS output (old
  directive names) needs the rename for this build — documented. V1: stub-FF
  test topology (`work/probe_t05/`) — correct include order (FF → ligand
  `.prm` → `[moleculetype]`) parses clean (grompp exit 0, `test.tpr` written);
  wrong order (`.prm` before FF) fails "Invalid order for directive bondtypes"
  (rule enforced). CHARMM36 tarball not in build → verified structurally with
  a stub `charmm36-feb2026_cgenff-5.0.ff/` dir (flagged per spec). V2:
  `genrestr -n <.ndx>` confirmed. Provenance in place.

---

## T-06 — Biphasic (water/oil) system construction

- **Status**: [x] RESOLVED (2026-09-15)
- **Target**: **new file** `02-md-types/02.15-biphasic-interfaces.md`
- **Story**: As an agent asked to simulate octanol/water partitioning or an
  interface, I want a construction recipe for two coexisting liquid phases,
  so I can build the system without water leaking into the hydrophobic phase.
- **Source**: repo Tutorial 8 (`gmx_tutorials.tex` §biphasic,
  `08_biphasic/`: `chx.gro`, `chx_10ns.gro`, `chx.top`) + Lemkul (2010)
  water–cyclohexane interface study.
- **Content spec**:
  1. **When to use**: solute partitioning (octanol/water as logP proxy),
     interface dynamics; note the simulation itself is standard MD — only
     construction differs (+ COM groups, → 02.13).
  2. **Pure-liquid box, method A — `insert-molecules`**: random insertion;
     `-nmol` is a *maximum* (not guaranteed); inspect the reported count;
     default vdW radii changed in GROMACS 5.0 (counts vary between versions);
     insertion is randomly seeded.
  3. **Pure-liquid box, method B — `genconf`**: perfect lattice (`-nbox 8 8 8`
     = 512 mols); highly artificial → much longer equilibration; needs a
     properly boxed input (or `-dist` vector).
  4. **Equilibrate the pure box first** (NVT + NPT; repo: 10 ns NPT at
     298 K) before using it as a building block.
  5. **Seat the oil box in a larger box**: `editconf -box <x y 2z> -center
     <cx cy cz>` where the center = geometric center of the original box
     (repo: 4.30795³ cube → 4.30795 × 4.30795 × 8.6159, center
     2.153975 2.153975 2.153975). Water added by `solvate` is continuous with
     the "bottom" via z-PBC — that is correct, not a bug.
  6. **Prevent water in the oil phase**: copy `vdwradii.dat` from `$GMXLIB`
     into the working dir, raise the C radius 0.17 → **0.35**, then
     `solvate`; a few stray waters may remain — expelled by short
     equilibration.
  7. **Place a solute in the oil phase**: `solvate -cs <oilbox.gro>` (the
     equilibrated oil box *is* the solvent template); place a solute in the
     aqueous phase by centering it at ¾ of the z-box length, then
     `solvate -cp solute -cs oilbox`.
  8. **Expand the oil layer**: `genconf -nbox 2 2 2` (cubic) or
     `-nbox 2 2 1` (tetragonal, xy only).
  9. **FF note**: repo's `chx.top` is GROMOS43A1/PRODRG (legacy,
     united-atom CH2 with zero charges); use a modern FF (OPLS/CHARMM
     cyclohexane or octanol) for production.
- **Implementation steps**: write the new file mirroring the section
  structure of an existing type file (e.g. `02.13-membranes.md`): when to
  use → prerequisite phases → setup → MDP deltas vs standard → analysis →
  pitfalls; add provenance line.
- **Validation**:
  - V2: `insert-molecules` flags (per KB I-10: `-f`, `-ci`, `-ip`, `-box`
    vector, `-nmol`, `-conc` — NOT `-s`/`-maxattempt`), `genconf -nbox`,
    `editconf -box -center`, `solvate -cs` (non-water box).
  - V3: cross-check the centering arithmetic and the vdwradii trick against
    the repo.
  - V4: cross-references to 01.3, 02.13.
- **Acceptance**: file created; CLI verified; provenance in place.

- **Resolution (2026-09-15)**: Created new file `02-md-types/02.15-biphasic-interfaces.md`
  (mirrors 02.13 structure: when-to-use → prerequisites → pure-liquid box
  methods A/B → equilibrate pure box → seat oil in larger box → prevent water
  in oil → place solute → expand oil layer → MDP deltas → analysis →
  pitfalls). Method A `insert-molecules` (`-nmol` is a maximum; vdW radii
  changed in GROMACS 5.0; random seed), Method B `genconf -nbox` (perfect
  lattice → longer equilibration), pure-box NVT+NPT (repo 10 ns NPT 298 K),
  `editconf -box 4.30795 4.30795 8.6159 -center 2.153975 2.153975 2.153975`
  (water PBC-continuous with bottom = correct), `vdwradii.dat` C-radius
  0.17→0.35 trick, solute placement (oil via `solvate -cs oilbox`; aqueous
  via center at ¾ z = 6.461925), `genconf -nbox 2 2 2`/`2 2 1` expansion,
  FF note (chx.top = legacy GROMOS43A1/PRODRG). **V2**: `insert-molecules`
  flags `-f/-ci/-ip/-box/-nmol/-conc` present, `-s`/`-maxattempt` gone (per
  KB I-10); `genconf -nbox/-dist`, `editconf -box/-center`, `solvate -cs/-cp`
  all confirmed in 2026.3. **V3**: centering arithmetic (4.30795/2 =
  2.153975; ×2 = 8.6159; ×0.75 = 6.461925) and vdwradii trick cross-checked
  vs repo §biphasic + `chx_10ns.gro` (4.30795³, 2796 atoms = 466 CHX). **V4**:
  xrefs to 01.3, 02.13, 01.8 in place. Provenance + Lemkul 2010 citation
  added.

---

## T-07 — Virtual sites (mass centers, linear molecules)

- **Status**: [x] RESOLVED (2026-09-15) — new file `02-md-types/02.16-virtual-sites.md` with a **build-verified** 2026.3 in-vacuo recipe (`pbc = xyz` + cutoff < L/2; `pbc = no`/`group` scheme removed; `comm-mode = angular` needs `-maxwarn`); MoI check reproduced (I_y = I_z = 0.5016 ≈ 0.500). **Highest-risk ticket closed.**
- **Target**: **new file** `02-md-types/02.16-virtual-sites.md`
- **Story**: As an agent asked to simulate a linear molecule (CO₂, N₂,
  CN⁻) or to use lone-pair/σ-hole sites, I want the virtual-site topology
  pattern with a validated gas-phase test, so the model is physically
  consistent (mass + moment of inertia preserved).
- **Source**: repo Tutorial 9 (`gmx_tutorials.tex` §vsite, `09_vsites/`:
  `topol.top`, `co2.pdb`, `em.mdp`, `md.mdp`) + Yang & Zhong, *J. Phys. Chem.
  B* 110:17776–17783 (2006) (CO₂ charges).
- **Content spec**:
  1. **Definition**: virtual site = no mass; may carry LJ/charge; forces
     project onto constructing atoms; position computed (not integrated).
     Terminology caveat: "dummy atom" is imprecise (may mean generic
     non-interacting particle).
  2. **Applications**: linear molecules (avoids the cos(θ) force
     discontinuity at 180°), lone pairs / σ-holes (OPLS3, CGenFF), Drude
     polarizable HB acceptors, H-mass repartitioning (4 fs steps).
  3. **CO₂ mass-center model** (the worked example):
     - two mass centers `MCO` (no LJ, no charge), each 22.0049 amu
       (½ × 44.0098);
     - preserve total mass AND moment of inertia: I = 2·m_O·L² =
       2 × 15.9994 × 0.125² = **0.500 amu·nm²** (C=O L = 0.125 nm);
     - diatomic rotor: L_MM = sqrt(I / (m_M·m_M/m_total)) = **0.213173 nm**;
     - `[ constraints ] 4 5 1 0.213173` (rigid, no force constant to guess);
     - `[ virtual_sites2 ]` funct 1 (linear): C at a = 0.5000 (midpoint);
       O at a = **1.0851116** beyond the M–M distance (repo value — see D8:
       the source's own equation (0.213173 + 0.0184135)/0.213173 actually
       evaluates to 1.086378, a 0.27 pm slip; adopt the repo value for
       consistency with `topol.top`); **order of constructing atoms sets
       direction** (O1: `4 5`, O3: `5 4`);
     - charges O −0.35 / C +0.70 (Yang & Zhong 2006) — **keep the repo's
       caveat**: educational model, not a validated FF.
  4. **Gas-phase validation**: 10 CO₂ in a 10 nm box, in vacuo, short MD;
     `gmx principal` per molecule → I_y = I_z = 0.500 amu·nm² (I_x = 0,
     axis coincides with the constraint) = model is physically consistent.
  5. **2026.3 R&D (the crux)**: the repo's in-vacuo recipe uses
     `cutoff-scheme = group` + `nstlist = 0` + `ns_type = simple` +
     `pbc = no` — **`group`/`ns` are removed in 2026.3** (Verlet only;
     "with Verlet lists only full pbc or pbc=xy with walls is supported").
     **Probe a working in-vacuo recipe in the build** (candidate matrix:
     `pbc = no` with Verlet; `pbc = xyz` + large box + `coulombtype = cutoff`
     with large/zero cutoffs; `pbc = xy` variants) and document what works,
     with the mdrun flags the repo uses (`-nt 1 -nb cpu` — group-scheme
     GPU limitation no longer applies; keep `-nb cpu` only if needed).
- **Implementation steps**:
  1. Run the probe matrix (V1) FIRST — the file's in-vacuo section depends
     on the result.
  2. Write the file with the CO₂ worked example + the verified in-vacuo MDP
     (mirror the section structure of `02.13-membranes.md`).
  3. Optional end-to-end: build the 10-CO₂ system, short gas-phase MD,
     `gmx principal` check (cheap: 50 particles).
  4. Add provenance line + Yang & Zhong 2006 citation.
- **Validation**:
  - V1: probe matrix results recorded; final in-vacuo MDP parses clean.
  - V3: moment-of-inertia arithmetic reproduced (0.500 amu·nm²;
     L_MM = 0.213173 nm; a = 1.0851116 as printed, 1.086378 as computed —
     per D8).
  - V2: `gmx principal` flags in the build.
- **Acceptance**: file created with a **build-verified** in-vacuo recipe;
  arithmetic reproduced; (ideally) end-to-end CO₂ check passed; provenance in
  place. If no in-vacuo recipe works in 2026.3, document the closest
  supported approximation and flag it as a build limitation.

---

## T-08 — Interaction-energy analysis (energygrps + mdrun -rerun)

- **Status**: [x] RESOLVED (2026-09-15)
- **Target**: `01-phases/01.8-analysis.md` — new section
  "Interaction energies between groups"
- **Story**: As an agent asked "how strongly does the ligand interact with
  the protein?", I want the energygrps + rerun recipe and its caveats, so I
  can report a meaningful number (and not over-interpret it).
- **Source**: repo Tutorial 3 (`gmx_tutorials.tex` §complex_analysis,
  `03_complex/ie.mdp`).
- **Content spec**:
  1. Add `energygrps = Protein JZ4` (any two groups) to a copy of the
     production mdp → new tpr via grompp →
     `gmx mdrun -deffnm ie -rerun traj.xtc -nb cpu`.
  2. **Multiple energy groups are not supported on GPU** → `-nb cpu` required.
  3. Extract `Coul-SR:A-B` and `LJ-SR:A-B` with `gmx energy`.
  4. **Caveats (must be stated)**: per-term decomposition has **no physical
     meaning** (FF-dependent); only the *total* interaction energy may be
     meaningful, and only if the FF was parametrized to make it so (e.g.
     CHARMM, which targets QM water interactions); this is **not** a binding
     energy or free energy of any kind — it is a potential-energy
     decomposition.
  5. Reference values (repo, JZ4/T4-lysozyme, 10 ns): Coul-SR
     −16.5 ± 10.0, LJ-SR −96.8 ± 7.4, total −113.3 ± 12.4 kJ/mol.
- **Implementation steps**: add the section (table + caveats); provenance
  line.
- **Validation**:
  - V1: mdp with `energygrps = A B` parses clean.
  - V2: `gmx mdrun -h` (`-rerun`, `-nb`).
  - V3: cross-check reference values against the repo.
- **Acceptance**: section present; MDP verified; caveats stated; provenance
  in place.

---

## T-09 — FEP practical setup (λ design, per-window workflow, benchmarks)

- **Status**: [x] RESOLVED (2026-09-15)
- **Target**: `02-md-types/02.03-alchemical-free-energy.md` (new "Practical
  window setup" section) + `03-playbooks/03.2-mdp-templates.md` (fep.mdp
  template additions)
- **Story**: As an agent running a decoupling calculation, I want concrete λ
  vector designs, per-window workflow, accuracy settings, and known-good
  benchmark values, so my setup is defensible without literature diving.
- **Source**: repo Tutorials 4–5 (`gmx_tutorials.tex` §vdw, §dgsolv,
  `04-06_free_energy/04_methane_water/` (mdp, `job.sh`, `write_mdp.pl`),
  `05_etoh_water/` (mdp, `write_mdp.txt`)) + Shirts et al., *J. Chem. Phys.*
  119:5740–5761 (2003) + Kelly, Cramer & Truhlar, *J. Chem. Theory Comput.*
  1:1133–1152 (2005) + Anisimov et al., *J. Chem. Theory Comput.*
  3:1927–1946 (2007).
- **Content spec**:
  1. **λ vector design** (worked examples from the repo):
     - vdW-only decoupling (methane): 21 windows, vdw_lambdas 0.00→1.00
       step 0.05, all other lambdas 0;
     - full decoupling (ethanol): **31 windows = 11 charge + 20 vdW**
       (coul_lambdas: 0.00, 0.10, …, 1.00 over the first 11 states, then
       1.00 × 20; vdw_lambdas: 0.00 × 11, then 0.05, 0.10, …, 1.00 over the
       last 20 states);
     - **decoupling order rationale**: charges off FIRST, then vdW —
       *never* scale vdW of atoms that still carry partial charge (repulsive
       LJ removal → charge collapse → numerical singularity);
     - clustering: equidistant 0.05 is a starting point; cluster vdW λ in
       **0.6–0.8** for strongly interacting / H-bonding molecules; Coulomb
       (linear in λ) usually tolerates equidistant 0.05–0.1.
  2. **Integrator**: `sd` (Langevin) for FEP windows with `tau-t = 1.0` ps
     (≥ 1.0 to avoid over-damping water and biasing sampling).
  3. **Per-window workflow**: EM (steep) → NVT 100 ps → NPT 100 ps →
     production (repo: 1 ns per window at tutorial scale; real work:
     10–100 ns × replicates); per-window directory layout; loop pattern —
     prefer `gmx mdrun -multidir` (2026.3) over hand-rolled loops (note D6:
     repo `job.sh` is 2018-era, do not copy).
  4. **Accuracy settings**: `pme-order = 6`, `ewald-rtol = 1e-6` for FEP
     (vs 4/1e-5 for regular MD); **DispCorr is FF-convention-dependent**:
     `No` for CHARMM (FFs fitted without it), `EnerPres` for OPLS/AMBER/GROMOS.
  5. **Analysis (2026.3)**: `gmx bar` from the `.edr` (legacy
     `-f md*.xvg` xvg API is gone — do NOT adopt); `calc-lambda-neighbors >
     1` + MBAR (pymbar) for all-windows reweighting.
  6. **Reference benchmarks** (validation values, with caveats):
     - methane vdW decoupling in TIP3P (OPLS): ΔG = 2.18 ± 0.02 kcal/mol vs
       Shirts et al. 2.21 ± 0.01 kcal/mol (TI);
     - ethanol ΔG_hydr: −17.8 ± 0.2 kJ/mol = −4.25 ± 0.05 kcal/mol (CGenFF
       topology) vs experimental −5.01 kcal/mol (Kelly 2005) and CHARMM22
       −5.34 ± 0.12 kcal/mol (Anisimov 2007) — deviation expected: CGenFF
       charges/LJ ≠ optimized model-compound parameters.
- **Implementation steps**:
  1. Add the "Practical window setup" section to 02.03 (include the 31-window
     λ vectors verbatim as a worked example; note D10 — the repo's mdp uses
     the legacy `init_lambda_state`/`delta_lambda` API, use the modern
     `init-lambda-state` from the `03.2` template).
  2. Extend the 03.2 fep.mdp template: `pme-order = 6`, `ewald-rtol = 1e-6`,
     DispCorr FF-convention comment, `sd`/`tau-t` note, 31-window vector
     example.
  3. Provenance lines in both files.
- **Validation**:
  - V1: extended fep.mdp template parses clean (incl. 31-element lambda
     vectors).
  - V2: `gmx bar -h` current API (cross-check against KB's existing claim).
  - V3: benchmark values cross-checked against the repo's printed results and
    the cited papers.
- **Acceptance**: both files updated; template verified; benchmarks cited;
  provenance in place.

- **Resolution (2026-09-15)**: Added "Practical window setup (worked
  examples)" to `02.03` (21-window vdW-only + 31-window full-decoupling λ
  vectors verbatim, charges-first decoupling-order rationale, 0.6–0.8 vdW
  clustering, `sd`/`tau-t ≥ 1.0`, per-window EM→NVT→NPT→prod workflow with
  `mdrun -multidir`, `pme-order 6`/`ewald-rtol 1e-6` + FF-convention DispCorr,
  `gmx bar -g *.edr` analysis, MBAR via `calc-lambda-neighbors > 1`, and the
  methane/ethanol benchmarks) and extended the `03.2` `fep.mdp` template
  (accuracy block, DispCorr FF-convention comment, `sd`/`tau-t` note,
  31-window pointer). Provenance added to both. **V1**: 31-window FEP mdp
  (11 charge + 20 vdW, all 2026.3 names incl. `sc-function`/`sc-r-power`,
  `dhdl-derivatives`, `pme-order 6`/`ewald-rtol 1e-6`, `sd`/`tau-t`) parses
  clean in 2026.3 (`work/probe_t09/`, grompp exit 0, `fep.tpr` written; only
  warning = stub net-charge, harmless). **V2**: `gmx bar -h` — current route
  is `-g <.edr>` (temp/λ deduced from `.edr`); legacy `-f dhdl.xvg` still
  present but deprecated (documented as "do not adopt"). **V3**: λ vectors and
  benchmarks cross-checked against repo `04_methane_water/md.mdp` (21-window,
  `DispCorr EnerPres`) and `05_etoh_water/md.mdp` (31-window, `DispCorr no`) +
  tex §vdw/§dgsolv printed results (methane 2.18 ± 0.02 kcal/mol; ethanol
  −17.8 ± 0.2 kJ/mol).

---

## T-10 — Scientific rationale nuggets (distributed)

- **Status**: [x] RESOLVED (2026-09-15)
- **Target**: `01-phases/01.5-equilibration.md`, `01-phases/01.8-analysis.md`,
  `02-md-types/02.04-pmf-umbrella.md`
- **Story**: As an agent advising on run quality, I want the repo's
  validation heuristics (pressure/density acceptance, RMSD caveats) in the
  KB, so my "is this run fine?" judgments match expert practice.
- **Source**: repo Tutorials 1 & 7 (`gmx_tutorials.tex` §lyso_equil,
  §lyso_ana, §umbrella_analysis).
- **Content spec** (each item = a short paragraph/bullet in the target file):
  1. → **01.5**: pressure is a wildly fluctuating microscopic quantity — an
     NPT average of e.g. −3 ± 11 bar vs target 1 bar is statistically
     indistinguishable from target; do not extend equilibration to chase the
     exact value.
  2. → **01.5**: density is the more robust NPT-convergence indicator (less
     noisy than pressure); a solvated-protein density slightly above pure
     water (repo: 1025 ± 0.5 vs 986 kg/m³ for TIP3P) is expected
     (protein + ions); constant density ⇒ adequately equilibrated.
  3. → **01.8**: RMSD is a **degenerate metric** — a plateau does NOT mean
     convergence (a structure can keep changing internally at constant
     RMSD); never terminate a simulation on RMSD alone.
  4. → **02.04**: WHAM zero-point convention: leftmost window = 0; shifting
     the curve is a systematic translation, ΔG unchanged. (T-10 runs before
     T-02 in the recommended order — add it here; T-02's implementer must
     not duplicate its item 3.)
  5. Verify (do not add if already present): minimum-image rationale in
     01.3; SMD rate-vs-displacement (→ T-03); membrane nuggets (→ T-04).
- **Implementation steps**: add the bullets in KB style; provenance line in
  each touched file.
- **Validation**: V3 (cross-check each number against the repo); V4
  (cross-references resolve; no duplication with T-02/T-03/T-04 content).
- **Acceptance**: all nuggets present exactly once; no duplication;
  provenance in place.

---

## T-11 — Housekeeping: README file map + central attribution section

- **Status**: [x] RESOLVED (2026-09-15) — README file map updated (added `02.15`/`02.16`, now 36 = 36 vs directory) + new "Sources & attribution" section (Lemkul LiveCoMS citation, adapted-not-copied + 2026.3 re-verification statement, pointer to per-file provenance). V4 grep check passes (all 9 files touched by T-01…T-10 carry provenance). **All 11 tickets closed.**
- **Target**: `README.md`
- **Story**: As a future maintainer, I want the README to reflect the new
  files and to carry the central attribution record, so provenance is
  discoverable in one place.
- **Source**: this ticket file + the resolved tickets.
- **Content spec**:
  1. File map: add `02.15-biphasic-interfaces.md` and
     `02.16-virtual-sites.md` (one-line descriptions matching the other
     entries).
  2. New section "Sources & attribution": the Lemkul LiveCoMS citation
     (title, author, journal, year, DOI, repo URL, CC BY 4.0), the statement
     that content is adapted (not copied) and re-verified against the
     2026.3 build, and a pointer to the per-file provenance lines.
  3. Do not otherwise restructure the README.
- **Implementation steps**: edit the file map; add the section.
- **Validation**: V4 (file map matches the directory listing; every KB file
  touched by T-01…T-10 carries a provenance line — grep check).
- **Acceptance**: map complete; attribution section present; grep check
  passes.

---

## Resolution log

| Ticket | Resolved | Probe/verification evidence (summary) |
|--------|----------|----------------------------------------|
| T-08   | 2026-09-15 | V1: `energygrps = G1 G2` (index groups via `grompp -n`) parses clean in 2026.3 (`work/probe_t08/m1.mdp` on probe box.gro/box.top; 0 unknown/invalid/obsolete). V2: `gmx mdrun -h` confirms `-rerun <traj>` and `-nb` (enum auto/cpu/gpu); manual: `energygrps` not supported on GPUs → `-nb cpu` required. V3: repo values (JZ4/T4-lysozyme, 10 ns, CHARMM) Coul-SR −16.5 ± 10.0, LJ-SR −96.8 ± 7.4, total −113.3 ± 12.4 kJ/mol — total = sum; combined SE √(10²+7.4²) = 12.44 ≈ 12.4 ✓. Section + provenance added to `01-phases/01.8-analysis.md`. |
| T-10   | 2026-09-15 | V3: pressure −3 ± 11 bar vs target 1 bar (target inside 1σ ✓); density 1025 ± 0.5 vs 986 kg/m³ TIP3P ✓ (repo text's "2.7% higher" is a slip — 1025.3/986 = 1.040; KB says "slightly above", slip not propagated); RMSD-degeneracy + WHAM zero-point text matches §lyso_ana/§umbrella_analysis. V4: each nugget present exactly once (01.5 pressure+density, 01.8 RMSD note + pitfall pointer, 02.04 WHAM zero-point in Analysis); 01.3 minimum-image rule already present (not re-added); SMD/membrane items left to T-03/T-04; provenance in 01.5 + 02.04 (01.8 carried over from T-08, same source). |
| T-02   | 2026-09-15 | V3: `correct_pmf.py` arithmetic reproduced on synthetic 2-col xvg (`work/probe_t02/`): 2·kB·T = 4.9579 kJ/mol @298.15 K; bulk shift = mean of corrected r ≥ 2.0 nm → plateau 4.9e-16 ≈ 0; worked example r = 0.5 nm → 4.9579 × (−0.6931) = −3.4366 ≈ −3.44 kJ/mol (identical with exact kB). D1 adopted (ln(r), not the text's ln(4)). V4: WHAM zero-point cross-referenced to Analysis (added by T-10, not duplicated); forward xref to T-03 "Generating window starting configurations". Section added to `02-md-types/02.04-pmf-umbrella.md` (provenance already present from T-10, same source). |
| T-03   | 2026-09-15 | V1: SMD block (m1) + umbrella-window block (m4) parse clean in 2026.3 (`work/probe_t03/`, KB conventions: v-rescale/h-bonds/C-rescale, no ns_type); `fourier_nx/ny/nz` still accepted (m2, omitted as unnecessary); `optimize_fft` obsolete/ignored (m3, dropped); `title` now obsolete (dropped). V2: `gmx distance -f` accepts a trajectory directly in 2026.3 (xtc/trr/cpt/gro/…) → one-shot form documented, per-frame `-sep` pattern noted as legacy; `trjconv -dump`/`-sep` present. V3: values cross-checked vs repo (SMD 500 ps, rate 0.01 nm/ps, k 1000, dim N N Y; 28 windows 0.2–2.9 nm per D9; per-window NPT 100 ps start=yes rate=0 k=1000; production 10 ns; dodecahedron 6.5 nm box for 3.0 nm max RC). tex/md_umbrella.mdp discrepancy (start=no+init vs start=yes) noted, mdp adopted. Section added to `02-md-types/02.04-pmf-umbrella.md`; T-02 forward xref now resolves (provenance already present). |
| T-05   | 2026-09-15 | V1: stub-FF test topology (`work/probe_t05/`) — correct include order (FF include → ligand `.prm` → `[moleculetype]`) parses clean in 2026.3 (grompp exit 0, `test.tpr` written); wrong order (`.prm` before FF) fails "Invalid order for directive bondtypes" (placement rule enforced). **New 2026.3 finding**: top-level type directives renamed `[bonds]`→`[bondtypes]`, `[angles]`→`[angletypes]`, `[dihedrals]`→`[dihedraltypes]`, `[pairs]`→`[pairtypes]`; `[system]` required before `[molecules]`; `[defaults]` before `[atomtypes]` (confirmed vs shipped `charmm27.ff` + source `topdirs.cpp`). CHARMM36 not in build → verified structurally with stub `charmm36-feb2026_cgenff-5.0.ff/` dir (flagged per spec). V2: `genrestr -n <.ndx>` confirmed. V3: every step cross-checked vs repo Tutorial 3 (JZ4 mol2/str/penalties, 6-step .itp surgery, placement rules, `genrestr -fc 1000 1000 1000`, RMSD 0.15 nm) + cgenff.com. Section + provenance added to `00-foundations/00.6-force-fields-water.md`. |
| T-09   | 2026-09-15 | V1: 31-window FEP mdp (11 charge + 20 vdW, all 2026.3 names incl. `sc-function`/`sc-r-power`, `dhdl-derivatives`, `pme-order 6`/`ewald-rtol 1e-6`, `sd`/`tau-t`) parses clean in 2026.3 (`work/probe_t09/`, grompp exit 0, `fep.tpr` written; only warning = stub net-charge, harmless). V2: `gmx bar -h` — current route is `-g <.edr>` (temp/λ deduced from `.edr`); legacy `-f dhdl.xvg` still present but deprecated (documented as "do not adopt"). V3: λ vectors and benchmarks cross-checked against repo `04_methane_water/md.mdp` (21-window, `DispCorr EnerPres`) and `05_etoh_water/md.mdp` (31-window, `DispCorr no`) + tex §vdw/§dgsolv printed results (methane 2.18 ± 0.02 kcal/mol; ethanol −17.8 ± 0.2 kJ/mol). "Practical window setup" section + provenance added to `02.03`; `fep.mdp` template extended + provenance added to `03.2`. |
| T-01   | 2026-09-15 | V3: reproduced repo worked example exactly — `06_complex/correct_restraints.py` prints **−30.5631 kJ/mol (−7.3048 kcal/mol)** for r0 = 0.53, θA = 95.57°, θB = 74.45°, all k = 500, T = 298.15 K (sensitivity: stale 0.40 nm comment → −31.9584, confirming r0 = 0.53 per D2). V1/V2: 5-restraint ligand `.itp` + FEP mdp with `restraint-lambdas` parses clean in 2026.3 (`work/probe_t01/`, grompp exit 0). **New 2026.3 findings**: `[ angle_restraints ]` now takes **4 atom indices** (`ai aj ak al funct θ0 kc mult`, was 3); `[ dihedral_restraints ]` = `ai aj ak al funct φ0 Δφ k_dihr` (new Δφ column); classic `[ distance_restraints ]` r0/fc form **gone** — now NMR-style (`ai aj funct type label low up1 up2 weight`, needs `disre = yes`); simple harmonic distance restraint = `[ bonds ]` funct = 6 (r0, fc). "Absolute binding free energy (Boresch-style restraints)" section + provenance + Boresch 2003/2024 citations added to `02.03`; D7 reconstruction caveats flagged. |
| T-04   | 2026-09-15 | V1: mdp blocks (merged tc-grps, comm-grps, semiisotropic 2-value compressibility/ref-p) + `define = -DSTRONG_POSRES` + double-`#ifdef` topology pattern parse clean in 2026.3 (`work/probe_t04/`, grompp exit 0, `npt.tpr` written; only harmless stub warnings). V2: `genrestr -fc`, `editconf -princ` (a `-[no]princ` flag), `trjconv -pbc mol -ur compact`, `msd -lateral z`, `order -d z`, make_ndx `1 | 13` merge all confirmed in 2026.3. V3: T_m(DPPC) ≈ 315 K, APL(fluid DPPC) ≈ 62 Å², SCD plateau ≈ 0.2, InflateGRO params (×4 inflate, 14 Å cutoff, 0.95 shrink, 26 rounds, 71 Å² stop) cross-checked vs repo §kalp + mdp files + cited literature. "Building a membrane around a protein (iterative lipid packing)" section + provenance + Kandt 2007 / Berger 1997 / Yeh 2004 / Kandasamy 2006 citations added to `02.13`. |
| T-06   | 2026-09-15 | Created new file `02-md-types/02.15-biphasic-interfaces.md` (mirrors 02.13 structure). V2: `insert-molecules` flags `-f/-ci/-ip/-box/-nmol/-conc` present, `-s`/`-maxattempt` gone (per KB I-10); `genconf -nbox/-dist`, `editconf -box/-center`, `solvate -cs/-cp` all confirmed in 2026.3. V3: centering arithmetic (4.30795/2 = 2.153975; ×2 = 8.6159; ×0.75 = 6.461925) and vdwradii C-radius 0.17→0.35 trick cross-checked vs repo §biphasic + `chx_10ns.gro` (4.30795³, 2796 atoms = 466 CHX). V4: xrefs to 01.3, 02.13, 01.8 in place. Provenance + Lemkul 2010 citation added. |
| T-07   | 2026-09-15 | Created new file `02-md-types/02.16-virtual-sites.md` (mirrors 02.13 structure). **V1 (the crux) — 2026.3 in-vacuo probe matrix** (`work/probe_t07/`, 10 CO₂ / 10 nm box): `cutoff-scheme = group` → **FAIL** ("removed since GROMACS 2020"); `pbc = no` (Verlet) → **FAIL** ("only full pbc or pbc=xy with walls"); `rcoulomb = rvdw = 0` → **FAIL** ("at least one cutoff radius > 0"); `pbc = xy` no walls → **FAIL**; `pbc = xyz` + cutoff 100 → **FAIL** ("> half the shortest box vector"); **`pbc = xyz` + `rcoulomb = rvdw = 4.5` → PASS** (grompp + mdrun EM clean). Threshold ≈ 4.75 nm for a 10 nm box (4.5/4.6/4.7 pass, 4.8/4.9 fail). `comm-mode = angular` in a periodic box raises a warning that **fails grompp by default** → `-maxwarn 2`. **V3**: MoI arithmetic reproduced exactly (I = 2·m_O·L² = 0.49998125; L_MM = 0.213173 nm; a = 1.0851116 as printed vs 1.086378 computed, 0.27 pm slip per D8 — repo value adopted). **V2**: `gmx principal` flags `-s/-f/-n/-om`/`-a1..a3` confirmed (no `-o`); end-to-end `gmx principal` on one CO₂ → I₁ ≈ 0, I₂ = I₃ = **0.5016 amu·nm²** (expected 0.500; 0.3% = PDB rounding of M1–M2 to 0.2132 nm) = model physically consistent. **MD instability** documented as a model limitation (C–O virtual-site pair in the OPLS LJ repulsive wall, no bonded exclusions → M1–M2 constraint breaks; same under the old infinite-cutoff recipe, not a 2026.3 regression). Provenance + Yang & Zhong 2006 citation added. |
| T-11   | 2026-09-15 | `README.md` housekeeping. V4: (1) file map now matches the directory listing exactly — **36 map entries = 36 KB files** (added `02.15-biphasic-interfaces.md` "water/oil boxes, insert-molecules, vdwradii trick" and `02.16-virtual-sites.md` "mass centers, linear molecules, in-vacuo MoI"); (2) every KB file touched by T-01…T-10 carries a provenance line (9/9: 00.6, 01.5, 01.8, 02.03, 02.04, 02.13, 02.15, 02.16, 03.2). New "Sources & attribution" section added after the file map: Lemkul LiveCoMS citation (title/author/journal/year/DOI/repo URL/CC BY 4.0), adapted-not-copied + 2026.3 re-verification statement, pointer to per-file provenance lines. No other README restructuring. |
