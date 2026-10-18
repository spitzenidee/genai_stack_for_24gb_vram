# KB Issues — GROMACS 2026.3 validation

**Gold standard:** actual build `gromacs-hip-gfx1100:latest` = **GROMACS 2026.3-dev-20260625**
(TNG on, Colvars on, CP2K **off**, Torch **off**, Plumed on, GPU=HIP, SIMD=AVX2_256, VkFFT 1.3.1, 101 commands).
Every item below was verified against that binary (grompp / tool CLI), not just the docs.
Note: `manual.gromacs.org/current` is **newer** than this build; where they disagree, the build wins.

**Status per issue:** each is a candidate for a reviewer to confirm in depth. `Files:` = KB paths affected (relative to `knowledge/`).

Severity: **[H]** breaks a workflow / wrong result · **[M]** stale name, needs update · **[L]** cosmetic / doc-only.

---

## Resolution status (2026-09-04 — KB fixes applied & re-verified against the build)

**All 33 issues are now closed.** Every KB file listed under each issue was edited to match the
`2026.3-dev-20260625` build, and the edited MDP blocks were re-verified by running `gmx grompp`
inside `gromacs-hip-gfx1100:latest` (see the `probe9` test matrix). Statuses below are updated
to `✅ RESOLVED (2026-09-04)`. New findings made during the fix pass are noted inline:

- **`sd`/`bd` require `tc-grps` + `ref-t` + `tau-t`** (all same count; `tc-grps` must cover all
  atoms) even though `tcoupl` is ignored — otherwise `grompp` aborts. Documented in `02.08` / `03.2`.
- **`wall-type` enum is `9-3`/`10-4`/`12-6`/`table`** (not `cubic`/`cylinder`/`dodecahedron`).
- **`awh-nstout` must be a multiple of `nstenergy`**; **`nstexpanded` should be a multiple of
  `nstcalcenergy`** (else grompp warns/adjusts).
- **`lincs-iter`/`lincs-warnangle` are the NEW names** (old `lincs-itmax`/`lincs-warnstep` gone) —
  an earlier draft of the fix had this backwards; corrected in `00.5`.
- **`rotation = yes` + `rot-*`** is the enforced-rotation API (the `enforced-rotation` block name
  is wrong) — corrected in `00.5`.
- Stragglers fixed on the final pass: `02.14` `gmx dipole`→`dipoles`, `02.13` `gmx solvation`
  →`gmx spatial`.
- **`cutoff-scheme` is `Verlet`-only** in 2026.3 — `grid` and `group` are removed ("The group
  cutoff scheme has been removed since GROMACS 2020"), and the old `ns` option is gone. Corrected
  in `00.5`.
- **Walls need `nwall` (explicit 0/1/2)**; with `cutoff-scheme = Verlet` a pbc=xy wall box must
  have **`nwall = 2`** (else "With Verlet lists only full pbc or pbc=xy with walls is supported").
  `wall-atomtype`/`wall-density` each need `nwall` values, and the wall atom type must be defined
  in the topology. Documented in `00.5` / `02.14`.
- **QMMM-CP2K module options are valid** and `grompp` reports "QMMM Interface with CP2K is
  active" (it marks the QM atoms and modifies the topology). **However** the build reports
  `CP2K support: disabled`, so an actual QMMM-CP2K `mdrun` would fail (no CP2K library linked).
  The KB (`02.10`) documents the module API and notes it needs a CP2K-enabled build.

---

## Verification status (2026-09-02, second audit vs build `2026.3-dev-20260625`)

All items below were re-verified by actually running `gmx <tool> -h` and `gmx grompp` with the old/new option names inside `gromacs-hip-gfx1100:latest`, plus cross-checks against `manual.gromacs.org/current`.

**Result: 30 of 32 issues confirmed real.** Three items needed correction (already applied in place):
- **I-15** — bug is real, but the original fix text was wrong (`dump` *has* `-s` for `.tpr`). Corrected below.
- **I-17** — **FALSE POSITIVE.** Old `awh1-dim1-*` options still work in this build; only new `coord-provider`/`coord-index` options were added. Downgraded [H]→[L]. Do NOT rewrite the AWH template's `awh1-dim1-force-constant`.
- **I-23** — enum claims confirmed, but the original reasoning had a factual error: MTTK requires `integrator = md-vv` (Velocity-Verlet), not `md`. Corrected below.

Additionally one finding **outside the KB** was verified and added as **I-33** (Dockerfile `LD_LIBRARY_PATH` bug).

Verified-OK / no-change tools (do not touch): `convert-tpr`, `energy`, `genrestr`, `gyrate`, `make_ndx`, `msd`, `pdb2gmx`, `rdf`, `rmsf`, `rms`, `order`, `sasa`, `density`, `pairdist`, `bar`, `trjcat`, `trjconv`, `editconf -bt`, `solvate -cs cubic`. Bonus: `hbond-legacy` and `gyrate-legacy` exist in this build and can serve as fallback references.

---

## 1. Tools — renamed or removed

### I-01 `gmx g_wham` → `gmx wham` (new API)  [H]  ✅ RESOLVED (2026-09-04)
Files: `00-foundations/00.2-command-surface.md`, `00.5-mdp-anatomy.md`, `01-phases/01.8-analysis.md`, `02-md-types/02.03-alchemical-free-energy.md`, `02.04-pmf-umbrella.md`, `03-playbooks/03.1-decision-trees.md`
`g_wham` does not exist. Build has `gmx wham` with a new API: `-ix -if -it -is -iiact -tab -o -bins -temp -tol -zprof0 -cycl -sym -ac` (+ bootstrap opts). Old `wham -f dhdl.xvg` form is gone.

### I-02 `gmx benchmark` → `gmx nonbonded-benchmark`  [H]  ✅ RESOLVED (2026-09-04)
Files: `00-foundations/00.1-versions-install.md`, `01-phases/01.7-restart-parallelization.md`, `03-playbooks/03.5-performance.md`
`gmx benchmark` does not exist. Build has `nonbonded-benchmark` with new API: `-o .csv -size -nt -simd -coulomb -iter -warmup`. Old `-s run.tpr -nsteps N` is invalid.

### I-03 `gmx dipole` → `gmx dipoles`  [M]  ✅ RESOLVED (2026-09-04)
Files: `00-foundations/00.2-command-surface.md`, `00.4-topology-anatomy.md`, `01-phases/01.8-analysis.md`, `02-md-types/02.14-specialized.md`
Tool is `dipoles` (plural). `gmx dipole` is an unknown command.

### I-04 `do_*` aliases removed  [M]  ✅ RESOLVED (2026-09-04)
Files: `00-foundations/00.2-command-surface.md`
00.2 line 73 claims "do_* aliases exist for most analysis tools (e.g. `gmx do_rms` ≡ `gmx rms`)". False in 2026.3 — `gmx do_rms` is an unknown command. Remove the alias claim.

### I-05 `gmx solvation` (analysis) removed  [M]  ✅ RESOLVED (2026-09-04)
Files: `01-phases/01.8-analysis.md`, `02-md-types/02.13-membranes.md`
KB uses `gmx solvation` for solvation-density analysis. That tool is gone; `gmx solvate` is a different (box-generation) tool and cannot do density analysis.

### I-06 Removed analysis tools still listed  [M]  ✅ RESOLVED (2026-09-04)
Files: `00-foundations/00.2-command-surface.md`, `01-phases/01.8-analysis.md`, `README.md`
These are unknown commands in the build but appear in the KB: `gmx add`, `axias`, `rotinv`, `pmx`, `pmat`, `nmat`, `fit`, `analysis`, `sander`. 01.8's analysis table lists `nmat`, `pmat`, `rotinv`, `axias`, `fit` as available.

### I-07 `gmx insert` → `gmx insert-molecules`  [M]  ✅ RESOLVED (2026-09-04)
Files: `01-phases/01.3-solvation-ions-box.md`
`gmx insert` does not exist; the tool is `insert-molecules` (see also I-11 for its flags).

---

## 2. Tool CLIs — broken flags

### I-08 `gmx solvate` — `-f` removed  [H]  ✅ RESOLVED (2026-09-04)
Files: `01-phases/01.3-solvation-ions-box.md`, `00.2-command-surface.md`, `00.3-file-formats-dataflow.md`, `00.6-force-fields-water.md`, `01.4-energy-minimization.md`, `03-playbooks/03.3-checklists.md`, `README.md`
KB: `gmx solvate -f protein.gro -o solvated.gro -cs cubic -r 1.0`. `-f` is "Unknown command-line option". Solute is now given with `-cp`; also `-p <.top>` (writes SOL count), `-box <vector>`, `-radius`, `-scale`, `-shell`, `-maxsol`, `-vel`. (`-cs cubic` is still valid.)

### I-09 `gmx genion` — CLI completely broken  [H]  ✅ RESOLVED (2026-09-04)
Files: `01-phases/01.3-solvation-ions-box.md`, `00.2-command-surface.md`, `00.3-file-formats-dataflow.md`, `00.6-force-fields-water.md`, `README.md`
KB: `gmx genion -s solvated.gro -p topol.top -n ions.itp -o … -neutral -conc 0.15`. Real: `-s` accepts **.tpr only** (`.gro` → "cannot be used for this option"), `-n` is `.ndx`, `-p` is `.top`, plus `-np/-pname/-pq`, `-nn/-nname/-nq`, `-conc`, `-neutral`. No `-select`/`-pdb`. Correct flow: `grompp → .tpr → gmx genion -s solvated.tpr -p topol.top -o out.gro -np N -pname NA -nn N -nname CL -conc 0.15` (prompts for solvent group).

### I-10 `gmx insert-molecules` — wrong flags  [H]  ✅ RESOLVED (2026-09-04)
Files: `01-phases/01.3-solvation-ions-box.md`
KB: `insert-molecules -s extra.gro -box solvated_ions.gro`. Real: `-f <system>`, `-ci <mols>`, `-ip <.dat>`, `-box <vector>` (not a file), `-nmol`, `-conc`.

### I-11 `gmx awh` — `-f` expects `.edr`  [M]  ✅ RESOLVED (2026-09-04)
Files: `01-phases/01.8-analysis.md`, `02-md-types/02.05-metadynamics-awh-colvars.md`
`-f` takes the AWH **.edr** (not `.xvg`); `-s` `.tpr`, `-o` `.xvg`, `-fric` `.xvg`.

### I-12 `gmx dssp` — output extensions  [M]  ✅ RESOLVED (2026-09-04)
Files: `01-phases/01.8-analysis.md`, `01.1-structure-preparation.md`, `00.2-command-surface.md`
`-o` expects `.dat`, `-num` expects `.xvg`. KB's `-o dssp.xvg` is wrong.

### I-13 `gmx hbond` — output extensions  [M]  ✅ RESOLVED (2026-09-04)
Files: `01-phases/01.8-analysis.md`, `02-md-types/02.01-standard-ensembles.md`, `00.2-command-surface.md`
`-o` expects `.ndx`, `-num` expects `.xvg`. KB's `-o hbond.xvg` is wrong.

### I-14 `gmx mindist` — output extensions  [M]  ✅ RESOLVED (2026-09-04)
Files: `01-phases/01.8-analysis.md`, `00.2-command-surface.md`
`-o` expects `.out`; `-od`/`-on` are the `.xvg` (distance / count).

### I-15 `gmx check` / `gmx dump` — wrong flag  [M]  ✅ RESOLVED (2026-09-04; fix text corrected in second audit)
Files: `00-foundations/00.1-versions-install.md`, `01-phases/01.7-restart-parallelization.md`
`check -s` is not a flag: use `-s1`/`-s2` for `.tpr`, `-f` for trajectories/`.cpt`. → 00.1 line 16 `gmx check -s run.tpr` is broken, fix to `gmx check -s1 run.tpr`.
**Correction (second audit): `dump` DOES have `-s` (for `.tpr`)** — do not remove `-s` from `dump`. The actual KB bug is 01.7 line 23 `gmx dump -s state.cpt`: `-s` only accepts `.tpr`, so for checkpoints use `gmx dump -cp state.cpt`.

---

## 3. MDP — pull engine (fully redesigned)

### I-16 Old `pull-*` options all invalid  [H]  ✅ RESOLVED (2026-09-04)
Files: `02-md-types/02.04-pmf-umbrella.md`, `03-playbooks/03.2-mdp-templates.md`, `02-md-types/02.05-metadynamics-awh-colvars.md`, `02-md-types/02.07-nemd-pulling.md`
Gone: `pull-coord`, `pull-coord1-type` (old enum), `pull-coord1-group1/2`, `pull-coord1-increment`, `pull-coord1-force-constant`, `pull-coord1-drag-coef`, `pull-coord1-dim = 1 0 0`.
New: `pull = yes` + `pull-ncoords` + `pull-ngroups` + `pull-group1-name` + `pull-coord1-groups` + `pull-coord1-vec` + `pull-coord1-rate` + `pull-coord1-k` + `pull-coord1-dim = yes no no` + `pull-coord1-geometry`.
- `pull-coord1-dim` is now **`yes`/`no`** (not `1 0 0`).
- `pull-coord1-geometry` enum: `distance direction cylinder direction-periodic direction-relative angle dihedral angle-axis transformation` — **`COM` removed**.
- Type enum: `umbrella constraint constant-force flat-bottom flat-bottom-high external-potential` (old `umswitch`/`pull` gone).
- New extras: `pull-coord1-expression/dx/origin/start`, `pull-group1-weights`, `pull-group1-pbcatom`, `pull-cylinder-r`, `pull-constr-tol`, `pull-print-com/ref-value/components`, `pull-nstxout/nstfout`, `pull-pbc-ref-prev-step-com`, `pull-xout-average`, `pull-fout-average`.

---

## 4. MDP — AWH / FEP

### I-17 AWH dim options — new options added, old ones NOT removed  [L]  ✅ RESOLVED (2026-09-04; original claim disproven — additions documented, existing `awh1-dim1-*` usage kept)
Files: `03-playbooks/03.2-mdp-templates.md`, `02-md-types/02.05-metadynamics-awh-colvars.md`
The original claim "old `awh1-dim1-*` gone" is **wrong**: `awh1-dim1-start/end/diffusion/cover-diameter` and `awh1-dim1-force-constant` (the exact option used in 03.2 line 230) all parse fine in this build. What is real: the build **added** `awh1-dim1-coord-provider` (`pull`|`free-energy-lambda`) + `awh1-dim1-coord-index`, plus `awh1-error-init`, `awh1-growth`, `awh1-growth-factor`, `awh1-equilibrate-histogram`, `awh1-histogram-tolerance`, `awh1-target`, `awh1-target-beta-scaling`, `awh1-target-cutoff`, `awh1-user-data`, `awh1-share-group`, `awh1-target-metric-scaling(-limit)`. Fix = document the additions, **do not rewrite existing `awh1-dim1-*` usage**.

### I-18 FEP soft-core renamed + `free-energy-group` removed  [H]  ✅ RESOLVED (2026-09-04)
Files: `00-foundations/00.5-mdp-anatomy.md`, `02-md-types/02.03-alchemical-free-energy.md`, `03-playbooks/03.2-mdp-templates.md`
Gone: `sc-r`, `sc-n`, `sc-zero`, `sc-coulomb`, `free-energy-group`.
New: `sc-function` (`beutler`|`gapsys`), `sc-r-power`, `sc-coul`, `sc-power`, `sc-sigma`, `sc-gapsys-scale-linpoint-lj/q`, `sc-gapsys-sigma-lj`.
`couple-lambda0/1` are now **enum** (e.g. `vdw-q`), not vectors. New: `dhdl-print-energy`, `init-lambda-weights/counts`.

---

## 5. MDP — misc renames / removals

### I-19 Renamed / removed options  [M]  ✅ RESOLVED (2026-09-04)
Files: `00-foundations/00.5-mdp-anatomy.md` (plus where each appears)
- `fourier`→`fourierspacing`; `fourier-grid`→`fourier-nx/ny/nz`
- `coulomb-mod`→`coulomb-modifier`
- `lincs-itmax`→`lincs-iter`; `lincs-warnstep`→`lincs-warnangle`
- `periodic-mols`→`periodic-molecules`
- `xtp`→`compressed-x-precision` + `compressed-x-grps` + `nstxout-compressed`
- `tau-bfric` **removed** (see also I-26)
- `colvars`→`colvars-active` + `colvars-configfile`
- `com-pull` **removed**
- `constraint`/`constraint-order` removed → `constraints` (plural)

### I-20 Option type changes  [M]  ✅ RESOLVED (2026-09-04)
Files: `00-foundations/00.5-mdp-anatomy.md`, `02-md-types/02.03-alchemical-free-energy.md`, `02-md-types/02.14-specialized.md`
- `dhdl-derivatives` now `yes/no` (was 16-value list)
- `calc-lambda-neighbors` now integer (was yes/no)
- `rotation` now `no/yes` + new `rot-*` API (`rot-ngroups`, `rot-group0`, `rot-type0`, `rot-vec0`, …); KB's "enforced-rotation block" name is wrong
- `simulated-tempering-scaling` is an enum (`linear`/`exponential`), not a real
- `electric-field-x/y/z` now take **4 values** `E0 omega t0 sigma` (static = `100 0 0 0`); KB's single-value form is wrong

### I-21 Wall options (2026)  [M]  ✅ RESOLVED (2026-09-04)
Files: `00-foundations/00.2-command-surface.md`, `00.5-mdp-anatomy.md`, `01-phases/01.3-solvation-ions-box.md`, `02-md-types/02.14-specialized.md`, `03-playbooks/03.1-decision-trees.md`, `README.md`
`wall-type` `cubic` removed → enum `9-3/10-4/12-6/table`. Now: `nwall` (0/1/2), walls fixed at z=0/z-box (no user positions), `wall-atomtype` (one per wall, must be defined in topology), `wall-density` (one per wall), `wall-ewald-zfac`, `wall-r-linpot`. Requires `pbc = xy`.

---

## 6. Coupling enums & integrators

### I-22 `tcoupl` enum changed  [H]  ✅ RESOLVED (2026-09-04)
Files: `00.5-mdp-anatomy.md`, `01.5-equilibration.md`, `01.6-production.md`, `02-md-types/02.01-standard-ensembles.md`, `02.08-langevin-brownian.md`, `02.09-simulated-annealing.md`, `03.1-decision-trees.md`, `03.2-mdp-templates.md`, `03.4-failure-diagnosis.md`, `README.md`
Build enum: `No Berendsen Nose-Hoover yes Andersen Andersen-massive V-rescale`. **MTTK and C-rescale removed from tcoupl** (moved to pcoupl). New: `Andersen`, `Andersen-massive`. Andersen is **not supported with `integrator = md`** (works with `sd`/`bd`) and requires `nstcomm = 1`.

### I-23 `pcoupl` enum changed  [H]  ✅ RESOLVED (2026-09-04; reasoning corrected in second audit)
Files: `00.5-mdp-anatomy.md`, `01.3-solvation-ions-box.md`, `01.5-equilibration.md`, `01.6-production.md`, `02-md-types/02.01-standard-ensembles.md`, `02.13-membranes.md`, `03.1-decision-trees.md`, `03.2-mdp-templates.md`, `03.3-checklists.md`, `03.4-failure-diagnosis.md`, `README.md`
Build enum: `No Berendsen Parrinello-Rahman Isotropic MTTK C-rescale`. **`pareto` removed** (verified: "Invalid enum 'pareto' for variable pcoupl"). `MTTK` is case-sensitive, is **deprecated** (per official docs), requires a **Velocity-Verlet integrator (`md-vv`)** — build error: "MTTK pressure coupling requires a Velocity-verlet integrator" (the original audit text wrongly said `integrator = md`) — **and no constraints** (build error: "Constraints are not implemented with MTTK pressure control"; note this triggers even with `constraints = none` when the topology itself carries constraints, e.g. SPC/SETTLE water).

### I-24 Removed integrators  [H]  ✅ RESOLVED (2026-09-04)
Files: `02-md-types/02.01-standard-ensembles.md`, `02.08-langevin-brownian.md`, `02.10-qmmm.md`, `03.1-decision-trees.md`, `03.2-mdp-templates.md`, `README.md`
`integrator = langevin / brownian / npt / rtpi / qmmm` do not exist. Present: `md, md-vv, sd, steep, cg, l-bfgs, nm, mimic, bd, tpi/tpic`. 02.08 is built around removed `tau-bfric`. QMMM is now `mimic`.

### I-25 `md-vv-avek` is validation-only now  [M]  ✅ RESOLVED (2026-09-04)
Files: `02-md-types/02.01-standard-ensembles.md`, `03-playbooks/03.1-decision-trees.md`
KB presents `md-vv-avek` as a production integrator. Build: "implemented primarily for validation, requires nsttcouple = 1 and nstpcouple = 1".

---

## 7. Expanded ensemble

### I-26 `lmc-mc-move` absent; `lmc-stats` enum  [M]  ✅ RESOLVED (2026-09-04)
Files: `00-foundations/00.5-mdp-anatomy.md`, `02-md-types/02.06-expanded-ensemble-replica-exchange.md`
`lmc-mc-move` is in the (newer) docs but **not in this build** — do not put it in the KB. `lmc-stats` enum uses `minvar` (KB says `min-variance`) and also has `weighted-wang-landau` (KB omits it). Full build enum: `no metropolis-transition barker-transition minvar wang-landau weighted-wang-landau`.

---

## 8. Topology / file format / warnings

### I-27 Top-level water `.itp` files removed  [H]  ✅ RESOLVED (2026-09-04)
Files: `00-foundations/00.6-force-fields-water.md`, `01-phases/01.2-topology-forcefield.md`, `00.4-topology-anatomy.md`, `03-playbooks/03.2-mdp-templates.md`
Top-level `spc.itp`/`tip3p.itp`/`tip4p.itp`/`opc.itp` etc. are now `#error` stubs; water must be included from the FF dir (e.g. `oplsaa.ff/spc.itp`). `amber14sb.ff`/`amber19sb.ff` ship `opc.itp`, `opc3.itp`, `ions_opc.itp`, `ions_opc3.itp`. Check every topology example/template.

### I-28 `[ system ]` section now required  [M]  ✅ RESOLVED (2026-09-04)
Files: `00-foundations/00.4-topology-anatomy.md`, `01-phases/01.2-topology-forcefield.md`
A `[ system ]` section is now required before `[ molecules ]`. Verify all topology examples include it.

### I-29 Unknown MDP option = warning; `-maxwarn` silently ignores  [M]  ✅ RESOLVED (2026-09-04)
Files: `00-foundations/00.2-command-surface.md`, `01-phases/01.9-troubleshooting.md`, `03-playbooks/03.3-checklists.md`, `03.4-failure-diagnosis.md`
Unknown options are a WARNING; grompp fails by default ("Too many warnings"), but with `-maxwarn` they are **silently ignored**. An agent writing old options (e.g. pull) + `-maxwarn` gets a TPR with no pull setup and a silent no-op run. KB's `-maxwarn` guidance should warn about this failure mode.

---

## 9. Specialized (02.14)

### I-30 02.14 multiple invalid option names  [M]  ✅ RESOLVED (2026-09-04)
Files: `02-md-types/02.14-specialized.md`
- "enforced-rotation block" → real API is `rotation = yes` + `rot-*` (see I-20)
- `fmm` (order, grid) → real: `fmm-backend` (`inactive/exafmm/fmsolvr`) + `fmm-exafmm-*`, requires `coulombtype = FMM`
- density-guided options → real: `density-guided-simulation-*` family
- `shell` options → not a valid MDP option
- test-particle insertion → not a valid option; TPI is `integrator = tpi/tpic`
- `wall-type cubic` → removed (see I-21)

---

## 10. Internal inconsistency

### I-31 03.5 all-bonds + GPU contradiction  [L]  ✅ RESOLVED (2026-09-04; fix applied in 03.5, docs-based)
Files: `03-playbooks/03.5-performance.md`
Line 31/34: "all-bonds still works with GPU update, but its P-LINCS setup incurs substantial communication overhead." Line 107 (pitfalls table): "constraints = all-bonds → GPU-resident update unavailable." These contradict each other; one is wrong. Confirm against the HIP build (no GPU compute available — docs-only check).
**Resolution (2026-09-02):** docs show GPU LINCS has a topology-support limit (`LincsGpu::isNumCoupledConstraintsSupported`) — with `all-bonds` on typical biomolecules the coupled-constraint count exceeds it and the update falls back to CPU. **Line 107 is the accurate one for typical use; lines 31/34 overstate.** Suggested fix: make 31/34 say all-bonds usually disables GPU-resident update (LINCS falls back to CPU); keep 107 as-is. Still not GPU-verified on this stack.

---

## 11. Missing topics (features in build, absent/thin in KB)

### I-32 New features not documented  [L]  ✅ RESOLVED (2026-09-04)
Files: (gaps) `02.14-specialized.md`, `02.10-qmmm.md`, `00.3-file-formats-dataflow.md`, `01.6-production.md`, `03.5-performance.md`
Present in the build but not properly covered: **FMM** (`fmm-backend`), **density-guided simulation** (`density-guided-simulation-*`), **`mimic`** (QMMM replacement), **TNG** (enabled; only mentioned in passing), **Andersen/Andersen-massive** thermostats, **Isotropic** pcoupl. Also several new analysis tools (`freevolume`, `scattering`/`saxs-legacy`/`sans-legacy`, `dos`, `dielectric`, `polystat`, `spol`, `saltbr`, `rotacf`, `rotmat`, `spatial`, `cluster`/`clustsize`/`extract-cluster`, `current`, `eneconv`/`enemat`, `mdmat`) are not in the analysis inventory.

---

## 12. Stack / Dockerfile findings (outside the KB)

### I-33 `gmx` fails to start — ROCm lib path dropped from `LD_LIBRARY_PATH`  [H]  ✅ FIXED (2026-09-03, verified against rebuilt image)
File: `../Dockerfile.rocm`
The image's `ENV LD_LIBRARY_PATH=/usr/local/gromacs/lib:${LD_LIBRARY_PATH}` drops the base image's ROCm library paths. Result: a plain `docker run gromacs-hip-gfx1100:latest gmx ...` dies immediately with `error while loading shared libraries: libamdhip64.so.7: cannot open shared object file` (the lib lives at `/opt/rocm/lib/libamdhip64.so.7`, via `/etc/alternatives` symlinks). Verified against the actual image on 2026-09-02 — every container invocation currently needs a manual `-e LD_LIBRARY_PATH=/opt/rocm/lib:/usr/local/gromacs/lib` override. Fix: add `/opt/rocm/lib` (and defensively `/opt/rocm/lib64`) to the `LD_LIBRARY_PATH` in the Dockerfile `ENV` line.
**Fix applied (2026-09-03):** the `ENV` line now reads `LD_LIBRARY_PATH=/opt/rocm/lib:/opt/rocm/lib64:/usr/local/gromacs/lib:${LD_LIBRARY_PATH}`. Root cause confirmed: base image `rocm/dev-ubuntu-24.04:7.14.0-full` does not export `LD_LIBRARY_PATH` in its image config (only `PATH` + `ROCM_PATH`), so `${LD_LIBRARY_PATH}` expanded empty at build time, and `/opt/rocm/lib` is also absent from `ld.so.conf`/`ldconfig` (no fallback). Image rebuilt (all layers cached); plain `docker run gromacs-hip-gfx1100:latest gmx --version` and `gmx grompp -h` now start with no `-e` override. Matches the working pattern in `llamacpp/Dockerfile.rocm`.

## Notes for the reviewer
- **Docs vs build drift:** `manual.gromacs.org/current` is newer than 2026.3-dev-20260625. Options that exist in docs but NOT in the build (do not add to KB): `lmc-mc-move`, `fep-lambda`, `dhdl-file`.
- **Verified OK / no change needed:** `convert-tpr`, `energy`, `genrestr`, `gyrate`, `make_ndx`, `msd`, `pdb2gmx`, `rdf`, `rmsf`, `rms`, `order`, `sasa`, `density`, `pairdist`, `bar`, `trjcat`, `trjconv` (no `-fitgroup` used in KB), `editconf -bt`, `solvate -cs cubic`, `01.7` already uses `convert-tpr`.
  - *Superseded in part by the second pass (section 13):* the first pass verified the flags
    **used in KB recipes**; the second pass checked the full 00.2 "Key flags" reference columns
    and found stale names there (I-35/I-36/I-37). Where the two conflict, section 13 wins.
- **No GPU compute** was available (eGPU busy with AI inference); all verification was CPU-only (grompp / solvate / help). GPU-specific claims (I-31) are docs-only.

---

## 13. Second audit pass (2026-09-04 — CLI flag columns, stale options, semantic errors)

**Verification (2026-09-05, vs live build `2026.3-dev-20260625` in `gromacs-rocm`):**
All 16 issues I-34…I-49 re-verified by re-running `gmx <tool> -h` probes, `grompp`
option/enum probes (incl. context-dependent), FF-dir listings, `libgromacs.so` `GMX_*`
string scans, and the 2026 manual (I-46). **All 16 are REAL — no false positives.**
14 are correctly described and ready to fix as written. Two description errors were found
and **corrected in place** in the entries below:
- **I-39**: the original sub-claim "`nnpot-pair-cutoff` → the option is `pair-cutoff`" was
  **inverted** (re-probed: `nnpot-pair-cutoff` is the valid name; `pair-cutoff` is
  "Unknown left-hand" even with `nnpot-active = yes`). Entry updated: the bullet was
  removed, `nnpot-pair-cutoff` is in the valid set, and the activation failure is noted as
  a **grompp**-time abort, not runtime.
- **I-44**: the "Correct NPT / New 2026.3 value" label is in
  **`01-phases/01.5-equilibration.md` (line 87)**, not in 02.01. Entry updated: 01.5 added
  to the file list and the attribution fixed. Build NOTE confirmed verbatim.

New issues found by re-verifying **every flag column, MDP block, and semantic claim** in the KB
against the live `gromacs-rocm` build (`2026.3-dev-20260625`) via `gmx <tool> -h`, targeted
`grompp` probes (incl. context-dependent options via `-po` and bogus-enum probing), and the
2026 manual. The prior pass (I-1…I-33) fixed the MDP *recipes*; this pass found that many
**reference flag columns** (00.2) and **secondary recipes** still carry pre-2026 names.

## Resolution status (2026-09-05 — second audit pass I-34…I-49 fixed & re-verified)

**All 16 issues (I-34…I-49) are now closed.** Every KB file listed under each
issue was edited to match the `2026.3-dev-20260625` build, and the rewritten
MDP blocks / flag columns were re-verified against the live `gromacs-rocm`
container (`gromacs-hip-gfx1100:latest`) via `gmx <tool> -h`, targeted `grompp`
option/enum probes, and a combined MDP parse. Statuses below are updated to
`✅ RESOLVED (2026-09-05)`. Notes from the fix pass:

- **I-34**: all 15 removed options confirmed "Unknown left-hand"; the 14
  current options (`epsilon-r`, `epsilon-rf`, `pme-order`, `fourierspacing`,
  `ewald-rtol`, `lincs-order`/`lincs-iter`/`lincs-warnangle`, `disre`/
  `disre-weighting`/`disre-mixed`/`disre-fc`/`disre-tau`/`nstdisreout`)
  confirmed valid. `00.5` rows rewritten.
- **I-35/I-37**: the 11 "Key flags" columns (00.2) and the 01.8 recipes were
  rewritten from live `gmx <tool> -h` output; `trjconv -pbc`/`-fit` enums
  re-probed (`none/mol/res/atom/nojump/cluster/whole`,
  `none/rot+trans/rotxy+transxy/translation/transxy/progressive`).
- **I-36**: `pdb2gmx` recipe rewritten with real flags (`-i` posre, `-[no]ss`
  boolean); `-igb`/`-pbr`/`-cys`/`-membrane` dropped. Straggler fixed in
  `03.3` (disulfide `-cys` checklist item).
- **I-38**: TPI corrected to `integrator = tpi`/`tpic` + `rtpi` (radius) in
  `00.5`, `02.01`, `02.14`, `README`; `rtpi` confirmed **not** an integrator
  ("Invalid enum 'rtpi' for variable integrator").
- **I-39**: NNPot options corrected; `nnpot-embedding` enum =
  `mechanical`/`electrostatic-model`; activation aborts at **grompp** time
  with `-DGMX_NNPOT=TORCH` (reproduced in
  `nnpotoptions.cpp::checkNNPotModel()`).
- **I-40**: FF table → `charmm27` (CHARMM36 not shipped), `gromos54a7`;
  water table → `tip4p`/`tip4pew`.
- **I-41**: `mdrun -colvars` references removed (00.2, 02.05); Colvars is
  MDP-only. Straggler fixed in `02.04`.
- **I-42**: `-continue`/`-f` dropped; `-cpt` documented as **minutes**.
- **I-43**: README "Removed tools" → `trjpos`→`convert-trj` (`trjconv`
  exists).
- **I-44**: `pcoupl = Isotropic` relabeled as a **legacy Berendsen alias**
  (grompp NOTE reproduced) in `00.5`, `01.5`, `02.01`, `README`; straggler
  fixed in `02.13`.
- **I-45**: `nonbonded-benchmark -simd` = `auto/no/4xm/2xmm`, `-coulomb` =
  `ewald/reaction-field`; `GMX_ENABLE_GPU_TIMING` removed.
- **I-46**: PLUMED fix corrected to `-ntmpi 1` (2026 manual: incompatible
  with thread-MPI, not OpenMP threads).
- **I-47**: "dhdl.xvg gone" clause removed (`mdrun -dhdl` still writes it).
- **I-48**: GPU-timing env-var row removed from `00.1`.
- **I-49**: 02.14 NMR section now names the `disre-*` family + `gmx
  nmr`/`nmeig`/`nmens`/`nmtraj`.

---

### I-34 00.5 MDP anatomy — five rows list removed options as current  [H]  ✅ RESOLVED (2026-09-05)
Files: `00-foundations/00.5-mdp-anatomy.md`
All probed with `grompp` (with proper context) against the build:
- **Electrostatics row**: `rfcutoff`, `eps-r`, `eps-rf`, `coulomb-verlet-scheme`, `pme-spacing`,
  `dispersion-correction` → all "Unknown left-hand" (probed `rfcutoff` under
  `coulombtype = Reaction-field`; `pme-spacing`/`dispersion-correction` under `coulombtype = PME`).
  Current names verified valid: `epsilon-r`, `epsilon-rf` (plus `pme-order`, `fourierspacing`,
  `ewald-rtol`).
- **Output control row**: `nstxout-steps`, `nstwrite`, `nstframe`, `nsthistogram` → all unknown.
- **Bonds/constraints row**: `lincs-warnsize`, `lincs-mtol`, `lincs-algo` → all unknown
  (only `lincs-order`, `lincs-iter`, `lincs-warnangle` exist).
- **NMR refinement row**: `nmr-*` → all removed. The 2026.3 NMR-refinement API is the
  `disre` family — `disre` (`no`/`simple`/`ensemble`), `disre-weighting`, `disre-mixed`,
  `disre-fc`, `disre-tau`, `nstdisreout` (all verified valid), plus `gmx nmr`/`nmeig`/`nmens`/
  `nmtraj` analysis tools (all present in the build).
- **Viscosity row**: `calcvf` → unknown (removed).
Fix: delete the removed options; replace the NMR row with the `disre-*` family.

### I-35 00.2 command surface — "Key flags" columns stale for 11 tools  [H]  ✅ RESOLVED (2026-09-05)
Files: `00-foundations/00.2-command-surface.md`
Every flag below was checked against live `gmx <tool> -h` output:
- **`pdb2gmx`**: `-igb`, `-pbr`, `-bact`, `-cys`, `-membrane`, `-zero`, `-altloc` don't exist;
  `-ss` is a boolean (`-[no]ss`), not a sec-struct file. Real flag set: `-f -o -p -i -n -q
  -chainsep -merge -ff -water -inter -ss -ter -lys -arg -asp -glu -gln -his -angle -dist -una
  -ignh -missing -v -posrefc -vsite -heavyh -deuterate -cmap -renum -rtpres`.
- **`editconf`**: `-ct`, `-if`/`-of` don't exist (real: `-bt`, `-center`, `-density`);
  `-d` is "distance between the solute and the box" (real, default 0), not density — the KB's
  "-d density" is wrong (density is `-density`). (`-[no]c` "center molecule in box" and
  `-[no]pbc` "apply PBC" both exist, so the KB's `-c` and `-pbc` are fine.)
- **`make_ndx`**: `-select`, `-id` don't exist (only `-f -n -o -natoms`; group building is
  interactive).
- **`select`**: `-index`, `-output`, `-res` don't exist (real: `-n`, `-oi`/`-on`,
  `-resnr`; `-select <selection>` does exist but is not in the KB column).
- **`mk_angndx`**: `-f`, `-o` don't exist (real: `-s -n -type -hq`).
- **`genrestr`**: `-group` doesn't exist (use `-n`).
- **`grompp`**: `-i` doesn't exist (continuation input is `-t`).
- **`convert-tpr`**: `-define` doesn't exist (real: `-s -n -o -extend -until -nsteps
  -velocity_temp -velocity_seed`).
- **`mdrun`**: `-f` (use `-s`), `-continue`, `-nocontinuation`, `-colvars`, `-debug`
  don't exist (`-[no]v` verbose does exist).
- **`trjconv`**: `-surround`, `-resnum`, `-fitref`, `-begin`/`-end` (use `-b`/`-e`),
  `-compress` don't exist (`-[no]center` boolean does exist, so the KB's `-center` is fine);
  `-pbc` enum wrong (real: `none/mol/res/atom/nojump/cluster/whole`);
  `-fit` enum wrong (real: `none/rot+trans/rotxy+transxy/translation/transxy/progressive`).
- **`trjcat`**: `-skip`, `-shift`, `-set-switch`, `-single` don't exist (real: `-f -n -demux -o
  -tu -xvg -b -e -dt`).
- Notes section: "Every analysis tool reads index groups (`-index`, `-n`)" — analysis tools use
  `-n`, not `-index`.
Fix: rewrite each flag column from live `-h` output.

### I-36 01.1 pdb2gmx recipe — four non-existent flags + `-ss` misuse  [H]  ✅ RESOLVED (2026-09-05)
Files: `01-phases/01.1-structure-preparation.md`, `02-md-types/02.13-membranes.md`
(02.13 line 13 also references the absent `pdb2gmx -membrane` flag.)
The step-3 recipe `gmx pdb2gmx -f protein.pdb -o protein.gro -ff amber14sb -water opc
-igb 1 -ss dssp -pbr protein.posre.itp -cys "CYS101 CYS205" -membrane` uses `-igb`, `-pbr`,
`-cys`, `-membrane` (all absent) and `-ss dssp` (`-ss` is a boolean, takes no file). The
following line explains "-cys: disulfide list. -membrane: orient TM helices along z" — both
flags absent. Posre output is via `-i posre.itp`.
Fix: rewrite the recipe with real flags; drop the disulfide/membrane flag notes.

### I-37 01.8 analysis — stale tool flags & capabilities  [M]  ✅ RESOLVED (2026-09-05)
Files: `01-phases/01.8-analysis.md`
- `gmx make_ndx -f md.tpr -o index.ndx -select "resname PRO and name CA" -id CA` — `-select`/
  `-id` don't exist (make_ndx is interactive).
- `gmx trjconv … -pbc mol -fit rot+trans -center -nocustom` — `-nocustom` doesn't exist
  (`-center` is a valid boolean; `-pbc mol` and `-fit rot+trans` are valid enum values).
- "-center / -surround … use -fitref" — `-surround` and `-fitref` don't exist (`-center` is
  fine).
- `gmx trjcat -f a.xtc b.xtc -o all.xtc -skip 0 -single` — `-skip`/`-single` don't exist.
- `gyrate` "overall + per-residue (`-res`)" — no `-res` flag.
- `hbond` "use `-ac` for the lifetime autocorrelation" — no `-ac` flag (outputs: `-o` ndx,
  `-num`, `-dist`, `-ang`, `-dan`).
- `rdf` "`-ac`" — no `-ac` flag.
Fix: use real flags; drop the per-residue/autocorrelation capability claims.

### I-38 TPI recipe wrong in four files  [M]  ✅ RESOLVED (2026-09-05)
Files: `00-foundations/00.5-mdp-anatomy.md`, `02-md-types/02.01-standard-ensembles.md`,
`02-md-types/02.14-specialized.md`, `README.md`
KB claims TPI = `free-energy = expanded` + `mc-temperature` and "the old `rtpi` integrator is
gone". The build's `integrator` enum **includes `tpi` and `tpic`** (probed: `integrator = tpi`
generates a TPR; the `rtpi` MDP option exists with default 0.05 and is the insertion radius).
`free-energy = expanded` + `mc-temperature` is the **expanded ensemble / Wang-Landau** machinery
(see 02.06), not TPI.
Fix: TPI = `integrator = tpi` (or `tpic`) + `rtpi` (radius); `mdrun -tpi`/`-tpid` write the
insertion-distribution outputs.

### I-39 02.11 NNPot — wrong option names/values  [M]  ✅ RESOLVED (2026-09-05)
Files: `02-md-types/02.11-nnpot.md`
- `nnpot-mm-group` doesn't exist.
- `nnpot-nnp-charge` doesn't exist (manual: `nnp-charge` is an `nnpot-model-input` field).
- `nnpot-embedding = none` → enum is `mechanical` / `electrostatic-model` (probed).
- Banner says "-DGMX_TORCH=ON"; the build's own error message says
  "reconfigure GROMACS with -DGMX_NNPOT=TORCH".
Valid set (probed): `nnpot-active`, `nnpot-modelfile`, `nnpot-input-group`, `nnpot-embedding`,
`nnpot-model-input[1-9]`, `nnpot-pair-cutoff`, `nnpot-link-type` (element symbol),
`nnpot-link-distance`.
**Correction (2026-09-05 re-verification):** the original bullet "`nnpot-pair-cutoff` → the
option is `pair-cutoff`" was **inverted** — `nnpot-pair-cutoff` is the valid option name in
this build (no unknown-left-hand warning); `pair-cutoff` is "Unknown left-hand" even with
`nnpot-active = yes`. The KB's `nnpot-pair-cutoff` is correct — **keep it, do not rename**.
Fix: correct names/values; note activation aborts at **grompp** time without LibTorch
(internal error "Libtorch/NN backend is not linked into GROMACS … reconfigure GROMACS with
-DGMX_NNPOT=TORCH"), not at mdrun runtime.

### I-40 00.6 — force fields & water models not in the build  [M]  ✅ RESOLVED (2026-09-05)
Files: `00-foundations/00.6-force-fields-water.md`
- `charmm36` absent from `/usr/local/gromacs/share/gromacs/top/` (only `charmm27.ff`).
- `gromos56a7` absent (only up to `gromos54a7.ff`).
- `tip4p-sw` / `tip4p-2019` are not valid `-water` values (enum: `select/none/opc/opc3/spc/
  spce/tip3p/tip4p/tip4pew/tip5p/tips3p`); TIP4P/2005 = `tip4p`, TIP4P-Ew = `tip4pew`.
- "Disulfides: pass `-cys`" — flag absent. "-ss file and `-bact`" — `-ss` is boolean; `-bact`
  absent.
Fix: FF table → `charmm27` (+ note CHARMM36 not shipped), `gromos54a7`; water table → `tip4p`/
`tip4pew`; drop `-cys`/`-bact` references.

### I-41 `gmx mdrun -colvars` doesn't exist  [M]  ✅ RESOLVED (2026-09-05)
Files: `02-md-types/02.05-metadynamics-awh-colvars.md`, `00-foundations/00.2-command-surface.md`
mdrun has no `-colvars` flag (full flag list verified). Colvars is enabled via MDP only:
`colvars-active = yes` + `colvars-configfile` (+ `colvars-seed`) — all verified present.
Fix: remove the `-colvars` CLI references; keep the MDP route.

### I-42 01.7 — `-continue`, `-f`, and `-cpt` semantics  [M]  ✅ RESOLVED (2026-09-05)
Files: `01-phases/01.7-restart-parallelization.md`
- `gmx mdrun -deffnm md -cpi state.cpt -continue` — `-continue` doesn't exist (restart is
  `-cpi` alone; `-rerun` is the separate re-run mode).
- `gmx mdrun -f md_ext.tpr …` — `-f` doesn't exist (use `-s`).
- `gmx mdrun -deffnm md -cpt 50000` — `-cpt` is a checkpoint interval **in minutes** (real),
  not a step count.
Fix: drop `-continue`/`-f`; fix the `-cpt` description.

### I-43 README — "Removed tools: trjconv→convert-trj"  [M]  ✅ RESOLVED (2026-09-05)
Files: `README.md`
`trjconv` **exists** in the build (verified). The removed tool is `trjpos` (→ `convert-trj`).
00.2's removed-tools list is correct; the README "2026.3 API breaks" bullet is not.
Fix: change to `trjpos`→`convert-trj`.

### I-44 `pcoupl = Isotropic` is a legacy Berendsen alias, not "correct NPT"  [M]  ✅ RESOLVED (2026-09-05)
Files: `02-md-types/02.01-standard-ensembles.md`, `01-phases/01.5-equilibration.md`,
`00-foundations/00.5-mdp-anatomy.md`, `README.md`
Probed: `pcoupl = Isotropic` → grompp NOTE "Old option for pressure coupling given: changing
'Isotropic' to 'Berendsen'". It is a legacy alias for **Berendsen** (incorrect thermodynamic
ensemble), not a new correct-NPT value. **01.5** (line 87) labels it "Correct NPT / New
2026.3 value"; 02.01 lists it in the `md-vv` pcoupl column; 00.5/README list it as a modern
alternative.
Fix: relabel as legacy Berendsen alias (discouraged); recommend C-rescale/PR.

### I-45 03.5 — nonbonded-benchmark flags & GPU-timing env var  [M]  ✅ RESOLVED (2026-09-05)
Files: `03-playbooks/03.5-performance.md`
- `gmx nonbonded-benchmark … -simd AVX2_256` — `-simd` enum is `auto/no/4xm/2xmm` (probed);
  `AVX2_256` is invalid.
- "-coulomb `<PME|…>`" — enum is `ewald/reaction-field` (probed). (00.1's version of the same
  flags is correct — 03.5 contradicts it.)
- "Use `GMX_ENABLE_GPU_TIMING=1`" — env var absent from the build (verified by scanning
  `GMX_*` strings in `libgromacs.so`; 110 vars, none GPU-timing related).
Fix: correct the enums; drop the env-var reference.

### I-46 02.05 — PLUMED thread-MPI fix hint  [L]  ✅ RESOLVED (2026-09-05)
Files: `02-md-types/02.05-metadynamics-awh-colvars.md`
"PLUMED + thread-MPI → hard error (use `-ntomp 1` or MPI ranks)." The 2026 manual states PLUMED
is incompatible with **thread-MPI** (>1 thread-MPI rank, i.e. `-ntmpi`), not with OpenMP
threads. The fix is `-ntmpi 1` / regular MPI ranks, not `-ntomp 1`.
Fix: correct the hint.

### I-47 02.03 — "the old dhdl.xvg output file is gone"  [L]  ✅ RESOLVED (2026-09-05)
Files: `02-md-types/02.03-alchemical-free-energy.md`
mdrun still has `-dhdl [<.xvg>] (dhdl.xvg)` (verified in the flag list). The `dhdl.xvg` output
still exists (opt-in via `-dhdl`).
Fix: delete that clause.

### I-48 00.1 — GPU-timing env vars absent  [L]  ✅ RESOLVED (2026-09-05)
Files: `00-foundations/00.1-versions-install.md`
`GMX_ENABLE_GPU_TIMING` / `GMX_DISABLE_GPU_TIMING` don't exist in the build (verified by
scanning `GMX_*` strings in `libgromacs.so`). All other env vars in the table verified present
(`GMX_MAXBACKUP`, `GMX_LOG_BUFFER`, `GMX_SUPPRESS_DUMP`, `GMX_TPI_DUMP`,
`GMX_TRAJECTORY_IO_VERBOSITY`, `GMX_CUDA_GRAPH`, `GMX_FILLERS_IN_LOCAL_STATE`,
`GMX_NBNXN_PLAINC_1X1`, `GMX_HIP_TARGET_ARCH`).
Fix: remove the GPU-timing row.

### I-49 02.14 — NMR section vague (real API is `disre-*`)  [L]  ✅ RESOLVED (2026-09-05)
Files: `02-md-types/02.14-specialized.md`
"MDP: NMR refinement options (restraint files, force constants)" — the actual 2026.3 API is the
`disre-*` family (`disre` no/simple/ensemble, `disre-weighting`, `disre-mixed`, `disre-fc`,
`disre-tau`, `nstdisreout` — all verified valid) plus `gmx nmr` (analysis of restraint
violations from `.edr`) and `gmx nmeig`/`nmens`/`nmtraj` (all present in the build).
Fix: name the `disre-*` options and the `gmx nmr` tool.

---

## Verified OK in this pass (no change needed)
- 00.1: version context, AMBER14SB/19SB + OPC/OPC3 presence, NNPot banner, HIP/VkFFT notes,
  `nonbonded-benchmark` flag description (correct in 00.1 — it is 03.5 that is wrong).
- 00.2: `solvate`, `genion`, `insert-molecules`, `check`, `dump`, `convert-trj`, `xpm2ps`
  rows; the full 45-tool analysis inventory (all present); the removed-tools list.
- 01.3 (solvate/genion/insert-molecules recipes), 01.4, 01.5 (incl. `refcoord-scaling` enum,
  `comm-mode`, no `constr-com`), 01.6 (incl. TNG claims, `nstcheckpoint`, MTS block), 01.9.
- 02.01: integrator compatibility table (Andersen×md error, md-vv-avek NOTE, MTTK constraints
  error all reproduced), `tcoupl` enum, `pcoupltype` enum.
- 02.02, 02.03 (all FEP/soft-core options incl. `couple-moltype`, `couple-intramol`,
  `sc-gapsys-*`), 02.04 (full pull API incl. geometry enum, `pull-coord1-origin`; old
  `pull-coord1-increment/-force-constant/-flat-bottom/-group1` confirmed gone), 02.05 AWH
  block (incl. `awh1-dimN-cover-diameter`, `awh-share-multisim`, `awh1-share-group` int,
  `calc-lambda-neighbors = -1` requirement), 02.06 (all LMC options + enums incl.
  `lmc-weights-equil`; `min-variance` confirmed rejected), 02.07 (pull API;
  `pull-coord1-drag-coef` confirmed gone), 02.08 (sd/bd + `bd-fric`; `tau-bfric` gone;
  `langevin`/`brownian` integrators gone), 02.09 (annealing API + example grompp-verified),
  02.10 (`qmmm-cp2k-*` all valid; `qmmm = yes` → fatal "no longer supported"), 02.12, 02.13
  (semiisotropic coupling + analysis tools; the `pdb2gmx -membrane` reference is covered by
  I-36), 02.14 (walls/rotation/DGS/FMM/electric-field sections all re-verified accurate).
- 03.1, 03.2 (all 76 template options valid), 03.3, 03.4, 03.5 (MTS block: "only
  mts-levels = 2" and "integrator md only" errors reproduced).
- Env vars, `GMX_TPI_DUMP`, TNG/`-x`/`dump`/`check` on `.tng`, `gmx nmr`/`nmeig`/`nmens`/
  `nmtraj` presence.
- **Correction (2026-09-06):** 01.6's `nstcheckpoint` was listed as "verified OK" in this
  pass but is actually **obsolete** (see I-50 below). The option parses without an
  "Unknown left-hand" warning but grompp prints `Ignoring obsolete mdp entry
  'nstcheckpoint'` — it never reaches the TPR. The false negative is noted.

---

## New issues from 00-foundations validation pass (2026-09-06)

**Resolution status (2026-09-06 — all 7 re-verified against live build
`2026.3-dev-20260625` in `gromacs-hip-gfx1100:latest` and fixed):**
All of I-50…I-56 were re-verified by running targeted `gmx grompp` probes
(`-po` output + TPR `gmx dump`), `find` on the install tree, and `gmx <tool> -h`
text inside the container. **All 7 are REAL — no false positives.** All KB files
listed were edited; the rewritten MDP templates (03.2 `em`/`nvt`/`npt`/`md`)
were re-verified by running `gmx grompp` on each (all generate a TPR, no
warnings). Notes:
- **I-50**: reproduced `Ignoring obsolete mdp entry 'nstcheckpoint'` verbatim;
  `mdrun -h` confirms `-cpt <real> (15) Checkpoint interval (minutes)`.
- **I-54**: default confirmed as `nstlist = 10` (TPR via `gmx dump` when the
  option is omitted). **Correction to the recommended-fix text:** `0` is NOT
  "auto-guess" in this build — `nstlist = 0` is rejected with `With Verlet
  lists nstlist should be larger than 0` (the 2026 manual defines 0 as
  "never updated, suitable for vacuum" — unsupported). The KB fix records the
  rejection instead.
- **I-55**: `annealing = XX` accepted in both EM and MD contexts (TPR
  generated, no error); the typo-safety note was added to 00.5.
- **I-56**: `vdwtype = cut-off` accepted (TPR generated). As the issue itself
  recommends, **no KB change** — 00.5 already uses the canonical `vdw-type`;
  alias noted here for reference.

### I-50 `nstcheckpoint` is obsolete and silently ignored [M]  ✅ RESOLVED (2026-09-06)
Files: `00-foundations/00.5-mdp-anatomy.md` (lines 24, 52)
`nstcheckpoint` is listed as a current output-control option. In this build it is recognized but
**ignored**: grompp prints `Ignoring obsolete mdp entry 'nstcheckpoint'` and it never reaches
the TPR. The checkpoint interval is set by `mdrun -cpt` (minutes, default 15).
GROMACS source: `tpxv_RemoveObsoleteParameters1, /**< remove optimize_fft, dihre_fc, nstcheckpoint */`.
The same stale option also appears in `01.6` (lines 34/54), `01.7` (line 9), `03.2` (lines 75/121/167:
`nstcheckpoint = 50000`), `03.3` (line 66) and `README.md` (line 141).
**Recommended fix**: Remove `nstcheckpoint` from 00.5; state that checkpoint interval is `mdrun -cpt`
(minutes). Replace `nstcheckpoint = 50000` in 01.6/03.2 templates with a `-cpt` note.

### I-51 00.5 claims "A sample MDP ships with GROMACS" [L]  ✅ RESOLVED (2026-09-06)
Files: `00-foundations/00.5-mdp-anatomy.md` (Conventions, line 15)
No `.mdp` file exists anywhere in the install (`find / -name "*.mdp"` → nothing). The grompp-warns
clause is true; the "ships with" clause is not verifiable.
**Recommended fix**: Delete the "A sample MDP ships with GROMACS" clause; keep the grompp-warns clause.

### I-52 00.4 omits that the main `.top` must include the force field's `forcefield.itp` [L]  ✅ RESOLVED (2026-09-06)
Files: `00-foundations/00.4-topology-anatomy.md`
Without `#include "<ff>.ff/forcefield.itp"`, the parser rejects `[ moleculetype ]` with the misleading
`Invalid order for directive moleculetype` (the forcefield include provides the single allowed
`[ defaults ]`). 00.4's directive-ordering section never mentions this requirement.
**Recommended fix**: Add: the main `.top` must start with `#include "<ff>.ff/forcefield.itp"`.

### I-53 00.2 flag descriptions don't match the build's help text [L]  ✅ RESOLVED (2026-09-06)
Files: `00-foundations/00.2-command-surface.md`
Five parenthetical descriptions diverge from build help text:
1. `pdb2gmx -[no]ss` — KB: "add sec-struct (bool)"; build: "Interactive SS bridge selection"
2. `solvate -cs` — KB: "default `0 0 0` = auto cubic"; build: `spc216.gro`
3. `solvate -radius` — KB: "min solute-box distance"; build: "Default van der Waals distance"
4. `solvate -scale` — KB: "scale water box"; build: "Scale factor to multiply Van der Waals radii"
5. `insert-molecules -sf` — KB: "structure file"; build: "Provide selections from files"
**Recommended fix**: Align the five descriptions with the build help text.

### I-54 00.5 "nstlist (default auto)" — build default is 10 [L]  ✅ RESOLVED (2026-09-06; fix text corrected — `0` is rejected, not auto-guess)
Files: `00-foundations/00.5-mdp-anatomy.md` (Cut-off & neighbor-search invariants)
KB says "default auto". The build's MDP default is `nstlist = 10` (0 = auto-guess with
`verlet-buffer-tolerance`).
**Recommended fix**: "(default 10; `0` = auto-guess with `verlet-buffer-tolerance`)".

### I-55 `annealing` parser quirk — accepts arbitrary strings [L]  ✅ RESOLVED (2026-09-06)
Files: `00-foundations/00.5-mdp-anatomy.md`
This build accepts *any* string for `annealing` (e.g. `XX` accepted without error) in both EM and MD
contexts, while all other enums validate. The 2026 API defines it as enum `No/Single/Periodic` —
KB's enum claim matches the documented API, but typos in `annealing` will not be caught by grompp.
**Recommended fix**: Add a note: "Note: this build's grompp accepts arbitrary strings for
`annealing` without validation — typos are not caught."

### I-56 `vdwtype` accepted as alias of `vdw-type` [L]  ✅ RESOLVED (2026-09-06, no KB change — as recommended)
Files: `00-foundations/00.5-mdp-anatomy.md`
The option `vdwtype` (no hyphen) is accepted as an alias of `vdw-type` in this build.
KB uses `vdw-type` which is correct; the alias is noted for completeness.
**Recommended fix**: No change needed; alias noted for reference.
**Verification (2026-09-06):** `vdwtype = cut-off` grompp probe generated a TPR
with no unknown-left-hand warning — alias confirmed. No KB edit required.

---

## New issues from full-KB re-audit (2026-09-07)

**Method:** all 31 KB files re-read; every tool CLI re-checked against the live build
`2026.3-dev-20260625` (`gmx <tool> -h`), MDP templates re-run through `gmx grompp`
(EM/NVT/NPT/production/FEP/umbrella/AWH/membrane/Langevin/annealing/expanded-ensemble
all generate a TPR), the install tree re-listed, and semantic claims cross-checked
against the `v2026.3` source tag and `manual.gromacs.org/2026.3`. CPU-only grompp /
tool probes only — no MD run (eGPU in use). **Result: 5 new issues (I-57…I-61),
all confirmed real against the build.**

### I-57 00.2 `gyrate` quick-ref claims a per-residue mode that no longer exists [M]  ✅ RESOLVED (2026-09-11)
Files: `00-foundations/00.2-command-surface.md` (line 47)
The analysis table lists `gyrate` as "radius of gyration (overall + per-residue)".
In this build `gmx gyrate` has **no per-residue mode**: the full option set is
`-f -s -n -o -b -e -dt -tu -fgroup -xvg -[no]rmpbc -sf -selrpos -seltype -sel -mode`,
where `-mode` is only `mass`/`charge`/`geometry`. There is no `-res` flag (removed
in the 2022 analysis rewrite). The KB's own `01.8` (line 45) is correct: "overall
radius of gyration (no `-res` flag; use `-sel`/`-fgroup` to change the group)" —
so 00.2 is stale and self-contradictory.
**Recommended fix**: Change line 47 to "radius of gyration (overall; pick the group
with `-sel`/`-fgroup`; no per-residue mode in 2026.3)".

### I-58 00.2 `hbond` quick-ref claims lifetime + autocorrelation outputs that no longer exist [M]  ✅ RESOLVED (2026-09-11)
Files: `00-foundations/00.2-command-surface.md` (line 48)
The analysis table lists `hbond` as "hydrogen bonds (count, lifetime, autocorrelation)".
In this build `gmx hbond` writes `-o` (H-bond index `.ndx`), `-num` (count over time
`.xvg`), `-dist`, `-ang`, `-dan` — there is **no lifetime and no autocorrelation**
(`-ac` was removed in the 2022 rewrite; the tool now only defines bonds geometrically
and reports count/distance/angle). The KB's own `01.8` (line 53) is correct: "`-o`
writes the H-bond index file (`.ndx`) … `-num` for the H-bond count … `-dist`/`-ang`/`-dan`
… (No `-ac` flag.)" — so 00.2 is stale and self-contradictory.
**Recommended fix**: Change line 48 to "hydrogen bonds (count via `-num`, distance/
angle via `-dist`/`-ang`/`-dan`, bond index via `-o`; no lifetime/autocorrelation in
2026.3)".

### I-59 02.02 `genrestr -group` — flag does not exist; subset restraint is `-n index.ndx` [M]  ✅ RESOLVED (2026-09-11)
Files: `02-md-types/02.02-position-restraints.md` (line 21)
The recipe notes "`-group` to restrain a subset (e.g. backbone only)". This build's
`gmx genrestr` has **no `-group` flag**: the full option set is `-f -n -o -of -fc
-freeze -[no]disre -disre_dist -disre_frac -disre_up2 -cutoff -[no]constr`. To restrain
a subset you pass an index group with **`-n index.ndx`** (e.g. a backbone group built
with `gmx make_ndx`/`gmx select`).
**Recommended fix**: Replace "`-group` to restrain a subset (e.g. backbone only)" with
"`-n index.ndx` to restrain a subset (e.g. a backbone index group)".

### I-60 03.5 `nonbonded-benchmark -size 100000` is infeasible; `-size` is a 3000-atom multiplier, not an atom count [H]  ✅ RESOLVED (2026-09-11)
Files: `03-playbooks/03.5-performance.md` (lines 97, 101)
The benchmark command is `gmx nonbonded-benchmark -o bench.csv -size 100000 -nt 1
-simd auto` and the flag is described as "`-size <atoms>`". In this build `-size`
means **"The system size is 3000 atoms times this value"** (`gmx nonbonded-benchmark
-h`; identical in the `v2026.3` and `v2024.4` source:
`IntegerOption("size").store(&sizeFactor_).description("The system size is 3000 atoms
times this value")`). So `-size 100000` requests **300,000,000 atoms** — the command
cannot run (allocation failure / OOM). Confirmed live: `-size 1` prints "System
size: 3000 atoms" and produces a 3000-atom CSV row.
**Recommended fix**: Use a feasible multiplier (e.g. `-size 33` ≈ 99,000 atoms) and
correct the flag description to "`-size <multiplier>` (system = 3000 atoms × value)".

### I-61 01.8 tells users to type SELFLANG / bare group names into `make_ndx`, which rejects both [M]  ✅ RESOLVED (2026-09-11)
Files: `01-phases/01.8-analysis.md` (lines 14-15)
The text says: at the `make_ndx` prompt "type SELFLANG expressions (e.g. `resname PRO
and name CA`) or group names". This build's `gmx make_ndx` **does not parse SELFLANG**
(that is `gmx select`'s language) and **rejects bare group names**. Verified live:
typing `SOL` → `Syntax error: "SOL"`; typing `"SOL"` → `Copied index group 2 'SOL'`;
typing `resid < 10` → `Syntax error`. The real editor syntax (from in-editor `h`,
matching the `v2026.3` source `src/gromacs/tools/make_ndx.cpp`) is: bare number =
copy group by number; **quoted** name = copy group by name; `a`/`t`/`r`/`ri`/`res`/
`chain` = atom/type/residue selections; `!`/`&`/`|` = boolean; `name`/`del`/`keep`/
`case`/`splitres`/`splitch`/`splitat`/`l`/`q` = editor commands.
**Recommended fix**: Replace the SELFLANG/bare-name guidance with the actual command
syntax (e.g. `r PRO`, `a CA`, or `"Protein"` to copy an existing group) and note that
SELFLANG belongs to `gmx select`.

---

## Full-KB re-audit (2026-09-10) — I-57…I-61 still open; 2 new issues (I-62, I-63)

**Method:** all 35 KB content files re-read in full; full probe suite re-run in session
`work/kbval_2026-09-10/` (fingerprint `2026.3-dev-20260625-1210900-unknown`, 101 commands,
no KB drift since `df800cb`); 24 extracted MDP blocks re-parsed through `gmx grompp`
(all clean: unknown=0, invalid=0, obsolete=0 — remaining errors are known system noise:
gen-vel/continuation conflicts, AWH/pull, PME-no-charges, exit=139 on exotic types);
~90 targeted value probes for every prose-only claim (enums, removed options, defaults,
error strings). CPU-only grompp / tool probes — no MD run (GPU work forbidden).

**Status of the 2026-09-07 issues (I-57…I-61): all five are still open.** Their fixes
were never applied to the KB files — the stale text is still present and every claim was
re-verified against the build in this pass:

| Issue | Location | Re-verified 2026-09-10 |
|-------|----------|------------------------|
| I-57 | `00.2` line 47 (`gyrate` "overall + per-residue") | `gmx gyrate -h`: no `-res` flag; `-mode` is `mass`/`charge`/`geometry` only. Still stale. |
| I-58 | `00.2` line 48 (`hbond` "count, lifetime, autocorrelation") | `gmx hbond -h`: no `-ac`/lifetime; outputs are `-o -num -dist -ang -dan`. Still stale. |
| I-59 | `02.02` line 21 (`genrestr -group`) | `gmx genrestr -h`: no `-group` flag (flags are `-f -n -o -of -fc -freeze -disre …`). Still stale. |
| I-60 | `03.5` lines 97, 101 (`-size 100000`, `-size <atoms>`) | `gmx nonbonded-benchmark -h`: "The system size is 3000 atoms times this value". Still stale. |
| I-61 | `01.8` lines 14–15 (SELFLANG / bare names into `make_ndx`) | `make_ndx` rejects SELFLANG and bare names (verified 2026-09-07). Still stale. |

### I-62 01.7 `-pme ranks` — value does not exist; PME ranks are set with `-npme <N>` [M]  ✅ RESOLVED (2026-09-11)
Files: `01-phases/01.7-restart-parallelization.md` (line 75)
The parallelization table lists "`-pme` ranks | separate PME ranks (multi-node, large
systems)". In this build `mdrun -pme` is an enum with values **`auto, cpu, gpu` only**
(`gmx mdrun -h`); there is no `ranks` value — `mdrun -pme ranks` fails with
`Invalid enum 'ranks' for variable pme`. Separate PME ranks are controlled by the
separate flag **`-npme <int>`** ("Number of separate ranks to be used for PME, -1 is
guess", default -1). The `-pme ranks` form existed in older releases and was replaced
by `-npme`.
**Recommended fix**: Change the table row to "`-npme <N>` | dedicate N ranks to PME
(multi-node, large systems; default -1 = guess)" (optionally noting `-pme gpu` for the
GPU PME offload).

### I-63 00.6 `martini3` listed in the `pdb2gmx -ff` column although it is not a `-ff` value [L]  ✅ RESOLVED (2026-09-11)
Files: `00-foundations/00.6-force-fields-water.md` (line 20)
The coarse-grained table has the header "| FF | `pdb2gmx -ff` | Notes |" and puts
`martini3` in the `-ff` column. `martini3` is **not** a valid `pdb2gmx -ff` value in
this build — no `martini3.ff` ships under `share/gromacs/top/` (the all-atom FFs
amber99sb-ildn / amber14sb / amber19sb / oplsaa / charmm27 / gromos54a7 do), and the
row's own Notes column says "(via `ac`/`martini` tooling, not plain pdb2gmx)". The
inline note mitigates the contradiction, so this is cosmetic — but an agent copying the
column value into `pdb2gmx -ff martini3` gets a "force field not found" error.
**Recommended fix**: Move the value out of the `-ff` column, e.g. "| **Martini 3** |
— (not a `pdb2gmx -ff` value) | via `ac`/`martini` tooling; 4:1 mapping; see `02.12` |".

---

## Fix pass (2026-09-11 — build `2026.3-dev-20260625-1210900-unknown`)

**Scope:** 7 open issues (I-57…I-63) from the 2026-09-07 and 2026-09-10 audit sections.
**Result:** 7 fixed (I-62 incl. 1 straggler in `03.5`), 0 already-fixed, 0
false-positive, 0 left open.

#### I-57 00.2 `gyrate` quick-ref — FIXED  ✅ RESOLVED (2026-09-11)
Files: `00-foundations/00.2-command-surface.md`
- **Preflight**: `gmx gyrate -h` re-run — no `-res` flag; stale text still at line 47. Issue confirmed.
- **Applied**: `radius of gyration (overall + per-residue)` → `radius of gyration (overall; pick the group with `-sel`/`-fgroup`; no per-residue mode in 2026.3)`.
- **Evidence**: fresh `-h` (`kbval_2026-09-11/snapshot/02_help/gyrate.txt`): options `-f -s -n -o -b -e -dt -tu -fgroup -xvg -[no]rmpbc -sf -selrpos -seltype -sel -mode`; `-mode` = "Atom weighting mode: mass, charge, geometry" — no `-res`; `-sel`/`-fgroup` both present.

#### I-58 00.2 `hbond` quick-ref — FIXED  ✅ RESOLVED (2026-09-11)
Files: `00-foundations/00.2-command-surface.md`
- **Preflight**: `gmx hbond -h` re-run — outputs are only `-o`/`-num`/`-dist`/`-ang`/`-dan`; no `-ac`, no lifetime. Issue confirmed.
- **Applied**: `hydrogen bonds (count, lifetime, autocorrelation)` → `hydrogen bonds (count via `-num`, distance/angle via `-dist`/`-ang`/`-dan`, bond index via `-o`; no lifetime/autocorrelation in 2026.3)`.
- **Evidence**: fresh `-h` (`kbval_2026-09-11/snapshot/02_help/hbond.txt`): `-o [<.ndx>] (hbond.ndx)`, `-num [<.xvg>] (hbnum.xvg)`, `-dist`, `-ang`, `-dan` — all five present, no `-ac`.

#### I-59 02.02 `genrestr -group` — FIXED  ✅ RESOLVED (2026-09-11)
Files: `02-md-types/02.02-position-restraints.md`
- **Preflight**: `gmx genrestr -h` re-run — no `-group` flag. Issue confirmed.
- **Applied**: `- `-group` to restrain a subset (e.g. backbone only).` → `- `-n index.ndx` to restrain a subset (e.g. a backbone index group).`
- **Evidence**: fresh `-h` (`kbval_2026-09-11/snapshot/02_help/genrestr.txt`): flags `-f -n -o -of -fc -freeze -[no]disre -disre_dist -disre_frac -disre_up2 -cutoff -[no]constr` — no `-group`; `-n [<.ndx>] (index.ndx)` present.

#### I-60 03.5 `nonbonded-benchmark -size` — FIXED  ✅ RESOLVED (2026-09-11)
Files: `03-playbooks/03.5-performance.md`
- **Preflight**: `gmx nonbonded-benchmark -h` re-run — `-size <int> (1)` described as "The system size is 3000 atoms times this value". Issue confirmed.
- **Applied**: command `-size 100000` → `-size 33` (≈ 99,000 atoms); flag description `-size <atoms>` → `-size <multiplier>` (system = 3000 atoms × value).
- **Evidence**: fresh `-h` (`kbval_2026-09-11/snapshot/02_help/nonbonded-benchmark.txt`): `-size <int> (1)  The system size is 3000 atoms times this value`.

#### I-61 01.8 `make_ndx` editor syntax — FIXED  ✅ RESOLVED (2026-09-11)
Files: `01-phases/01.8-analysis.md`
- **Preflight**: interactive `gmx make_ndx -f /work/probe/box.gro` (5832-water SPC-E box) re-run with piped input: `resname PRO and name CA` → `Syntax error: "name PRO and name CA"`; bare `SOL` → `Syntax error: "SOL"`; quoted `"SOL"` → `Copied index group 2 'SOL'`; `r SOL` → `Found 17496 atoms with residue name SOL`; in-editor `h` confirms the syntax table (`a`/`r` name selections, `"name"` group copy, `!`/`&`/`|` booleans, `name`/`del`/`keep`/`case`/`split*`/`l`/`q` commands). Issue confirmed.
- **Applied**: "type SELFLANG expressions (e.g. `resname PRO and name CA`) or group names" → "use the editor syntax — `r PRO` / `a CA` select by residue/atom name, `"Protein"` (quoted) copies an existing group, `!`/`&`/`|` combine groups. SELFLANG expressions are rejected here — they belong to `gmx select`."
- **Evidence**: probe above (session dir `kbfix_2026-09-10/`, input `mkndx_probe.txt`, output captured in the fix session); every syntax token in the new text verified against the live in-editor help.

#### I-62 01.7 `-pme ranks` — FIXED  ✅ RESOLVED (2026-09-11)
Files: `01-phases/01.7-restart-parallelization.md` (+ straggler in `03-playbooks/03.5-performance.md`)
- **Preflight**: `gmx mdrun -h` re-run — `-pme <enum> (auto)  Perform PME calculations on: auto, cpu, gpu` (no `ranks`); `-npme <int> (-1)  Number of separate ranks to be used for PME, -1 is guess`. Issue confirmed.
- **Applied**: table row `- `-pme` ranks | separate PME ranks (multi-node, large systems).` → `- `-npme <N>` | dedicate N ranks to PME (multi-node, large systems; default -1 = guess)`. **Straggler**: the same stale claim also existed in `03.5` ("dedicate ranks to PME (`-pme` ranks)") — not in the issue's `Files:` list; fixed with the same verified text and noted here per the straggler convention.
- **Evidence**: fresh `-h` (`kbval_2026-09-11/snapshot/02_help/mdrun.txt`): `-pme` enum `auto, cpu, gpu`; `-npme <int> (-1)` present.

#### I-63 00.6 `martini3` in `-ff` column — FIXED  ✅ RESOLVED (2026-09-11)
Files: `00-foundations/00.6-force-fields-water.md`
- **Preflight**: install-tree listing re-run — no `martini3.ff` (no martini/`ac` FF of any kind). Issue confirmed.
- **Applied**: `| **Martini 3** | `martini3` (via `ac`/`martini` tooling, not plain pdb2gmx) | 4:1 mapping; different workflow (see `02.12`). |` → `| **Martini 3** | — (not a `pdb2gmx -ff` value) | via `ac`/`martini` tooling; 4:1 mapping; see `02.12`. |`
- **Evidence**: fresh FF listing (`kbval_2026-09-11/snapshot/03_ff_listing.txt`): top-level `.ff` dirs are amber03/14sb/19sb/94/96/99/99sb/99sb-ildn/GS, charmm27, gromos43a1/43a2/45a3/53a5/53a6/54a7 — no martini3.

## Notes for the auditor
- **Regression suite** (full re-run after all fixes, session `kbval_2026-09-11/`): 24 blocks probed, matrix re-parsed; block verdicts and matrix verdicts are **identical to the pre-fix baseline** (`kbval_2026-09-10/`) — zero new parse signals. The single parse signal, `block_013` (`03.1-decision-trees.md:93`, the decision-tree line `integrator = md, tcoupl = v-rescale, pcoupl = C-rescale   [2026]`), is pre-existing known false-positive class (c) ("single-line summary 'block' in playbooks"), unchanged since before the fix.
- **New-problem candidate (reported, not fixed)**: the `block_013` line above is decision-tree prose that the probe suite's block extractor picks up as an MDP option (it matches the `^[a-z][a-z0-9-]* =` pattern). False-positive class (c) covers it, but note the 2026-09-10 audit section states "all clean: unknown=0, invalid=0, obsolete=0", which is not literally true for `block_013` (it carries `invalid=1` in both the 09-10 and 09-11 runs). Consider rewording that line so it does not begin with `option = value`, or documenting it as a persistent suite-noise line. **Resolved (2026-09-11, same day):** the line was reworded to three individually backticked spans — `integrator = md` + `tcoupl = v-rescale` + `pcoupl = C-rescale` — so the block extractor no longer sees it and each span is now a separately verified matrix claim. Suite re-run: 23 blocks, zero parse signals, matrix unchanged.
- **Stale-text sweep** after the fix: grep for all seven stale patterns across the KB (excluding `issues_kb.md`) → no hits.

---

## Full-KB regression audit (2026-09-11, post-fix-pass) — build unchanged; 2 new issues (I-64, I-65)

**Method:** full probe suite re-run in session `work/kbval_2026-09-11/` (fingerprint
`2026.3-dev-20260625-1210900-unknown` — identical to the 2026-09-11 fix-pass gold standard;
`git diff` of the KB is empty since commit `c2088a1`). All 23 extracted MDP blocks clean
(unknown=0 invalid=0 obsolete=0); the 5 matrix "Unknown left-hand" hits (`nrexcl`, `fc`,
`expanded`, `lmc`, `type`) re-confirmed as documented false positives (topology/pull
directives + removed-option changelog). All seven fix-pass text changes (I-57…I-63) verified
present in the 7 touched files. Every prose-only claim re-verified with targeted CPU-only
`gmx grompp` probes (rounds r4–r18 under `work/kbval_2026-09-11/targeted/`, 1-atom dummy
system + `assets/base.mdp`): integrator/thermostat enums, LMC/FEP/AWH/Colvars/FMM/DGS/
electric-field options, the 00.5 removal list, the full pull-code API (02.04/02.07),
sd/bd Langevin/Brownian (02.08), annealing (02.09), qmmm/nnpot (02.10/02.11), the
`[ system ]` requirement (00.4/01.2), the `.tng` read path (00.3), the tool list
(00.2, 79 tools), and the 01.9 error catalog (strings checked against the build binary
and the v2026.3 source tree). No MD runs (GPU work forbidden).

### I-64 02.06 `lmc-gibbsdelta` described as a real-valued λ step size; the build requires an integer [M]  ✅ RESOLVED (2026-09-11)
Files: `02-md-types/02.06-expanded-ensemble-replica-exchange.md` (line 42)
The LMC option table has "| `lmc-gibbsdelta` | Gibbs move step size in λ. |". In this build
`lmc-gibbsdelta` is an **integer** — the number of neighboring λ states considered for Gibbs
sampling — not a real-valued step size in λ. Setting a fractional value fails grompp:
**Build evidence**: probe `lmc-gibbsdelta = 0.01` (in an otherwise valid LMC block) →
`ERROR: Right hand side '0.01' for parameter 'lmc-gibbsdelta' in parameter file is not an
integer value` (`work/kbval_2026-09-11/targeted/lmc_misc2.log`); `lmc-gibbsdelta = 2` parses
clean (only expected dummy-system noise). The v2026.3 source reads it as an int with default
-1: `readir.cpp:2214 expand->gibbsdeltalam = get_eint(inp, "lmc-gibbsdelta", -1, wi);`
(a positive value limits exchanges to states ±N; -1 = all states).
**Recommended fix**: reword the table row to "| `lmc-gibbsdelta` | integer; limits Gibbs
sampling to states within ±N of the current one (default -1 = all states). |".

### I-65 01.9 troubleshooting catalog cites 8 error strings that do not exist in this build [L]  ✅ RESOLVED (2026-09-11)
Files: `01-phases/01.9-troubleshooting.md` (lines 16, 33, 38, 54, 55, 59, 61, 63)
The catalog is explicitly a literal error → cause/fix mapping ("GROMACS errors are
descriptive — read them literally, then use this catalog"). Eight of its quoted strings do
not occur in this build (verified with `strings` on `libgromacs.so` and cross-checked
against the v2026.3 source tree; build is `2026.3-dev-20260625`):

**Check no longer exists (the error cannot occur):**

| KB string (line) | Build status |
|---|---|
| `T-Coupling group XXX has fewer than 10% of the atoms` (33) | absent — no such check in build or source; the closest output is the NOTE `Number of degrees of freedom in T-Coupling group %s is %.2f` |
| `Can not do Conjugate Gradients with constraints` (59) | absent — no such check; probe `integrator = cg` + `constraints = h-bonds` → grompp exit=0 |
| `Range Checking error` (61) | absent from build binary and source |
| `A line longer than 4095 characters` (38) | absent from build binary and source |

**Event still occurs, but the message was reworded (quoted string is not greppable):**

| KB string (line) | Current build message |
|---|---|
| `Stepsize too small, or no change in energy. Converged to machine precision` (54) | "…the algorithm tried to make a new step whose size was too small, or there was no change in the energy… converged to within the available machine precision" |
| `force on at least one atom is not finite` (55) | `At step %d detected non-finite forces on %td atoms` |
| `A charge group moved too far between two domain decomposition steps` (63) | `One or more atoms moved too far between two domain decomposition steps.` |
| `Long bonds and/or missing atoms` (16) | `Long Bond (%d-%d = %g nm)` + `There were %d missing atoms in molecule %s` |

**Recommended fix**: for the four gone entries — delete the row or reword it to describe
current behavior (e.g. the 10% row: "small T-coupling groups only produce a degrees-of-freedom
NOTE; merge small groups for stable thermostating"); for the four reworded entries — update
the quoted string to the current message text (or a greppable substring such as
`converged to within the available machine precision`).

**Fix deviation (2026-09-11, fix pass):** the preflight corrected the audit's
4-gone/4-reworded split — against the build (gold standard), only 2 of the 8
entries are truly gone (10%-of-atoms tc-group check; CG+constraints check), 4
are reworded (long-bond/missing-atoms, 4095-char line, EM machine-precision,
DD moved-too-far), and 2 are actually valid (`force on at least one atom is not
finite` is a verbatim substring of the build's EM message; `Range checking
error` exists, the KB quote was off by one capital). The audit's "4095 NOT-IN-BUILD"
and "Range Checking ABSENT" results were false negatives: the 4095 message is a
`%d` format string (`An input file contains a line longer than %d characters,
while the buffer passed to fgets2 has size %d.` — reproduced live with a
5000-char line, `work/kbfix_2026-09-11/longline.log`), and the Range-checking
message is lowercase-c. Applied the corrected variant: 7 lines changed, line 55
untouched.

---

## Fix pass (2026-09-11, post-audit — build `2026.3-dev-20260625-1210900-unknown`)

**Scope:** 2 open issues (I-64, I-65) from the 2026-09-11 post-fix-pass regression audit.
**Result:** 2 fixed, 0 already-fixed, 0 false-positive, 0 left open.

#### I-64 02.06 `lmc-gibbsdelta` described as a real-valued λ step size; the build requires an integer [M] — FIXED  ✅ RESOLVED (2026-09-11)
Files: `02-md-types/02.06-expanded-ensemble-replica-exchange.md`
- **Preflight**: stale text present at line 42. Re-probes (session `work/kbfix_2026-09-11/`): `lmc-gibbsdelta = 0.01` (in a minimal LMC block) → `ERROR 1 [file i64_frac.mdp, line 11]: Right hand side '0.01' for parameter 'lmc-gibbsdelta' in parameter file is not an integer value`; `lmc-gibbsdelta = 2` parses clean (only expected dummy-system noise). Issue confirmed.
- **Applied**: `Gibbs move step size in λ.` → `integer; limits Gibbs sampling to states within ±N of the current one (default -1 = all states).`
- **Evidence**: integer requirement verbatim from the preflight probe above; semantics + default from the 2026.3 manual (manual.gromacs.org/2026.3/user-guide/mdp-options.html): "(-1) Limit Gibbs sampling to selected numbers of neighboring states. … A positive value of `lmc-gibbsdelta` means that only states plus or minus `lmc-gibbsdelta` are considered in exchanges up and down. A value of -1 means that all states are considered." — matching the v2026.3 source `readir.cpp:2214 get_eint(inp, "lmc-gibbsdelta", -1, wi)` (int, default -1).

#### I-65 01.9 troubleshooting catalog cites 8 error strings that do not exist in this build [L] — FIXED  ✅ RESOLVED (2026-09-11)
Files: `01-phases/01.9-troubleshooting.md` (+ 6 stragglers in `01.1`, `01.4` ×2, `01.5`, `01.6`, `01.7` — see Notes)
- **Preflight**: all 8 lines located. Re-probes (session `work/kbfix_2026-09-11/`) re-ran the audit's binary checks and corrected its 4-gone/4-reworded split to 2-gone/4-reworded/2-valid (details in the Fix deviation note on the issue): `force on at least one atom is not finite` is IN the build (EM message "Energy minimization has stopped because the force on at least one atom is not finite. This usually means atoms are overlapping…"); `Range checking error` is IN the build (lowercase c; plus "Range checking error (possible bug)"); the 4095-char line error was reproduced live with a 5000-char `.top` line → `An input file contains a line longer than 4095 characters, while the buffer passed to fgets2 has size 4095. The line starts with: '/* xxxxxxxxxxxxxxxxx'`; `cg` + `constraints = h-bonds` re-probed → grompp exit=0 (check truly gone); `T-Coupling group … fewer than 10%` absent (closest build output: NOTE `Number of degrees of freedom in T-Coupling group %s is %.2f`).
- **Applied** (01.9, 7 lines): 16 `Long bonds and/or missing atoms` → `Long Bond (N-N = X nm)` / `missing atoms in molecule X`; 33 `T-Coupling group XXX has fewer than 10% of the atoms` → `Number of degrees of freedom in T-Coupling group X is N` (NOTE; the old "fewer than 10% of the atoms" error is gone in 2026.3); 38 `A line longer than 4095 characters` → `An input file contains a line longer than 4095 characters`; 54 `Stepsize too small, or no change in energy. Converged to machine precision` → `converged to within the available machine precision`; 59 `Can not do Conjugate Gradients with constraints` → suffixed "— no longer emitted (gone in 2026.3; `cg` + constraints is accepted)", Fix column → "None — the combination is valid now."; 61 `Range Checking error` → `Range checking error` (capitalization); 63 `A charge group moved too far between two domain decomposition steps` → `One or more atoms moved too far between two domain decomposition steps`. Line 55 left unchanged (verified present in the build).
- **Evidence**: every new quoted string verified verbatim against `libgromacs.so` (`strings`): "Long Bond", "There were %d missing atoms in molecule", "Number of degrees of freedom in T-Coupling group", "An input file contains a line longer than %d characters, while the buffer passed to fgets2 has size %d", "converged to within the available machine precision", "One or more atoms moved too far between two domain decomposition steps", "Range checking error"; CG+constraints acceptance from the re-probe (exit=0, `work/kbfix_2026-09-11/i65_cg.log`).
- **Deviation**: see the Fix deviation note on the issue — the audit's "gone" classification was wrong for the 4095-char and Range-checking rows (format-string / case false negatives) and its "reworded" classification was wrong for the force-not-finite row (verbatim in the build); 7 lines changed instead of 8, line 55 untouched.

## Notes for the auditor
- **Stragglers** (same stale claims outside the issue's `Files:` list; fixed with the same verified text, per project convention): `01.1-structure-preparation.md:46` (`Long bonds and/or missing atoms`), `01.4-energy-minimization.md:57` (`Stepsize too small, …`) and `:67` (`Can not do Conjugate Gradients with constraints`), `01.5-equilibration.md:123` (`T-Coupling group XXX has fewer than 10% …`), `01.6-production.md:89` (`Range Checking error` capitalization), `01.7-restart-parallelization.md:112` (`A charge group moved too far …`). Post-fix stale-text sweep: clean — remaining hits are the intentional "gone in 2026.3" annotations (false-positive class (b)).
- **Regression suite** (re-run after all edits, session `kbval_2026-09-11/`): 23 blocks probed; `03_block_verdicts.txt` and `03_matrix_verdicts.txt` are **byte-identical to the pre-fix baseline** — zero new parse signals.
- **Method note for the next audit**: binary `strings` checks for error messages must account for (a) format arguments — a message like "…longer than %d characters…" will not match a grep for the rendered number (4095), and (b) case — "Range checking error" ≠ "Range Checking error". Prefer grepping a stable word fragment (e.g. "longer than", "Range checking") over the full rendered string.
- **Build vs. release tag**: the EM message "Energy minimization has stopped because the force on at least one atom is not finite…" is present in the build binary but absent from the v2026.3 source tag — the dev snapshot and the release tag differ in places; the build remains the gold standard, the tag is only supplementary.
- **Tag-only string sweep (2026-09-11, post-fix-pass, at user request)**: the 17 remaining 01.9 catalog strings that had been verified only against the v2026.3 source tag ("Pressure scaling more than", "assigned multiple times", "no domain decomposition", "Invalid order for directive", "second defaults directive", "non-zero total charge", "Incorrect number of parameters", "does not match topology", "No such moleculetype", "non-matching atom names", "not found in residue topology database", "is missing in residue", "not found in rtp entry", "No force fields found", "non-sequential", "out of bounds", "Invalid line in") were re-verified against the build binary via stable-fragment `strings` grep — **all IN-BUILD, no new issues**. The audit skill's Step 3 now carries an error-string verification bullet (reproduce-first; fragment + case-aware `strings` as fallback) to prevent format-argument/case false negatives recurring.

---

## New issues from full-KB regression audit (2026-09-13)

**Method:** full-KB regression pass against the unchanged build `2026.3-dev-20260625-1210900-unknown` (fingerprint identical to the 2026-09-11 gold standard — no drift). Probe suite re-run (session `work/kbval_2026-09-13/`): 101 commands, 23 MDP blocks re-probed, 35-file option matrix re-extracted. `03_block_verdicts.txt` and `03_matrix_verdicts.txt` are **byte-identical to the 2026-09-11 baseline** (zero parse signals; the 5 known matrix false positives persist). Every KB file re-read; semantic claims not captured by the mechanical probes were cross-checked with targeted CPU-only `gmx grompp` probes (session `work/kbval_2026-09-13/targeted/`) and `strings` on `/usr/local/gromacs/lib/libgromacs.so`. No MD run, no GPU (CPU-only grompp/strings/tool probes). The uncommitted KB diff exactly matches the documented 2026-09-11 fix-pass edits for I-64/I-65 + stragglers, so this run was treated as a regression pass; it re-confirmed I-64/I-65 are still in place and found new stragglers the fix pass missed (I-66, I-67, I-69) plus one ongoing inaccuracy (I-68).
**Result:** 4 new issues (I-66…I-69), all confirmed real against the build.

### I-66 Three troubleshooting error strings are quoted with wording the build does not emit  [L]  ✅ RESOLVED (2026-09-13)
Files: `01-phases/01.1-structure-preparation.md`, `01-phases/01.2-topology-forcefield.md`, `01-phases/01.6-production.md`, `01-phases/01.9-troubleshooting.md`
- **PME node → PME rank.** KB `01.6:89` and `01.9:62` quote `X particles communicated to PME node Y ... out of the domain decomposition cell`. The build emits `"%zd particles communicated to PME rank %d out of the domain decomposition cell"` — the word is **rank**, not node (`strings` on `libgromacs.so`).
- **was used → is used.** KB `01.1:47` and `01.9:17` quote `Chain identifier 'X' was used in two non-sequential blocks`. The build emits `"Chain identifier '%c' is used in two non-sequential blocks."` — **is used**, not *was used*.
- **second defaults directive file → second defaults directive.** KB `01.2:60` and `01.9:27` quote `Found a second defaults directive file`. The build emits `"Found a second defaults directive."` — no "file".
**Recommended fix**: in each listed location, replace the quoted string with the build's wording: `PME node` → `PME rank` (01.6:89, 01.9:62); `was used in two non-sequential blocks` → `is used in two non-sequential blocks` (01.1:47, 01.9:17); `Found a second defaults directive file` → `Found a second defaults directive` (01.2:60, 01.9:27).

### I-67 01.4 still claims `cg` cannot be used with constraints, contradicting the build and its own I-65 fix  [M]  ✅ RESOLVED (2026-09-13)
Files: `01-phases/01.4-energy-minimization.md`
- KB `01.4:41` says `cg` "**cannot be used with constraints** (no SETTLE/LINCS)" and `01.4:52` says "`cg` requires no constraints". Both contradict `01.4:66` (updated by the I-65 fix pass): "`Can not do Conjugate Gradients with constraints` — no longer emitted (gone in 2026.3; `cg` + constraints is accepted)".
- Build: `integrator = cg` + `constraints = h-bonds` → `gmx grompp` **exit=0** (accepted; `work/kbval_2026-09-13/targeted/cg_hb.log`). The I-65 fix pass updated the catalog (`01.9:59`) and `01.4:66` but left the two stale claims at `01.4:41` and `01.4:52`.
**Recommended fix**: `01.4:41` — `Faster near the minimum; **cannot be used with constraints** (no SETTLE/LINCS). Used before normal-mode analysis.` → `Faster near the minimum; **constraints are allowed** (the old "Can not do Conjugate Gradients with constraints" check is gone in 2026.3). Used before normal-mode analysis.`; `01.4:52` — `cg requires no constraints.` → `cg may use constraints (no longer rejected in 2026.3).`

### I-68 MTTK requirement misstated: it needs Nose-Hoover temperature control, and constraints are allowed  [M]  ✅ RESOLVED (2026-09-13)
Files: `00-foundations/00.5-mdp-anatomy.md`, `01-phases/01.5-equilibration.md`, `02-md-types/02.01-standard-ensembles.md`
- KB `00.5:82-83` (`MTTK (deprecated — requires md-vv and no constraints)`), `01.5:86` (`requires integrator = md-vv and no constraints`), and `02.01:21` (`MTTK requires no constraints`) all state MTTK requires **no constraints**.
- Build: MTTK + `tcoupl = v-rescale` (no Nose-Hoover) → `grompp` exit=1, `"Cannot do MTTK pressure coupling without Nose-Hoover temperature control"`. MTTK + `tcoupl = nose-hoover` + `integrator = md-vv` + `constraints = h-bonds` → **exit=0** (only the deprecation NOTE `MTTK coupling is deprecated and will soon be removed`; `work/kbval_2026-09-13/targeted/mttk_vv_hb.log`). MTTK + `nose-hoover` + `integrator = md` (not md-vv) → exit=1, `"leapfrog does not yet support Nose-Hoover chains, nhchainlength reset to …"` — so the operative requirement is **Nose-Hoover temperature control** (which in turn forces `md-vv`), and **constraints are allowed**, not forbidden.
**Recommended fix**: in all three files, replace the "requires `md-vv` and no constraints" / "requires no constraints" wording with: MTTK requires **Nose-Hoover temperature control** (`tcoupl = nose-hoover`, which requires `integrator = md-vv`); **constraints are allowed**. E.g. `01.5:86` → `**Deprecated** (use C-rescale / PR); requires **Nose-Hoover temperature control** (`tcoupl = nose-hoover` + `integrator = md-vv`); constraints are allowed.`

### I-69 "Coupling/annealing a tiny tc-group → grompp error" is stale — it is now a NOTE  [L]  ✅ RESOLVED (2026-09-13)
Files: `01-phases/01.5-equilibration.md`, `02-md-types/02.01-standard-ensembles.md`, `02-md-types/02.09-simulated-annealing.md`
- KB `01.5:50` (`Never couple a tiny group (<10 % of atoms) to its own bath → grompp error`), `02.01:59` (`Coupling a tiny group to its own bath (<10 % of atoms) → grompp error`), and `02.09:63` (`Annealing a group with too-small a bath (<10 % of atoms) → grompp error`) all claim a tiny temperature-coupling group is rejected by `grompp`.
- Build: the old `"T-Coupling group … has fewer than 10% of the atoms"` error is **absent** (`strings` count=0 on `libgromacs.so`). The current output is a NOTE: `"Number of degrees of freedom in T-Coupling group %s is %.2f"`. The I-65 fix pass updated the catalog (`01.9:33`) and `01.5:123` (both now say "the old 'fewer than 10%' error is gone") but left these three prose claims still saying "→ grompp error".
**Recommended fix**: in `01.5:50`, `02.01:59`, and `02.09:63`, replace `→ grompp error` (and the `<10 % of atoms` framing) with the current behavior. E.g. `01.5:50` → `Never couple a tiny group to its own bath — grompp only emits a degrees-of-freedom NOTE (`Number of degrees of freedom in T-Coupling group X is N`); merge small groups for stable thermostating.` (same wording in `02.01:59` and `02.09:63`).

## Verified OK (this pass)
- **README.md** + **00.1–00.6**: version/build flags (TNG/Colvars/Plumed on; CP2K/Torch off), 101 tools, removed/renamed tools (`gmx check -s1`, `gmx nonbonded-benchmark`; no `benchmark`/`pmx`/`g_wham`/`make_ndx`/`insert-molecules`), GMX env vars (no `GMX_ENABLE_GPU_TIMING`; `GMX_GPU_*` set), MDP enums (integrator/tcoupl/pcoupl/constraints/dt), FF/water models, no bundled sample MDP.
- **01.1–01.9**, **02.01–02.14**, **03.1–03.5**: all option names, enums, and workflow claims re-verified except the specific lines in I-66/I-67/I-68/I-69. Spot-checks confirmed: `free-energy`/`sc-function`/`mts-level2-forces`/`nnpot-embedding` enums, `bd`+`bd-fric`, `sd`/`bd` tc-group requirement + "Invalid T coupling input" / "not part of any of the %s groups" messages, NNPot LibTorch error string + `nnpot-mm-group`/`nnpot-nnp-charge` "Unknown left-hand", QMMM CP2K-disabled, `md-vv-avek` validation warning, MTS options parse, `nonbonded-benchmark` flags.
- **MDP blocks**: all 23 blocks re-probed — zero parse signals (byte-identical to the 2026-09-11 baseline).
- **Option matrix**: 35 files re-extracted — only the 5 known false positives (topology/pull `nrexcl`/`fc`/`type`; removed-option changelog `expanded`/`lmc`).
- **I-64 / I-65 fixes still in place**: `lmc-gibbsdelta` integer requirement re-confirmed (fractional → `is not an integer value`); all I-65 reworded/gone error strings re-confirmed (Long Bond, missing atoms, machine precision, degrees-of-freedom NOTE, Range checking, moved-too-far, 4095-char line, CG+constraints acceptance).

## Notes
- **Build drift**: none — fingerprint `2026.3-dev-20260625-1210900-unknown` is identical to the 2026-09-11 gold standard; no re-baseline needed.
- **Fix-pass stragglers**: the I-65 fix pass's "Post-fix stale-text sweep: clean" note was incomplete. It missed `01.4:41`/`01.4:52` (cg+constraints, now I-67), `01.5:50`/`02.01:59`/`02.09:63` (tiny tc-group, now I-69), and the PME-node / was-used / second-defaults quote discrepancies (now I-66). The MTTK requirement (I-68) predates the fix pass and was never accurate.
- **All four issues are CPU-verified** (targeted `gmx grompp` probes in `work/kbval_2026-09-13/targeted/` + `strings` on `libgromacs.so`); none requires GPU.
- **Handoff**: this section is the fixer's work list (I-66…I-69). All are mechanical text edits with the verified replacement text given in each Recommended fix.

## Fix pass (2026-09-13 — build 2026.3-dev-20260625-1210900-unknown)

**Scope:** 4 open issues (I-66…I-69) from the 2026-09-13 audit section.
**Result:** 4 fixed, 0 already-fixed, 0 false-positive, 0 left open.

#### I-66 Three troubleshooting error strings are quoted with wording the build does not emit — FIXED  ✅ RESOLVED (2026-09-13)
Files: `01-phases/01.1-structure-preparation.md`, `01-phases/01.2-topology-forcefield.md`, `01-phases/01.6-production.md`, `01-phases/01.9-troubleshooting.md`
- **Preflight**: re-ran `strings` on `libgromacs.so` for all three quoted strings — all three KB wordings confirmed absent, all three build wordings confirmed present. Issue still real.
- **Applied**: `PME node` → `PME rank` (01.6:89, 01.9:62); `was used in two non-sequential blocks` → `is used in two non-sequential blocks` (01.1:47, 01.9:17); `Found a second defaults directive file` → `Found a second defaults directive` (01.2:60, 01.9:27).
- **Evidence** (verbatim `strings` on `libgromacs.so`):
  - `Chain identifier '%c' is used in two non-sequential blocks. They will be treated as separate chains unless you reorder your file.`
  - `%zd particles communicated to PME rank %d are more than 2/3 times the cut-off out of the domain decomposition cell of their charge group in dimension %c.`
  - `Found a second defaults directive.`

#### I-67 01.4 still claims `cg` cannot be used with constraints — FIXED  ✅ RESOLVED (2026-09-13)
Files: `01-phases/01.4-energy-minimization.md` (+ sweep straggler `03-playbooks/03.2-mdp-templates.md`)
- **Preflight**: re-ran `gmx grompp` with `integrator = cg` + `constraints = h-bonds` → exit=0 (accepted); the old `Conjugate Gradients with constraints` error string is absent from `libgromacs.so`. Issue still real.
- **Applied**: `01.4:41` `**cannot be used with constraints** (no SETTLE/LINCS)` → `**constraints are allowed** (the old "Can not do Conjugate Gradients with constraints" check is gone in 2026.3)`; `01.4:52` `cg requires no constraints.` → `cg may use constraints (no longer rejected in 2026.3).`; sweep straggler `03.2:16` — removed `(no constraints)` from the cg/l-bfgs comment (verified `l-bfgs` + `h-bonds` → exit=0 with `-maxwarn 5`).
- **Evidence** (verbatim `grompp`, `work/kbfix_2026-09-13/`):
  - `i67_cg_hb`: `gmx grompp -f i67_cg_hb.mdp -c tmin.gro -p tmin.top -o i67_cg_hb.tpr` → exit=0, TPR generated; `turning H bonds into constraints...`
  - `i67_lbfgs_chk`: `gmx grompp -f i67_lbfgs_chk.mdp … -o i67_lbfgs_chk.tpr -maxwarn 5` → exit=0, TPR generated (only an unrelated BFGS/switch WARNING).

#### I-68 MTTK requirement misstated — FIXED  ✅ RESOLVED (2026-09-13)
Files: `00-foundations/00.5-mdp-anatomy.md`, `01-phases/01.5-equilibration.md`, `02-md-types/02.01-standard-ensembles.md`
- **Preflight**: re-ran the full MTTK probe matrix (a–d, all with `compressibility = 4.5e-5`) — confirmed the operative requirement is Nose-Hoover temperature control (which forces `md-vv`), and constraints are allowed. Issue still real.
- **Applied** (all three files): `requires md-vv and no constraints` / `requires no constraints` → `requires Nose-Hoover temperature control (tcoupl = nose-hoover), which needs md-vv; constraints allowed`.
- **Evidence** (verbatim `grompp`, `work/kbfix_2026-09-13/`):
  - `i68_c` (`md-vv` + MTTK + `nose-hoover` + `h-bonds`) → exit=0, TPR generated; `NOTE 1: MTTK coupling is deprecated and will soon be removed` + `turning H bonds into constraints...`
  - `i68_a` (`md-vv` + MTTK + `v-rescale`) → exit=1: `Cannot do MTTK pressure coupling without Nose-Hoover temperature control`
  - `i68_d` (`md` + MTTK + `nose-hoover`) → exit=1: `MTTK pressure coupling requires a Velocity-verlet integrator`

#### I-69 "Coupling/annealing a tiny tc-group → grompp error" is stale — FIXED  ✅ RESOLVED (2026-09-13)
Files: `01-phases/01.5-equilibration.md`, `02-md-types/02.01-standard-ensembles.md`, `02-md-types/02.09-simulated-annealing.md`
- **Preflight**: re-ran `gmx grompp` with a 1-atom `System` tc-group (`md-vv` + `v-rescale` + `tc-grps = System` + `nsttcouple = 0`) → exit=0; the old "fewer than 10% of the atoms" error is absent from `libgromacs.so`; the degrees-of-freedom line is present. Issue still real.
- **Applied** (all three files): replaced `→ grompp error` (and the `<10 % of atoms` framing) with the verified behavior — `grompp` no longer errors (old "fewer than 10% of the atoms" check gone); it only prints the degrees-of-freedom NOTE; merge small groups. Consistent with the already-corrected catalog entries at `01.9:33` / `01.5:124`.
- **Evidence** (verbatim `grompp`, `work/kbfix_2026-09-13/i69b.log`):
  - `gmx grompp -f i69b.mdp -c tmin.gro -p tmin.top -o i69b.tpr` → exit=0, TPR generated
  - `Number of degrees of freedom in T-Coupling group System is 0.00` (plain log line printed right after 1-4 generation; no NOTE/WARNING/ERROR, no rejection)
  - `strings libgromacs.so | grep "fewer than 10"` → absent (old error gone)

## Notes for the auditor
- **I-69 fix-text correction during the pass**: an intermediate edit described the tiny-tc-group behavior as "accepted silently"; a re-probe showed `grompp` actually prints the degrees-of-freedom line (`Number of degrees of freedom in T-Coupling group System is 0.00`), so the final text matches the audit's recommended fix (DoF NOTE + merge small groups). The line is a plain log line (not a `NOTE`-prefixed message), but the KB's established convention (`01.9:33`, `01.5:124`) calls it a "NOTE", so the fix follows that convention.
- **Regression suite**: 23 blocks re-probed — zero parse signals (`unknown=invalid=obsolete=0` for all); matrix verdicts byte-identical to the pre-fix baseline (only the 5 known false positives). Block source ranges in `01.5` shifted +2 lines from the I-69 edit (benign; all verdict fields unchanged).
- **Straggler found and fixed as part of the pass**: `03.2:16` "(no constraints)" on cg/l-bfgs (I-67 sweep).
- **All four issues CPU-verified** (targeted `gmx grompp` probes in `work/kbfix_2026-09-13/` + `strings` on `libgromacs.so`); none required GPU.
- **Drift gate**: live `gmx --version` = `2026.3-dev-20260625-1210900-unknown`, identical to the 2026-09-11 gold standard; no re-baseline needed.

## New issues from full-KB regression audit (2026-09-14)

**Method:** All 35 KB files (00.1–00.6, 01.1–01.9, 02.01–02.14, 03.1–03.5, README) re-read and mapped to the probe snapshot. Probe suite re-run (101 commands, 23 MDP blocks → `unknown=invalid=obsolete=0` across the board; matrix verdicts byte-identical to the `kbval_2026-09-13` baseline — only the 5 known false positives). All 60 referenced CLI tools re-verified present in the build; the 21 "absent" names re-confirmed as documented removals/renames or prose placeholders. ~60 targeted `gmx grompp` probes (dummy 1-atom topology + `assets/base.mdp`) under `work/kbval_2026-09-14/targeted/` covering every enum / removed-option / error-string claim not covered by the suite; `strings` on `libgromacs.so` for every quoted error message in the `01.9` catalog and elsewhere; `gmx dump` on TPRs for default values (`rtpi = 0.05`) and silent no-op checks (`annealing = group`). CPU-only grompp/tool probes — no `mdrun` (eGPU in use).
**Result:** 7 new issues (I-70…I-76), all confirmed real against the build.

### I-70 `1-4 interaction not within cut-off` quote is not greppable  [L]  ✅ RESOLVED (2026-09-14)
Files: `01-phases/01.6-production.md`, `01-phases/01.9-troubleshooting.md`, `03-playbooks/03.4-failure-diagnosis.md`
The KB quotes the blow-up error as `1-4 interaction not within cut-off` (01.6:84, 01.9:57, 03.4:31). The build's message is `1-4 (%d,%d) interaction not within cut-off! r=%g. Ignored` — the atom-pair `(%d,%d)` sits between `1-4` and `interaction`, so the quoted string is not a contiguous substring of the real log line. A user following the catalog's "read them literally" rule and grepping the log for `1-4 interaction not within cut-off` finds nothing.
**Evidence** (verbatim `strings` on `libgromacs.so`):
- `1-4 (%d,%d) interaction not within cut-off! r=%g. Ignored`
**Recommended fix**: in all three files replace the quote with the real pattern, e.g. `1-4 (i,j) interaction not within cut-off! r=… Ignored` (or keep the exact format string `1-4 (%d,%d) interaction not within cut-off! r=%g. Ignored`).

### I-71 `qmmm = yes` is "gone" but the build still recognizes it  [L]  ✅ RESOLVED (2026-09-14)
Files: `02-md-types/02.10-qmmm.md`, `00-foundations/00.5-mdp-anatomy.md`
02.10:24 says "(the old `qmmm = yes` option is gone)"; 00.5:43 says "**Old flat `qmmm`/`qmmm-*` names are gone**". In this build the flat `qmmm-*` options really are gone (`Unknown left-hand`), but the bare `qmmm` boolean is still recognized: `qmmm = yes` does not produce `Unknown left-hand` — it hard-errors with a dedicated message. In this KB's own terminology (01.9: `Unknown left-hand … option name removed/renamed`), "gone" is inaccurate for `qmmm`.
**Evidence** (verbatim `gmx grompp`, `work/kbval_2026-09-14/targeted/b/`):
- `e02_qmmm.mdp` (`qmmm = yes`) → exit=1: `ERROR 1 [file e02_qmmm.mdp]: The QMMM integration you are trying to use is no longer supported`
- `e03_qmmmg.mdp` (`qmmm-group = QM`) → `WARNING 1 [file e03_qmmmg.mdp, line 6]: Unknown left-hand 'qmmm-group' in parameter file`
**Recommended fix**: 02.10:24 → "(the old `qmmm = yes` option is no longer usable — the build still recognizes it but hard-errors with `The QMMM integration you are trying to use is no longer supported`)"; 00.5:43 → "**Old flat `qmmm-*` names are gone (`Unknown left-hand`); bare `qmmm` is still recognized but hard-errors (`The QMMM integration you are trying to use is no longer supported`); the module prefix is `qmmm-cp2k-`.**"

### I-72 rtp-entry error quote omits `was` and the in-residue atom number  [L]  ✅ RESOLVED (2026-09-14)
Files: `01-phases/01.9-troubleshooting.md`
01.9:19 quotes `Atom X in residue YYY not found in rtp entry`. The build's message is `Atom %s in residue %s %d was not found in rtp entry %s with %d atoms` — with the placeholders filled in, the KB quote is not a substring of the real line (the build inserts the in-residue atom number `%d` after the residue name and uses `was not found`).
**Evidence** (verbatim `strings` on `libgromacs.so`):
- `Atom %s in residue %s %d was not found in rtp entry %s with %d atoms`
**Recommended fix**: 01.9:19 → `Atom X in residue YYY N was not found in rtp entry Z with M atoms` (or the exact format string).

### I-73 position-restraints out-of-bounds quote drops the parentheses  [L]  ✅ RESOLVED (2026-09-14)
Files: `01-phases/01.9-troubleshooting.md`
01.9:28 quotes `Atom index n in position_restraints out of bounds`. The build's message is `Atom index (%d) in %s out of bounds (1-%d).` — the index is parenthesized and a `(1-N)` range follows, so the quoted form does not match the log line. The adjacent catalog line for bonds keeps the full form (`Atom index (1) in bonds out of bounds (1-0)`), so this entry is also internally inconsistent with its neighbor.
**Evidence** (verbatim `strings` on `libgromacs.so`):
- `Atom index (%d) in %s out of bounds (1-%d).`
**Recommended fix**: 01.9:28 → `Atom index (n) in position_restraints out of bounds (1-N)`.

### I-74 residue-database error quote omits `type`  [L]  ❌ FALSE POSITIVE (2026-09-14 — closed by fix pass)
Files: `01-phases/01.9-troubleshooting.md`
01.9:15 quotes `Residue 'XXX' not found in residue topology database`. The build's message is `Residue type '%s' not found in residue topology database` — the word `type` is missing from the KB quote, so a literal grep of the quoted form fails.
**Evidence** (verbatim `strings` on `libgromacs.so`):
- `Residue type '%s' not found in residue topology database`
**Recommended fix**: 01.9:15 → `Residue type 'XXX' not found in residue topology database`.

### I-75 short T-coupling-group quote is not greppable  [L]  ✅ RESOLVED (2026-09-14)
Files: `02-md-types/02.08-langevin-brownian.md`, `03-playbooks/03.2-mdp-templates.md`
02.08:34 and 03.2:290 quote the abort as `atoms not part of any T-Coupling group`. The build's message is `N atoms are not part of any of the T-Coupling groups` (format: `are not part of any of the %s groups`) — the short form drops `are` and `of the`, so it does not match the log line. 02.08:29 already carries the correct full form, so 02.08:34 is internally inconsistent with its own file.
**Evidence** (verbatim):
- `strings` on `libgromacs.so`: `are not part of any of the %s groups`
- `c96_sd_nogroups.mdp` (`integrator = sd`, no `tc-grps`) → exit=1: `Invalid T coupling input: 0 groups, 1 ref-t values and 1 tau-t values` (the other half of the quoted pair)
**Recommended fix**: 02.08:34 and 03.2:290 → `N atoms are not part of any of the T-Coupling groups`.

### I-76 README claims `annealing = group` is gone, but the build silently accepts it  [M]  ✅ RESOLVED (2026-09-14)
Files: `README.md`
README:104 lists "`annealing = group` gone (`no`/`single`/`periodic` per group)" among the 2026.3 API breaks. In this build `annealing = group` is not rejected: it parses without any `Invalid enum` error and is silently treated as `No` (no annealing) — a silent no-op, not an error. In fact grompp accepts *arbitrary* strings for `annealing` without validation (00.5:31 already notes this), so the "gone" wording (which in this KB means "will be rejected") is wrong and hides a silent-wrong-physics hazard: a user re-using the old `group` value gets a run with annealing silently off.
**Evidence** (verbatim, `work/kbval_2026-09-14/targeted/b/`):
- `f07_ann_group.mdp` (`annealing = group` + `annealing-npoints = 1` + time/temp, 1 tc-group) → exit=0, no NOTE/WARNING/ERROR; `gmx dump` of the TPR: `annealing:          No` / `annealing-npoints:           0`
- `f08_ann_bogus.mdp` (`annealing = totally-bogus-value`, otherwise identical) → exit=0, no `Invalid enum`
- `f07_ann_single.mdp` (`annealing = single` + `annealing-npoints = 1`) → exit=1: `Fatal error: Please specify at least a start and an end point for annealing` (i.e. real per-group values are validated, `group` is not)
- `f09_ann_single2.mdp` (`annealing = single` + 2 points) → exit=0; TPR: `annealing:      Single`, `annealing-npoints:           2`
**Recommended fix**: README:104 → "`annealing = group` no longer means per-group annealing — the build silently accepts it (and any string) and treats it as `No`; use one `no`/`single`/`periodic` value per temperature group". Optionally add the same caveat to the annealing row in 00.5:31.

## Verified OK (this pass)
- 00.1 (version context, FF/water presence, NNPot banner, HIP/VkFFT/SIMD notes), 00.2 (all 60 referenced tools present; removed/renamed list), 00.3, 00.4, 00.5 (incl. the `annealing` arbitrary-string note — accurate), 00.6.
- 01.1–01.9 (all commands and MDP deltas; error catalog re-checked line by line — the only defects are the five non-greppable quotes above, I-70…I-75). 01.9 §B `-maxwarn` behavior re-confirmed: `sc-r = 1` + `-maxwarn 2` → `WARNING 1 [file d11_maxwarn.mdp, line 6]: Unknown left-hand 'sc-r' in parameter file` and grompp continues (exit=0, TPR written).
- 02.01–02.14: all 23 KB MDP blocks re-probed clean (`unknown=invalid=obsolete=0`); targeted re-probes all confirmed — AWH (`awh1-dimN-coord-provider = fep-lambda` + `calc-lambda-neighbors = -1`, `awh1-dimN-cover-diameter`, `awh-share-multisim = yes`, `colvars-active`/`colvars-configfile`/`colvars-seed` all parse); pull API (`pull-coord1-vec`, `pull-coord1-origin`, `constraint`/`constant-force` types parse; `pull-coord1-drag-coef` unknown and `type = drag` invalid enum — both gone); sd/bd (`tau-t` friction, `bd-fric`, `ld-seed` parse; `Invalid T coupling input` on missing `tc-grps`); annealing (02.09 example block parses; `annealing-t`/`annealing-p` unknown — gone); QMMM (`qmmm-cp2k-*` parse; `qmmethod` values PBE, PBE0-D3, CAM-B3LYP-D3, WB97X, INPUT all accepted); NNPot (LibTorch abort reproduced verbatim at grompp time: `Libtorch/NN backend is not linked into GROMACS, NNPot simulation is not possible. Please, reconfigure GROMACS with -DGMX_NNPOT=TORCH`; `nnpot-mm-group`/`nnpot-nnp-charge` unknown; `nnpot-embedding = electrostatic-model` accepted); 02.12 (methodology only, no build-specific claims); 02.13 (semiisotropic 2-value requirement reproduced, `Isotropic` Berendsen alias confirmed, `gmx solvation` gone, `gmx order`/`density`/`potential`/`msd`/`spatial` present); 02.14 (FMM backend-alone error `FMM requires Coulomb interaction type to be FMM, but got Cut-off`; `fmm-backend = fmsolvr` + `coulombtype = FMM` parses; DGS similarity-measure enum `inner-product`/`relative-entropy`/`cross-correlation` all parse; walls incl. `wall-r-linpot`/`wall-ewald-zfac` and `Specified wall atom type LIG is not defined`; `com-pull`/`enforced-rotation`/`shell`/`electric-field-pulse` all unknown — gone; `rtpi` default `0.05` confirmed via TPR dump; `gmx nmr`/`nmeig`/`nmens`/`nmtraj` present).
- 03.1 (md-vv-avek NOTE reproduced verbatim: `Integrator method md-vv-avek is implemented primarily for validation purposes; for molecular dynamics, you should probably be using md or md-vv`; mdrun GPU flags `-nb`/`-pme`/`-bonded`/`-update`/`-ntmpi`/`-ntomp` present), 03.2 (all 10 templates parse clean), 03.3 (Makefile targets `gromacs`/`llama`/`comfyui`/`blender` + `scripts/switch-mode.sh` present; `-maxwarn` claim confirmed), 03.4 (cross-checked against 01.9), 03.5 (all 7 MTS `mts-level2-forces` enum values parse; `no domain decomposition for` / `isNumCoupledConstraintsSupported` / `PP task will update and constrain coordinates on the %s` strings present; `GMX_ENABLE_GPU_TIMING` absent as claimed; `-npme` default `-1`; `nonbonded-benchmark` flags incl. `-[no]all` present; `gmx benchmark` gone).
- README 2026.3 API-break list: all removals re-confirmed except `annealing = group` (I-76) — `integrator = qmmm`/`npt` invalid enum, `lmc = yes`/`expanded = yes`/`dhdl-file` unknown left-hand, `gmx pmx`/`g_wham`/`benchmark` absent, `trjpos`→`convert-trj` etc.

## Notes
- **No build drift**: live `gmx --version` = `2026.3-dev-20260625-1210900-unknown`, byte-identical fingerprint to the 2026-09-13 baseline; probe-suite matrix byte-identical (only the 5 known false positives). No gold-standard re-baseline needed.
- **Runtime-only claims not re-verified** (require `mdrun`, out of scope for a CPU-only audit): PLUMED thread-MPI incompatibility (02.05), GPU-resident-update engagement/fallback behavior (01.7/03.5), MTS throughput claims (03.5). The static side of each (option parse, build strings, `LincsGpu::isNumCoupledConstraintsSupported` symbol, `PP task will update…` format string) is verified.
- **I-70…I-75 are the same class as I-65/I-66** (catalog quotes that are not contiguous substrings of the real message). All five were found by re-running the full `01.9` catalog against `strings libgromacs.so`; the remaining catalog quotes were re-checked and are greppable — including `Number of coordinates ... does not match topology` (the `...` elision matches the real `number of coordinates in coordinate file (…, N) does not match topology (…, N)` line) and `WARNING: atom X is missing in residue XXX` (a prefix of `atom %s is missing in residue %s %d in the pdb file`).
- **Probe artifacts**: `work/kbval_2026-09-14/` (suite + `targeted/` + `targeted/b/`); `/tmp/strings.txt` inside the container is the `strings` dump of `libgromacs.so` used for the error-string checks.

## Fix pass (2026-09-14 — build 2026.3-dev-20260625-1210900-unknown)

**Scope:** 7 open issues (I-70…I-76) from the 2026-09-14 full-KB regression audit.
**Result:** 6 fixed, 0 already-fixed, 1 false-positive (closed), 0 left open.

#### I-70 `1-4 interaction not within cut-off` quote is not greppable — FIXED  ✅ RESOLVED (2026-09-14)
Files: `01-phases/01.6-production.md`, `01-phases/01.9-troubleshooting.md`, `03-playbooks/03.4-failure-diagnosis.md`
- **Preflight**: re-ran `strings` on `libgromacs.so` — build string confirmed present (line 28463); stale quote found in all three listed files (01.6:84, 01.9:57, 03.4:31). Issue still real.
- **Applied**: `1-4 interaction not within cut-off` → `1-4 (i,j) interaction not within cut-off! r=... Ignored` (all three files; placeholder style matches the catalog's X/YYY/N convention, ASCII `...` elision per `01.9:30`).
- **Evidence** (verbatim `strings` on `libgromacs.so`):
  - `1-4 (%d,%d) interaction not within cut-off! r=%g. Ignored`

#### I-71 `qmmm = yes` is "gone" but the build still recognizes it — FIXED  ✅ RESOLVED (2026-09-14)
Files: `02-md-types/02.10-qmmm.md`, `00-foundations/00.5-mdp-anatomy.md`
- **Preflight**: re-ran both audit probes in `work/kbfix_2026-09-14/` — `qmmm = yes` → exit=1 with the dedicated hard-error; `qmmm-group = QM` → `Unknown left-hand`. Issue still real.
- **Applied**: 02.10:24 `(the old `qmmm = yes` option is gone)` → `(the old `qmmm = yes` option is no longer usable — the build still recognizes it but hard-errors with `The QMMM integration you are trying to use is no longer supported`)`; 00.5:43 `**Old flat `qmmm`/`qmmm-*` names are gone; the module prefix is `qmmm-cp2k-`.**` → `**Old flat `qmmm-*` names are gone (`Unknown left-hand`); bare `qmmm` is still recognized but hard-errors (`The QMMM integration you are trying to use is no longer supported`); the module prefix is `qmmm-cp2k-`.**` (exactly the audit's recommended text).
- **Evidence** (verbatim `gmx grompp`, `work/kbfix_2026-09-14/`):
  - `i71_qmmm` (`qmmm = yes`): exit=1, log:
    - `ERROR 1 [file i71_qmmm.mdp]:`
    - `  The QMMM integration you are trying to use is no longer supported`
  - `i71_qmmmg` (`qmmm-group = QM`): exit=1, `WARNING 1 [file i71_qmmmg.mdp, line 5]: Unknown left-hand 'qmmm-group' in parameter file`

#### I-72 rtp-entry error quote omits `was` and the in-residue atom number — FIXED  ✅ RESOLVED (2026-09-14)
Files: `01-phases/01.9-troubleshooting.md` (+ sweep straggler `01-phases/01.1-structure-preparation.md`)
- **Preflight**: re-ran `strings` on `libgromacs.so` — build string confirmed present (line 44970); stale quote found at 01.9:19 (listed) and 01.1:49 (straggler, same quoted text). Issue still real.
- **Applied**: `Atom X in residue YYY not found in rtp entry` → `Atom X in residue YYY N was not found in rtp entry Z with M atoms` (01.9:19, 01.1:49).
- **Evidence** (verbatim `strings` on `libgromacs.so`):
  - `Atom %s in residue %s %d was not found in rtp entry %s with %d atoms`

#### I-73 position-restraints out-of-bounds quote drops the parentheses — FIXED  ✅ RESOLVED (2026-09-14)
Files: `01-phases/01.9-troubleshooting.md` (+ sweep stragglers `01-phases/01.2-topology-forcefield.md`, `00-foundations/00.4-topology-anatomy.md`, `02-md-types/02.02-position-restraints.md`)
- **Preflight**: re-ran `strings` on `libgromacs.so` — build string confirmed present (line 48761); stale quote found at 01.9:28 (listed) and three stragglers (01.2:61, 00.4:84, 02.02:62), all the same quoted text. Issue still real.
- **Applied**: `Atom index n in position_restraints out of bounds` → `Atom index (n) in position_restraints out of bounds (1-N)` (all four sites; now consistent with the neighboring bonds entry `Atom index (1) in bonds out of bounds (1-0)`).
- **Evidence** (verbatim `strings` on `libgromacs.so`):
  - `Atom index (%d) in %s out of bounds (1-%d).`

#### I-74 residue-database error quote omits `type` — FALSE POSITIVE  ❌ CLOSED (2026-09-14)
The audit's `strings` evidence cited `Residue type '%s' not found in residue topology database` (lib line 27341), but the library **also** contains `Residue '%s' not found in residue topology database` (line 46813, no `type`) — the strings evidence alone is ambiguous about which one pdb2gmx emits. Decisive probe: `gmx pdb2gmx -f i74_zzz.pdb -ff amber19sb -water none -ter -ignh -o i74_zzz.gro` (3-atom residue `ZZZ`, absent from the rtp) → exit=1, fatal error from `src/gromacs/gmxpreprocess/resall.cpp (line 632)`:
- `Residue 'ZZZ' not found in residue topology database`

No `type` in the emitted line — the KB's existing quote `Residue 'XXX' not found in residue topology database` **is** a contiguous substring of the real log line. The `Residue type '%s'...` variant is a different code path, not emitted by pdb2gmx. No edit made.

#### I-75 short T-coupling-group quote is not greppable — FIXED  ✅ RESOLVED (2026-09-14)
Files: `02-md-types/02.08-langevin-brownian.md`, `03-playbooks/03.2-mdp-templates.md`
- **Preflight**: re-ran `strings` on `libgromacs.so` — build string confirmed present (line 44031); stale quote found at 02.08:34 and 03.2:290 (both listed; 02.08:29 already carries the correct full form). Issue still real.
- **Applied**: `atoms not part of any T-Coupling group` → `N atoms are not part of any of the T-Coupling groups` (02.08:34, 03.2:290).
- **Evidence** (verbatim `strings` on `libgromacs.so`):
  - `%d atoms are not part of any of the %s groups`

#### I-76 README claims `annealing = group` is gone, but the build silently accepts it — FIXED  ✅ RESOLVED (2026-09-14)
Files: `README.md`
- **Preflight**: re-ran the audit's probe set in `work/kbfix_2026-09-14/` (base.mdp + `tc-grps = System` + `ref-t` + `tau-t` + `annealing-npoints = 1` + time/temp): `annealing = group` → exit=0, no `Invalid enum`; `gmx dump -s` of the TPR: `annealing: No` / `annealing-npoints: 0`; `annealing = totally-bogus-value` → exit=0 (any string accepted); `annealing = single` + 1 point → exit=1 `Please specify at least a start and an end point for annealing` (real values are validated, `group` is not). Issue still real.
- **Applied**: README:103-105 `annealing = group` gone (`no`/`single`/`periodic` per group) → `annealing = group` no longer means per-group annealing — the build silently accepts it (and any string) and treats it as `No`; use one `no`/`single`/`periodic` value per temperature group. (The audit's optional 00.5 caveat was **not** applied — 00.5 is not in the issue's `Files:` list and its existing arbitrary-string note is already accurate per the audit's Verified-OK.)
- **Evidence** (verbatim `gmx grompp` / `gmx dump -s`, `work/kbfix_2026-09-14/`):
  - `i76_group` (`annealing = group`): exit=0, no NOTE/WARNING/ERROR about annealing; TPR dump: `annealing:          No` / `annealing-npoints:           0`
  - `i76_totally-bogus-value`: exit=0, no `Invalid enum`
  - `i76_single` (`annealing = single`, 1 point): exit=1: `Please specify at least a start and an end point for annealing`
  - `i76_no` (`annealing = no`): exit=0; TPR dump: `annealing:          No` (enum value `no` confirmed)
  - `i76_periodic` (`annealing = periodic`, 1 point): exit=1 with the same start/end-point error, **not** `Invalid enum` (enum value `periodic` confirmed)

## Notes for the auditor
- **I-74 false positive — strings evidence picked the wrong library string**: both `Residue type '%s' not found in residue topology database` (line 27341) and `Residue '%s' not found in residue topology database` (line 46813) exist in `libgromacs.so`; pdb2gmx emits the latter (resall.cpp:632). Suggestion for the next audit: when a `strings` hit has a near-identical sibling variant, confirm the emitting code path with a live tool probe before opening an issue.
- **Sweep stragglers found and fixed as part of the pass** (project convention): I-72 → `01.1:49`; I-73 → `01.2:61`, `00.4:84`, `02.02:62`. All carried the identical stale quoted text.
- **Regression suite**: 23 blocks re-probed — zero parse signals (`unknown=invalid=obsolete=0` for all); matrix verdicts **byte-identical** to the 2026-09-14 audit baseline (only the 5 known false positives). Block verdicts differ only in block_009's source range (`02.10-qmmm.md:27-36` → `29-38`, +2-line shift from the I-71 edit; all verdict fields unchanged). Stale-text sweep for all six fixed issues: clean (no hits outside `issues_kb.md`).
- **All issues CPU-verified** (targeted `gmx grompp` / `gmx pdb2gmx` / `strings` / `gmx dump -s` probes in `work/kbfix_2026-09-14/`); no `mdrun`, no GPU.
- **Probe mechanics note**: in this build `gmx dump` takes TPRs via `-s` (`-f` rejects `.tpr`: "Only the following extensions are possible: .xtc, .trr, .cpt, .gro, .g96, .pdb, .tng, .h5md").
- **Drift gate**: live `gmx --version` = `2026.3-dev-20260625-1210900-unknown`, identical to the gold standard; no re-baseline needed.

---

## New issues from full-KB regression audit (2026-09-14, post-fix-pass)

**Method:** Drift gate first — live `gmx --version` fingerprint `2026.3-dev-20260625-1210900-unknown` is byte-identical to the 2026-09-14 baseline and `git diff HEAD -- gromacs/knowledge/` is clean (no KB change since the I-70…I-76 fix pass) → **regression pass**. Re-ran the full probe suite (101 commands, 23 per-block MDP probes, merged matrix); matrix verdicts byte-identical to the prior baseline (only the 5 known false positives). Re-read all 35 KB files; mapped every mechanical claim to the snapshot; ran targeted CPU-only `gmx grompp` probes to (a) check cross-option constraints on each MDP block and (b) reproduce error-string quotes verbatim. No `mdrun`, no GPU.
**Result:** 3 new issues (I-77 [H], I-78 [M], I-79 [L]), all confirmed against the build or the KB text.

### I-77 DGS block hard-errors in grompp — `nstcalcenergy` must be a multiple of `density-guided-simulation-nst`  [H]  ✅ RESOLVED (2026-09-14)
Files: `02-md-types/02.14-specialized.md`
The DGS block (lines 30-40) sets `density-guided-simulation-nst = 1000` (line 38) but never sets `nstcalcenergy`. The build requires `nstcalcenergy` to be a **multiple** of `density-guided-simulation-nst`; with the default `nstcalcenergy = 100` — and with the KB's own production template `nstcalcenergy = 1` (`01-phases/01.6-production.md:33`) — `grompp` aborts. So the documented block, used as-is or layered on the standard production MDP, cannot run.
**Evidence** (verbatim):
- KB block probed as-is (`work/kbval_2026-09-14/blocks/block_011.mdp.log`):
  - `ERROR 1 [file blocks/block_011.mdp]:`
  - `  nstcalcenergy (100) is not a multiple of density-guided-simulation-nst`
  - `  (1000) .`
- Targeted probes (`work/kbval_2026-09-14/targeted/`, `integrator = md-vv`, `nsteps = 100`, `group = System`):
  - `dgs-nst = 1000` + `nstcalcenergy = 1` → `nstcalcenergy (1) is not a multiple of density-guided-simulation-nst` (EXIT=1)
  - `dgs-nst = 1000` + `nstcalcenergy = 500` → `nstcalcenergy (500) is not a multiple of density-guided-simulation-nst` (EXIT=1)
  - `dgs-nst = 1000` + `nstcalcenergy = 1000` → EXIT=0; `dgs-nst = 500` + `nstcalcenergy = 1000` → EXIT=0; `dgs-nst = 100` + `nstcalcenergy = 100` → EXIT=0
  - ⇒ constraint is `nstcalcenergy % density-guided-simulation-nst == 0` (matches the error wording).
- Not a dummy-system artifact: the check fires for any `nsteps > 0` and is independent of the topology (reproduced with `group = System`).
**Recommended fix**: in the DGS block (`02.14-specialized.md:30-40`), add a `nstcalcenergy` line that is a multiple of `density-guided-simulation-nst`, with a comment, e.g. after line 38:
```
  ; nstcalcenergy MUST be a multiple of density-guided-simulation-nst
  ; (grompp errors otherwise); this overrides the production nstcalcenergy = 1:
  nstcalcenergy = 1000
```

### I-78 GPU-resident-update `h-bonds` "required" contradicts the detailed files (and 03.2 mis-cites them)  [M]  ✅ RESOLVED (2026-09-14)
Files: `README.md`, `03-playbooks/03.1-decision-trees.md`, `03-playbooks/03.2-mdp-templates.md`, `00-foundations/00.1-versions-install.md`, `01-phases/01.7-restart-parallelization.md`, `03-playbooks/03.5-performance.md`
The summary files state `constraints = h-bonds` is **required** for GPU-resident update, while the detailed files consistently state it is a **performance recommendation / not a hard gate** (`all-bonds` → CPU fallback, not a hard error). `03.2` Notes cites `01.7`/`03.5` as supporting "required" when both say the opposite. The specific "required" claim is **unverified against the build** (needs a GPU `-update gpu` run with `all-bonds` to confirm the fallback), but the internal inconsistency and the 03.2 mis-citation are clear from the KB text.
**Evidence** (verbatim KB lines):
- `README.md:90`: "GPU-resident update requires `constraints = h-bonds` and `-ntmpi 1`."
- `03.1-decision-trees.md:122`: "Requirements: constraints = h-bonds, -ntmpi 1, dynamical integrator, ..."
- `03.2-mdp-templates.md:321-322`: "**`constraints = h-bonds`** is required for GPU-resident update on this stack (`01.7`, `03.5`)."
- `00.1-versions-install.md:42-43`: "`constraints = h-bonds` is **performance-recommended** (avoids all-bonds P-LINCS communication overhead), not a hard requirement."
- `01.7-restart-parallelization.md:91-92`: "**Performance-recommended** (not required): `constraints = h-bonds`, not `all-bonds` — `all-bonds` works but adds P-LINCS communication overhead."
- `03.5-performance.md:30-35`: "**Performance recommendation** (not a hard gate): `constraints = h-bonds`, **not** `all-bonds`. With `all-bonds` ... the update **falls back to CPU** — so `all-bonds` usually **disables** GPU-resident update."
**Recommended fix**: align the three "required" statements with the detailed wording — `h-bonds` is a performance recommendation, not a hard requirement; `all-bonds` causes a CPU fallback for the update (via `LincsGpu::isNumCoupledConstraintsSupported`), not a hard error. Concretely: `README.md:90` → "...requires `-ntmpi 1`; `constraints = h-bonds` is performance-recommended (all-bonds falls back to CPU)"; `03.1:122` → move `constraints = h-bonds` out of "Requirements" into a "recommended" note; `03.2:321-322` → "is **recommended** (not required) for GPU-resident update ... (`01.7`, `03.5`)" (the citation then becomes correct).

### I-79 error quote `Invalid line in coordinate file for atom X` is not greppable  [L]  ✅ RESOLVED (2026-09-14)
Files: `01-phases/01.9-troubleshooting.md`
Line 37 quotes the error as `Invalid line in coordinate file for atom X`. The real message is `Invalid line in <filename> for atom N:` — the **filename** sits where the KB has the words "coordinate file", so the quote is not a contiguous substring of any rendered log line (same class as I-70…I-75).
**Evidence** (verbatim):
- `strings` on `libgromacs.so`: the format string is `Invalid line in %s for atom %d:` (`%s` = filename). The literal "coordinate file" does not appear in this message.
- Reproduction (`work/kbval_2026-09-14/targeted/bad.gro` — one atom line replaced with garbage, `gmx grompp -c bad.gro`):
  - `Fatal error:`
  - `Invalid line in bad.gro for atom 1:`
  - (EXIT=1)
**Recommended fix**: `01.9-troubleshooting.md:37` → change the quote to `Invalid line in <file> for atom N:` (or, matching the catalog's placeholder convention, `Invalid line in X for atom N:`).

## Verified OK (this pass)
- **Drift gate**: build fingerprint byte-identical to the 2026-09-14 baseline; no KB change since the fix pass (`git diff` clean).
- **All 23 KB MDP blocks**: zero parse signals (`unknown=invalid=obsolete=0`). Every block error is the known `gen-vel`/`continuation` probe artifact (context header adds `continuation = yes` while KB blocks set `gen-vel = yes`) or known noise (block_007 AWH/com-pull: `AWH biasing along a pull dimension is only compatible with COM pulling turned on`) — **except block_011 (DGS → I-77)**. block_013/017/019/021 NOTEs are expected (PME mesh-load hint; FEP stochastic-dynamics hint + `Setting nstcalcenergy (100) equal to nstdhdl (10)` auto-adjust; `awh1-dim1-diffusion not explicitly set`; SD/BD `ld_seed` continuation hint) — none are legacy-alias/deprecation NOTEs.
- **Matrix**: verdicts byte-identical to the prior baseline; the 5 `Unknown left-hand` lines (`nrexcl`, `fc`, `expanded`, `lmc`, `type`) are the known false positives — `nrexcl`/`fc`/`type` are topology/pull directives, and `expanded`/`lmc` are documented as *gone* in `README.md`/`02.06` (use `free-energy = expanded`).
- **00.1**: env vars `GMX_MAXBACKUP`/`GMX_LOG_BUFFER`/`GMX_SUPPRESS_DUMP`/`GMX_TPI_DUMP`/`GMX_TRAJECTORY_IO_VERBOSITY`/`GMX_HIP_TARGET_ARCH`/`GMX_CUDA_GRAPH`/`GMX_NBNXN_PLAINC_1X1`/`GMX_FILLERS_IN_LOCAL_STATE` all present; `amber14sb.ff`/`amber19sb.ff` + `opc.itp`/`opc3.itp` present; `gmx benchmark` gone, `nonbonded-benchmark` present.
- **00.2**: all referenced tools present; removed/renamed lists hold; `pdb2gmx -water` enum includes `opc`/`opc3`/`tip5p`/`tips3p`.
- **00.3 / 00.4**: file-format claims hold; 00.4 error quotes match the I-73 fix (`Atom index (n) in position_restraints out of bounds (1-N)`).
- **00.5**: `refcoord-scaling = yes` → `Invalid enum 'yes' for variable refcoord-scaling, using 'No'` (com/all parse); MTTK-requires-Nose-Hoover + constraints-allowed (I-68); `Isotropic` Berendsen alias; `annealing` arbitrary-string note; bare `qmmm` hard-error (I-71) — all consistent.
- **00.6**: `opc.itp`/`opc3.itp`/`spc.itp`/`spce.itp`/`ions_opc.itp`/`ions_opc3.itp` present in `amber14sb.ff`/`amber19sb.ff`; top-level `spce.itp` is a `#error` stub (verbatim); TIP5P present.
- **01.1–01.8**: commands/flags/MDP deltas hold; `cg`+constraints allowed (I-67); MTTK (I-68); tiny-tc-group NOTE (I-69); `1-4 (i,j) ... Ignored` (I-70); `Andersen temperature control not supported for integrator md.` reproduced verbatim at grompp time (KB quote is a contiguous substring — the `strings` miss is the `%s temperature control not supported for integrator %s.` format-string trap).
- **02.01–02.14**: all blocks re-probed; AWH/FEP/pull/sd-bd/annealing/QMMM/NNPot/walls/DGS-enum claims consistent with the I-71/I-75 fixes (DGS `nstcalcenergy` constraint is the only new defect → I-77).
- **03.1–03.5**: 10 templates parse clean; MTS `mts-level2-forces` enum; `nonbonded-benchmark` flags; GPU offload flags present.
- **README** 2026.3 API-break list: all removals re-confirmed; `lmc = yes`/`expanded = yes` correctly documented as gone.

## Notes
- **No build drift**: live `gmx --version` = `2026.3-dev-20260625-1210900-unknown`, byte-identical to the 2026-09-14 baseline; probe-suite matrix byte-identical. No re-baseline needed.
- **I-77 was missed by prior passes**: block_011's `errors=2` was classified as system noise, but the `nstcalcenergy ... not a multiple of density-guided-simulation-nst` error is an intrinsic cross-option constraint (fires for any `nsteps > 0`, topology-independent), not a 1-atom dummy artifact. Prior audits verified the DGS *enum values* parse but not the `nstcalcenergy` constraint. Suggestion for the next audit: when a block probe shows `errors > 0` with `unknown=invalid=obsolete=0`, read each error line and rule out intrinsic cross-option constraints, not just parse masking.
- **I-79 vs the 2026-09-11 fragment sweep**: that sweep verified the stable fragment `Invalid line in` is in-build (it is, as part of `Invalid line in %s for atom %d:`) and concluded "no new issues" — but it did not verify the *full* quote, whose `coordinate file` wording is not a rendered substring (→ I-79).
- **Runtime-only claims not re-verified** (require `mdrun`/GPU, out of scope for a CPU-only audit): PLUMED thread-MPI incompatibility (02.05), GPU-resident-update engagement/fallback and the I-78 `h-bonds` hard-requirement question (01.7/03.5), MTS throughput (03.5). The static side (option parse, build strings, `LincsGpu::isNumCoupledConstraintsSupported` symbol) is verified.
- **Probe artifacts**: `work/kbval_2026-09-14/` (suite + `targeted/` with the DGS `c1-c6`/`vA-vD` matrix, the `bad.gro` reproduction, and `and_md.mdp`).

## Fix pass (2026-09-14 — build 2026.3-dev-20260625-1210900-unknown)

**Scope:** 3 open issues (I-77…I-79) from the 2026-09-14 audit.
**Result:** 3 fixed, 0 already-fixed (closed), 0 false-positive (closed), 0 left open.

#### I-77 DGS block hard-errors in grompp — `nstcalcenergy` must be a multiple of `density-guided-simulation-nst` — FIXED  ✅ RESOLVED (2026-09-14)
Files: `02-md-types/02.14-specialized.md` (as listed in the issue)
- **Preflight**: re-probed the DGS block as-is (`nsteps = 100`, `md-vv`, 1-atom `tmin` system): `ERROR 1 …: nstcalcenergy (100) is not a multiple of density-guided-simulation-nst (1000)` (EXIT=1) — issue still real. Constraint matrix re-confirmed: `nstcalcenergy = 1` and `= 500` → same error; `= 1000` → no nstcalcenergy error (⇒ `nstcalcenergy % density-guided-simulation-nst == 0`).
- **Applied**: after `density-guided-simulation-nst = 1000` (line 38) added:
  ```
  ; nstcalcenergy MUST be a multiple of density-guided-simulation-nst
  ; (grompp errors otherwise); this overrides the production nstcalcenergy = 1:
  nstcalcenergy = 1000
  ```
- **Evidence**: the verbatim post-fix KB block re-probed (`nsteps = 100`, `md-vv`) produces **no** `nstcalcenergy … not a multiple` error (grep count 0); the only residual error is the probe artifact `Group Protein referenced in the .mdp file was not found in the list of index groups` (the 1-atom `tmin` system has no Protein group). `nstcalcenergy` is a real MDP option (grompp parses it and emits the constraint error, not "Unknown left-hand"); `01.6-production.md:33` carries `nstcalcenergy = 1` (the override the comment references).
- **Deviation**: none — applied the Recommended fix verbatim.

#### I-78 GPU-resident-update `h-bonds` "required" contradicts the detailed files (and 03.2 mis-cites them) — FIXED  ✅ RESOLVED (2026-09-14)
Files: `README.md`, `03-playbooks/03.1-decision-trees.md`, `03-playbooks/03.2-mdp-templates.md` (the three "required" statements; the detailed files `00.1`/`01.7`/`03.5` already carry the correct "performance-recommended" wording and were left unchanged)
- **Preflight**: text-consistency issue. The three "required" statements (README.md:90, 03.1:122, 03.2:321-322) contradict the detailed files' "performance-recommended / not a hard gate" wording (00.1:42-43, 01.7:91-92, 03.5:30-35), and 03.2 mis-cites 01.7/03.5 as supporting "required" — confirmed from the KB text. Build tokens in the fix verified: `-ntmpi <int>` present in `gmx mdrun -h`; `constraints = h-bonds` and `= all-bonds` both accepted by grompp (EXIT=0; `all-bonds` emits only a soft NOTE suggesting `h-bonds` for performance); `constraints = bogus` rejected (`Invalid enum 'bogus' for variable constraints, using 'none'`); `gmx::LincsGpu::isNumCoupledConstraintsSupported(gmx_mtop_t const&)` present in `libgromacs.so` (mangled `_ZN3gmx8LincsGpu32isNumCoupledConstraintsSupportedERK10gmx_mtop_t`, plus the `UpdateConstrainGpu` variant) — the CPU-fallback mechanism exists in the build.
- **Applied**:
  - `README.md:89-90` → "GPU-resident update requires `-ntmpi 1`; `constraints = h-bonds` is performance-recommended (all-bonds falls back to CPU)."
  - `03.1-decision-trees.md:122` → moved `constraints = h-bonds` out of "Requirements" into a new line: "Recommended: constraints = h-bonds (all-bonds falls back to CPU)."
  - `03.2-mdp-templates.md:321-323` → "**`constraints = h-bonds`** is recommended (not required) for GPU-resident update on this stack — `all-bonds` works but the update falls back to CPU (`01.7`, `03.5`)." (the 01.7/03.5 citation is now correct).
- **Evidence**: the `constraints = all-bonds` grompp probe returns EXIT=0 with only a NOTE ("You are using constraints on all bonds … We suggest using constraints = h-bonds instead, this will also improve performance") — i.e. `all-bonds` is not a hard gate, matching the "recommended, not required" wording. The runtime all-bonds→CPU-fallback itself needs a GPU `-update gpu` run (out of scope, rule 10); the static side (option parse + fallback symbol) is verified.
- **Deviation**: none — applied the Recommended fix (wording aligned to the detailed files).

#### I-79 error quote `Invalid line in coordinate file for atom X` is not greppable — FIXED  ✅ RESOLVED (2026-09-14)
Files: `01-phases/01.9-troubleshooting.md` (as listed in the issue)
- **Preflight**: re-probed. `strings` on `libgromacs.so`: the format string is `Invalid line in %s for atom %d:` (`%s` = filename) — the literal "coordinate file" is not in the message. Reproduction (a `tmin`-derived `.gro` with the atom line set to garbage, `gmx grompp -c bad.gro`): `Fatal error:` / `Invalid line in /work/…/bad.gro for atom 1:` (EXIT=1). Issue still real.
- **Applied**: `01.9-troubleshooting.md:37` quote `` `Invalid line in coordinate file for atom X` `` → `` `Invalid line in X for atom N:` `` (catalog placeholder convention: `X` for the filename, `N` for the atom number, matching e.g. "T-Coupling group X is N").
- **Evidence**: the fix's tokens map 1:1 onto the format string — `Invalid line in` (prefix), `X`→`%s` (filename), `for atom`, `N`→`%d` (number), trailing `:` (present in `…for atom %d:`). The rendered message shows the filename where the KB had "coordinate file".
- **Deviation**: none — applied the Recommended fix (used the `X`/`N` placeholder variant).

## Notes for the auditor
- **Regression suite (post-fix)**: 23 blocks probed; `03_block_verdicts.txt` and `03_matrix_verdicts.txt` diff vs the pre-fix baseline shows **no new parse signals** (every block `unknown=0 invalid=0 obsolete=0`; matrix identical). Only deltas: block_011 (DGS) `errors` 2→1 (the `nstcalcenergy … not a multiple` error is gone — the I-77 fix; the remaining `ERROR 1` is the known `gen-vel`/`continuation` probe artifact) and `notes` 0→1 (benign `nstcomm < nstcalcenergy` hint); block_012's line range shifted 84-89→87-92 (same file, 3 lines added above it) with an unchanged verdict.
- **I-77 straggler sweep**: only one DGS block exists in the KB (`02.14-specialized.md`); no other `density-guided-simulation-nst` block lacks `nstcalcenergy`.
- **I-78 straggler sweep**: no remaining "required" framing for `h-bonds`/GPU-resident update outside the three fixed files. `03.3-checklists.md:96` (`[ ] constraints = h-bonds (for GPU-resident update on this stack)`) is a checklist to-do, not a "required" claim — left as-is.
- **I-79 straggler sweep**: no remaining `Invalid line in coordinate file` in the KB.
- **Still runtime-only (not re-verified, needs GPU/`mdrun`, out of scope)**: the I-78 all-bonds→CPU-fallback behavior itself (static side verified); PLUMED thread-MPI (02.05); MTS throughput (03.5).
- **Probe artifacts**: `work/kbfix_2026-09-14/` (I-77 `i77_*` constraint matrix + verbatim KB-block probe, I-78 `i78_con_*` enum probes, I-79 `bad.gro` reproduction, plus `baseline_03_*` pre-fix verdict snapshots).

## Regression audit — no new issues (2026-09-14, post I-77…I-79 fix pass)

**Method:** Drift gate first — live `gmx --version` fingerprint `2026.3-dev-20260625-1210900-unknown` is byte-identical to the 2026-09-14 baseline and `git diff HEAD -- gromacs/knowledge/` is clean (latest commit `6c8f144` is the I-77…I-79 fix pass; no KB change since) → **regression pass**. Re-ran the full probe suite (101 commands, 23 per-block MDP probes, merged matrix). Confirmed the I-77…I-79 fixes are in place. Spot-checked the highest-value claim categories against the live build: 00.2 command surface (bidirectional flag check), 02.11 NNPot (all options + LibTorch abort reproduced verbatim), 02.05 PLUMED, 03.5 MTS, 01.9 error catalog (every quoted error reproduced or greppable), env vars, FF/water listing, CLI tool inventory, multi-value options. CPU-only grompp / tool probes only — no `mdrun`, no GPU.
**Result:** 0 new issues. All 23 blocks `unknown=invalid=obsolete=0`; matrix byte-identical to the prior baseline (only the 5 known false positives). The I-77…I-79 fixes hold.

## Verified OK (this pass)
- **Drift gate**: build fingerprint byte-identical to the 2026-09-14 baseline; KB clean since the I-77…I-79 fix pass (latest commit `6c8f144`); no open issues.
- **I-77…I-79 fixes in place**: `02.14-specialized.md:39-41` DGS block now sets `nstcalcenergy = 1000` (a multiple of `density-guided-simulation-nst = 1000`); `README.md:90`, `03.1-decision-trees.md:124`, `03.2-mdp-templates.md:321` carry the "h-bonds performance-recommended (all-bonds falls back to CPU)" wording; `01.9-troubleshooting.md:37` quote is `Invalid line in X for atom N:`.
- **All 23 KB MDP blocks**: zero parse signals (`unknown=invalid=obsolete=0`). Every block error is the known `gen-vel`/`continuation` probe artifact or known 1-atom dummy-system noise. block_011 (DGS) `errors=1 notes=1` = the post-I-77-fix state (the `nstcalcenergy … not a multiple` error is gone; the residual `ERROR 1` is the probe artifact, the NOTE is the benign `nstcomm < nstcalcenergy` hint). block_013/017/019/021 NOTEs are the expected PME-mesh / FEP / AWH / SD-BD hints — none are legacy-alias/deprecation NOTEs.
- **Matrix**: verdicts byte-identical to the prior baseline; the 5 `Unknown left-hand` lines (`nrexcl`, `fc`, `expanded`, `lmc`, `type`) are the known false positives.
- **00.2 command surface**: every referenced tool present; every flag in the "Key flags" table verified present in the build's `-h` (bidirectional — no phantom flags, no missing flags).
- **02.11 NNPot**: all `nnpot-*` options parse; `nnpot-embedding` enum confirmed; the LibTorch-missing abort reproduced verbatim (`grompp` exits, no TPR).
- **01.9 error catalog**: every quoted error string is a contiguous substring of a reproduced log line or the build's `strings` (one accepted minor case deviation — see Notes).
- **Env vars / FF / CLI tools / multi-value options**: all verified against the snapshot (re-confirmed this pass; consistent with the prior pass's Verified OK).

## Notes
- **No build drift, no KB drift**: pure regression re-verification after the I-77…I-79 fix pass. No re-baseline needed.
- **01.9 accepted minor deviation (not a new issue)**: `01.9-troubleshooting.md:31` quotes `Number of coordinates ... does not match topology` (capital `N`); the build renders `number of coordinates in coordinate file (…, N) does not match topology (…, N)` (lowercase `n`). Already examined and accepted in the prior pass as a recognizable fragment (the `...` elision covers the elided middle); the only residual is the `N`/`n` case. If desired, a future fix pass could align the case.
- **Runtime-only claims not re-verified** (require `mdrun`/GPU, out of scope for a CPU-only audit): PLUMED thread-MPI incompatibility (02.05), GPU-resident-update all-bonds→CPU-fallback behavior (01.7/03.5 — static side verified), MTS throughput (03.5).
- **Probe artifacts**: `work/kbval_2026-09-14/` (suite re-run this pass; `targeted/` from the prior pass retained).

## Regression audit — no new issues (2026-09-14, second regression pass)

**Method:** Drift gate first — live `gmx --version` fingerprint `2026.3-dev-20260625-1210900-unknown` is byte-identical to the 2026-09-14 baseline and `git diff HEAD -- gromacs/knowledge/` shows only `issues_kb.md` itself (the log; no KB content change since the I-77…I-79 fix pass, latest commit `6c8f144`) → **regression pass**. Re-ran the full probe suite (101 commands, 23 per-block MDP probes, merged matrix). Re-read all 35 KB files; mapped every mechanical claim to the snapshot; ran ~25 targeted CPU-only `gmx grompp` probes for prose-only claims (enum values, "gone" options, cross-option constraints, error strings) and re-checked the CLI surface bidirectionally against the `-h` dumps. No `mdrun`, no GPU.
**Result:** 0 new issues. All 23 blocks `unknown=invalid=obsolete=0`; matrix byte-identical to the prior baseline (only the 5 known false positives). Every targeted probe matched the KB claim, verbatim where the KB quotes build output.

## Verified OK (this pass)
- **Drift gate**: build fingerprint byte-identical to the 2026-09-14 baseline; no KB content change since the I-77…I-79 fix pass; no open issues.
- **I-77…I-79 fixes hold**: DGS block (`02.14-specialized.md`) sets `nstcalcenergy = 1000` (block_011 `errors=1 notes=1` = post-fix state: residual `gen-vel`/`continuation` probe artifact + benign `nstcomm < nstcalcenergy` hint); the three "h-bonds performance-recommended" wordings are in place; `01.9` quote is `Invalid line in X for atom N:`.
- **All 23 KB MDP blocks**: zero parse signals. Every block error/NOTE is a known artifact: `gen-vel`/`continuation` probe artifact (18 blocks), block_007 AWH/com-pull incompatibility, block_013 PME mesh-load hint, block_017 FEP stochastic-dynamics hint + `Setting nstcalcenergy (100) equal to nstdhdl (10)` auto-adjust, block_019 `awh1-dim1-diffusion not explicitly set` hint, block_021 SD/BD `ld_seed` continuation hint. No legacy-alias/deprecation NOTEs.
- **Matrix**: byte-identical to the prior baseline; the 5 `Unknown left-hand` lines (`nrexcl`, `fc`, `expanded`, `lmc`, `type`) are the known false positives (topology/pull directives; `expanded`/`lmc` are documented as *gone* — and the build indeed rejects both, confirming the KB).
- **CLI surface (bidirectional)**: every referenced tool present (incl. `sorient`, `spol`, all 2026.3 analysis tools); every listed flag present in the build's `-h` — including the 21 boolean flags written `-[no]X` (`pdb2gmx -ss/-lys/-arg/-asp/-glu/-gln/-his/-una/-missing/-deuterate/-cmap/-renum`, `editconf -pbc`, `genion -neutral`, `trjcat -sort/-keeplast/-overwrite`, `grompp -zero/-renum`, `mdrun -v`, `convert-tpr -generate_velocities`, `genrestr -constr`, `mk_angndx -hyd`); every "No `-X` in 2026.3" claim confirmed absent (`pdb2gmx -igb/-pbr/-bact/-cys/-membrane/-zero/-altloc`, `editconf -ct/-if/-of`, `solvate -f/-dodeca/-boxx/-boxy/-boxz/-r`, `genion -select/-pdb`, `insert-molecules -maxattempt`, `make_ndx -select/-id`, `select -index/-output/-res`, `mk_angndx -f/-o`, `genrestr -group`, `grompp -i`, `convert-tpr -define`, `mdrun -f/-continue/-nocontinuation/-colvars/-debug`, `check -s`, `trjconv -surround/-resnum/-fitref/-compress/-begin/-end`, `trjcat -skip/-shift/-set-switch/-single`, `hbond/-rdf -ac`, `gyrate -res`, `-index` on all analysis tools); all 20 removed tools absent (`trjpos`, `xvdgen`, `mktube`, `charge`, `ion2group`, `pmx`, `fit`, `nmat`, `pmat`, `dipole`, `rotinv`, `axias`, `solvation`, `g_wham`, `benchmark`, `insert`, `sander`, `do_rms`, `do_wham`, `analysis`); replacements present (`convert-trj`, `wham`, `dipoles`, `nonbonded-benchmark`, `insert-molecules`, `spatial`). `gmx awh` help matches the KB verbatim (`-f [<.edr>]`, `-s [<.tpr>]`, `-o [<.xvg>]`, `-fric [<.xvg>]`); `gmx wham` file-list API (`-ix/-if/-it/-is/-iiact/-tab/-o/-bins/-temp/-tol`) all present; `gmx dump -s <tpr>` works (no positional arg).
- **"Gone" MDP options (36 probed)**: all `Unknown left-hand` — `ns`, `calcvf`, `tau-bfric`, `lincs-itmax`, `lincs-warnstep`, `lincs-warnsize`, `lincs-mtol`, `lincs-algo`, `annealing-t`, `annealing-p`, `free-energy-group`, `sc-r`, `sc-n`, `sc-zero`, `sc-coulomb`, `dhdl-file`, `pull-coord`, `pull-coord1-increment`, `pull-coord1-force-constant`, `pull-coord1-flat-bottom`, `pull-coord1-drag-coef`, `com-pull`, `enforced-rotation`, `shell`, `electric-field-pulse`, `wall`, `wall-r`, `wall-epsilon`, `wall-sigma`, `rfcutoff`, `eps-r`, `eps-rf`, `coulomb-verlet-scheme`, `pme-spacing`, `dispersion-correction`, `nmr`, plus matrix-confirmed `lmc`/`expanded`.
- **Obsolete/legacy behavior (verbatim)**: `nstcheckpoint` → `Ignoring obsolete mdp entry 'nstcheckpoint'`; bare `qmmm = yes` → `ERROR 1 …: The QMMM integration you are trying to use is no longer supported`; `integrator = md-vv-avek` → `NOTE …: Integrator method md-vv-avek is implemented primarily for validation purposes; for molecular dynamics, you should probably be using md or md-vv`; `pcoupl = Isotropic` (with `md`) → `NOTE …: Old option for pressure coupling given: changing "Isotropic" to "Berendsen"`.
- **Enums (targeted probes)**: `tcoupl` enum list matches the KB exactly (`'No' 'Berendsen' 'Nose-Hoover' 'yes' 'Andersen' 'Andersen-massive' 'V-rescale'`), and the 01.9 invalid example reproduces verbatim: `Invalid enum 'V-rescale!' for variable tcoupl, using 'No'`; `refcoord-scaling = yes` → `Invalid enum 'yes' … Next time, use one of: 'No' 'All' 'COM'`; `integrator = tpi`/`tpic` accepted (failure is the dummy-system T-coupling check, not a parse rejection); `free-energy = expanded` + `lmc-stats = minvar` + `lmc-move = metropolized-gibbs` + `lmc-weights-equil = no` + `nstexpanded` all parse, and the md-vv requirement reproduces verbatim: `Can only use expanded ensemble with md-vv (for now)`; `sc-function = gapsys` accepted; `wall-type = table` accepted (and `wall-atomtype = W1` reproduces the KB-quoted `Specified wall atom type W1 is not defined`); `rtpi`, `nstdisreout`, the `disre` family, `colvars-active`/`colvars-configfile`, `rotation = yes` + `rot-*`, `electric-field-x = 100 0 0 0` (four reals) all parse.
- **Cross-option constraints (verbatim)**: `fmm-backend = exafmm` without `coulombtype = FMM` → `ERROR 1 …: FMM requires Coulomb interaction type to be FMM, but got Cut-off` (with `coulombtype = FMM` the FMM error is gone — only the no-charges warning on the dummy system); `awh-nstout = 7` with `nstenergy = 100` → `awh-nstout (7) should be a multiple of nstenergy (100)`; `pcoupltype = semiisotropic` with one value → `Pressure coupling incorrect number of values (I need exactly 2)` (two values parse).
- **01.9 error catalog**: every quoted error string is a contiguous substring of a reproduced log line or of the build's `strings` (format strings: `Atom index (%d) in %s out of bounds (1-%d).` covers both the `position_restraints` and `bonds` quotes; `) is not a multiple of ` covers the DGS quote; `%s temperature control not supported for integrator %s.` covers the Andersen quote). `Can not do Conjugate Gradients with constraints` is correctly **absent** (only `Polak-Ribiere Conjugate Gradients` present) — the KB's "no longer emitted" claim holds.
- **00.1**: env vars `GMX_MAXBACKUP`/`GMX_LOG_BUFFER`/`GMX_SUPPRESS_DUMP`/`GMX_TPI_DUMP`/`GMX_TRAJECTORY_IO_VERBOSITY` present in `libgromacs.so`; `PLUMED_KERNEL` present in `libgromacs.so` (PLUMED is statically linked — the `GMX_*`-prefix sweep misses it by design); version facts hold (TNG on, Colvars on, Plumed on, CP2K off, Torch off, HIP `--offload-arch=gfx1100`, SIMD `AVX2_256`, VkFFT 1.3.1, 101 commands).
- **00.3/01.6 TNG**: `mdrun -x` help is `-x [<.xtc/.tng>] (traj_comp.xtc) (Opt.)` / `Compressed trajectory (tng format or portable xdr format)` — matches the KB quotes verbatim.
- **00.6**: `amber14sb.ff`/`amber19sb.ff` ship `opc.itp`, `opc3.itp`, `spc.itp`, `spce.itp`, `ions_opc.itp`, `ions_opc3.itp`; `charmm27.ff` only (no CHARMM36); `gromos54a7.ff` only (no 56a7); `oplsaa.ff` present; top-level `spc.itp`/`spce.itp`/`tip3p.itp`/`tip4p.itp` are `#error` stubs with the exact KB-quoted text.
- **01.7**: the GPU-update log quote is the rendered form of the in-build format string `PP task will update and constrain coordinates on the %s` (`%s` = device, renders "GPU"); `gmx::UpdateConstrainGpu` symbols present (static side of the I-78 claim).

## Notes
- **No build drift, no KB drift**: third consecutive regression pass on the `2026.3-dev-20260625-1210900-unknown` baseline with an unchanged KB. No re-baseline needed.
- **01.9 accepted minor deviation (carried over, not a new issue)**: `01.9-troubleshooting.md:31` quotes `Number of coordinates ... does not match topology` (capital `N`); the build renders lowercase `number of coordinates …`. Accepted in the prior pass; re-accepted here.
- **Runtime-only claims not re-verified** (require `mdrun`/GPU, out of scope for a CPU-only audit): PLUMED thread-MPI incompatibility (02.05), GPU-resident-update all-bonds→CPU-fallback behavior (01.7/03.5 — static side verified), MTS throughput (03.5).
- **Probe artifacts**: `work/kb-audit/` (suite re-run this pass) + `work/kb-audit/targeted/` (this pass's targeted probes: `tpi2`/`tpic2`, `fmm1`/`fmm2`, `gapsys2`, `iso`/`isomd`, `badenum`, `efield`, `exp`, `wallt`, `disre`, `colv`, `rot`, `qmmm`, `gone` (35-option batch), `obsolete`, `avek2`, `drag`, `rtpi`, `refyes`, `awhnst2`, `semi1`/`semi2`).

## One-off fix — 01.9 case alignment (2026-09-14, user-approved, outside the open-issue contract)

The carried-over "accepted minor deviation" (01.9 capital-`N` quote) was aligned with the build, per explicit user request. No open `### I-NN` issue was involved; this is a one-off task, logged here for traceability.
- **Fix**: `01-phases/01.9-troubleshooting.md:31` — quote changed `Number of coordinates ... does not match topology` → `number of coordinates ... does not match topology` (single character; the `...` elision was already accepted and is untouched). Straggler sweep: the only content-file hit was this line; the remaining `Number of coordinates` occurrences in this file are historical log entries (append-only — intentionally not rewritten).
- **Build evidence (re-verified this pass, CPU-only)**: `strings libgromacs.so` format string `number of coordinates in coordinate file (%s, %d)\n             does not match topology (%s, %d)`; targeted repro — `gmx grompp -f base.mdp -c casemismatch.gro -p tmin.top` (2-atom `.gro` vs 1-atom topology) renders verbatim: `number of coordinates in coordinate file (casemismatch.gro, 2)` / `             does not match topology (tmin.top, 1)`.
- **Regression gate**: full probe suite re-run post-fix; `03_block_verdicts.txt` and `03_matrix_verdicts.txt` byte-identical to the pre-fix baseline (all 23 blocks `unknown=invalid=obsolete=0`; matrix = the 5 known false positives). No new parse signals.
- **Probe artifacts**: `work/kb-audit/casemismatch.gro` (repro input; session dir is wiped by the next suite run — repro is one `printf` + the command above).

## Regression audit — no new issues (2026-09-15, fourth regression pass)

**Method:** Drift gate first — live `gmx --version` fingerprint `2026.3-dev-20260625-1210900-unknown` is byte-identical to the 2026-09-14 baseline and `git diff HEAD -- gromacs/knowledge/` is clean (latest KB commit `65c4eb2` is the 2026-09-14 one-off fix + regression logs; the two newer repo commits `daa0801`/`fa34fc5` are Qwen model-config changes, not KB) → **regression pass**. Re-ran the full probe suite (101 commands, 23 per-block MDP probes, merged matrix). Re-verified the highest-value claim categories the mechanical floor does not cover, with targeted CPU-only probes: removed-command inventory (14 tools), removed `gmx` options, the `disable-drift-correction`/`disable-lambda-correction` removal, the DGS `nstcalcenergy` constraint, the GRO `Invalid line` message, the NNPot LibTorch abort, env-var inventory, and the FF/water listing. No `mdrun`, no GPU.
**Result:** 0 new issues. All 23 blocks `unknown=invalid=obsolete=0`; matrix byte-identical to the prior baseline (only the 5 known false positives). Every targeted probe matched the KB claim, verbatim where the KB quotes build output.

## Verified OK (this pass)
- **Drift gate**: build fingerprint byte-identical to the 2026-09-14 baseline; KB clean since the 2026-09-14 one-off fix (latest KB commit `65c4eb2`); no open issues.
- **All 23 KB MDP blocks**: zero parse signals (`unknown=invalid=obsolete=0`). Every block error/NOTE is a known artifact (1-atom dummy-system noise, AWH/com-pull incompatibility on block_007, `gen-vel`/`continuation` probe artifact). No legacy-alias/deprecation NOTEs.
- **Matrix**: byte-identical to the prior baseline; the 5 `Unknown left-hand` lines (`nrexcl`, `fc`, `expanded`, `lmc`, `type`) are the known false positives (topology/pull directives; `expanded`/`lmc` documented as *gone*, and the build rejects both).
- **Removed commands (14)**: `axias`, `charge`, `dipole`, `do_rms`, `do_wham`, `fit`, `g_wham`, `ion2group`, `nmat`, `pmat`, `pmx`, `rotinv`, `solvation`, `trjpos` — all absent from the build's command inventory; the KB references each only in "gone / removed / replaced" framing, never as a live tool. Replacements (`dipoles`, `wham`, `nonbonded-benchmark`, `insert-molecules`, `convert-trj`, `spatial`) present.
- **Removed `gmx` options**: `benchmark` (now `nonbonded-benchmark`) and `trjconv -w` — both absent from the build; the KB documents both as gone/replaced.
- **`disable-drift-correction` / `disable-lambda-correction`**: both absent from the build (replaced by the unified `disable-correction`); the KB documents the removal correctly.
- **DGS `nstcalcenergy` constraint (I-77)**: targeted probe (`density-guided-simulation-active = yes`, `nstcalcenergy = 1`) reproduces verbatim `nstcalcenergy (1) is not a multiple of density-guided-simulation-nst`; the KB block (`02.14`) sets `nstcalcenergy = 1000` (a multiple of `density-guided-simulation-nst = 1000`) — post-fix state holds.
- **GRO `Invalid line` message (I-79)**: targeted probe (malformed atom line in a 3-atom `.gro`) reproduces verbatim `Invalid line in bad2.gro for atom 1:` — matches the KB quote `Invalid line in X for atom N:`.
- **02.11 NNPot**: all `nnpot-*` options parse; the LibTorch-missing abort reproduces verbatim: `Libtorch/NN backend is not linked into GROMACS, NNPot simulation is not possible. Please, reconfigure GROMACS with -DGMX_NNPOT=TORCH` (grompp exits, no TPR).
- **Env vars**: every `GMX_*` referenced in the KB is accounted for — present in `libgromacs.so` (`GMX_MAXBACKUP`, `GMX_SUPPRESS_DUMP`, `GMX_TPI_DUMP`, `GMX_LOG_BUFFER`, `GMX_NNPOT`, `GMX_HIP_TARGET_ARCH`, `GMX_CUDA_GRAPH`, `GMX_FILLERS_IN_LOCAL_STATE`, `GMX_NBNXN_PLAINC_1X1`, `GMX_TRAJECTORY_IO_VERBOSITY`, `GMX_CP2K`, `GMX_TORCH`), or correctly framed as a build-time CMake flag (`GMX_BUILD_OWN_FFTW` = `-DGMX_BUILD_OWN_FFTW=ON`; `GMX_SIMD` = `-DGMX_SIMD=AVX2_256`, in the "build notes" sections — consistent with the GROMACS docs where `GMX_SIMD` is a CMake option, not a runtime var), or correctly documented as absent (`GMX_ENABLE_GPU_TIMING` / `GMX_DISABLE_GPU_TIMING` — `03.5:77` "there is no dedicated `GMX_ENABLE_GPU_TIMING` env var in this build").
- **00.6 FF/water**: all 4 referenced FFs present in the build (`amber14sb.ff`, `amber19sb.ff`, `charmm27.ff`, `oplsaa.ff`); CHARMM36 correctly noted absent (only `charmm27.ff` ships). `amber14sb.ff`/`amber19sb.ff` ship all 6 claimed water/ion files (`opc.itp`, `opc3.itp`, `spc.itp`, `spce.itp`, `tip3p.itp`, `tip4pew.itp`). Every referenced water model present (`spce`, `tip3p`, `tip4p`, `tip4pew`, `tip5p`, `opc`, `opc3`, `spc`).

## Notes
- **No build drift, no KB drift**: fourth consecutive regression pass on the `2026.3-dev-20260625-1210900-unknown` baseline with an unchanged KB. No re-baseline needed.
- **01.9 accepted minor deviation (carried over, not a new issue)**: `01.9-troubleshooting.md:31` capital-`N` case was already aligned in the 2026-09-14 one-off fix (quote now `number of coordinates ... does not match topology`); no residual deviation.
- **Runtime-only claims not re-verified** (require `mdrun`/GPU, out of scope for a CPU-only audit): PLUMED thread-MPI incompatibility (02.05), GPU-resident-update all-bonds→CPU-fallback behavior (01.7/03.5 — static side verified), MTS throughput (03.5).
- **Probe artifacts**: `work/kb-audit/` (suite re-run this pass) + `work/kb-audit/targeted/` (this pass's targeted probes: `nnpot.mdp` (NNPot abort, `nnpot-input-group = System`), `min.mdp`/`bad2.gro` (I-79 `Invalid line` repro), DGS `nstcalcenergy` constraint probe).

## New issues from full-KB audit (2026-09-16, fifth pass)

**Method:** Drift gate first — live `gmx --version` fingerprint `2026.3-dev-20260625-1210900-unknown` is byte-identical to the 2026-09-14/15 baseline (no build drift), but the KB has a new commit `3e57b3d` (C-01 content pass: carbohydrate + inorganic parameterization sections added to `00.6`) → **full pass**, not regression. Re-ran the full probe suite (101 commands, **30** per-block MDP probes — 7 new blocks extracted from `03.2`/`03.5`/`02.04` delta blocks —, 23 directive probes, merged matrix). Suite change this pass (hard rule 5): the block context header now injects context parents (`pull = yes`/`pull-ncoords`/`pull-ngroups`, `awh = yes`, `free-energy = yes`, `colvars-active = yes`, `coulombtype = FMM`) when a delta block uses child options without its parent — the prior run's `block_010` `unknown=3` (`pull-coord1-start/rate/k` in the `02.04:111-114` delta block) was a context artifact, not a KB defect; re-probed with parents, all three options parse. All 32 content files + `README.md` re-read; semantic claims verified with targeted CPU-only probes (grompp / `gmx <tool> -h` / `strings`). No `mdrun`, no GPU.
**Result:** 4 new issues (I-80…I-83), all confirmed real against the build.

### I-80 moleculetype table lists a `[ nonbonded ]` section that does not exist in the build  [M]  ✅ RESOLVED (2026-09-16)
Files: `00-foundations/00.4-topology-anatomy.md`
KB line 56 (moleculetype sub-section table): `| `[ nonbonded ]` | `i  j  func  epsilon  sigma` (or 4-col for mixed) |`. The build rejects the directive in every position: stage-A name probe (line 1, top level) → `ERROR 1 [file nonbonded_a.top, line 1]: Invalid directive nonbonded`; inside a moleculetype after `[ bonds ]`, after `[ pairs ]`, and after `[ position_restraints ]` → `Invalid directive nonbonded` each time (targeted probes, 2-atom DUM moleculetype). The 2025.1 manual's "Molecule definition(s)" table (Table 14) lists `bonds`/`angles`/`dihedrals`/`pairs`/`pairs_nb`/`virtual_sites*`/`constraints`/`position_restraints` — no `nonbonded`. In GROMACS, nonbonded parameters derive from `[ atomtypes ]` (per atom type); 1-4 interactions are set via `[ pairs ]` / top-level `[ pairtypes ]`.
**Recommended fix**: delete the `[ nonbonded ]` row (00.4:56). Optionally replace it with a row stating that nonbonded parameters come from `[ atomtypes ]` and 1-4 interactions from `[ pairs ]`/`[ pairtypes ]`.

### I-81 moleculetype table lists a `[ cgenff_nons ]` section that does not exist in the build  [M]  ✅ RESOLVED (2026-09-16)
Files: `00-foundations/00.4-topology-anatomy.md`
KB line 57: `| `[ cgenff_nons ]` | CGenFF-specific nonbonded |`. Stage-A name probe → `ERROR 1 [file cgenff_nons_a.top, line 1]: Invalid directive cgenff_nons`; `strings /usr/local/gromacs/lib/libgromacs.so | grep -i cgenff` returns zero hits — the name appears nowhere in the binary. CGenFF nonbonded parameters live in the standard `[ atomtypes ]` table (CHARMM mixed nonbonded function types); there is no dedicated section.
**Recommended fix**: delete the `[ cgenff_nons ]` row (00.4:57).

### I-82 `[ position_restraints ]` format line omits the `type` column  [M]  ✅ RESOLVED (2026-09-16)
Files: `00-foundations/00.4-topology-anatomy.md`
KB line 55: `| `[ position_restraints ]` | `atom  fcx  fcy  fcz` — must live in the moleculetype it belongs to |`. The build requires 5 columns (`atom  type  fcx  fcy  fcz`): a 4-column line `1  1000 1000 1000` fails with `Invalid position restraint type 1000` (the parser reads column 2 as the function type), while the 5-column line `1  1  1000 1000 1000` parses cleanly (targeted probe, 2-atom moleculetype).
**Recommended fix**: change the format to `atom  type  fcx  fcy  fcz` (function type 1 = harmonic; the 02.02 file's "per component, with `fcx/fcy/fcz`" wording stays correct).

### I-83 FEP lambda vectors use backslash line continuation, which is invalid MDP  [M]  ✅ RESOLVED (2026-09-16)
Files: `02-md-types/02.03-alchemical-free-energy.md`
KB lines 90-95 show the 31-window `coul-lambdas`/`vdw-lambdas` vectors "verbatim" with trailing `\` continuations. The build's MDP parser is line-based and has no backslash continuation: the suite block probe (`blocks/block_007.mdp`) fails with `ERROR 1 [file blocks/block_007.mdp, line 13]: Invalid value \ in string in mdp file. Expected a real number.` Minimal repro (`coul-lambdas = 0.00 0.10 0.20 \` + continuation line) → `Invalid value \n in string in mdp file. Expected a real number.`; a single-line vector parses with no such error. A bare multi-line vector (no backslash) is also rejected: `No '=' to separate .mdp parameter key and value was found on line: '  0.30 0.40'`.
**Recommended fix**: re-emit each vector on a single line (31 values each; the values themselves are correct). Drop the trailing `\` characters.

## Verified OK (this pass)
- **Drift gate**: build fingerprint `2026.3-dev-20260625-1210900-unknown` byte-identical to the 2026-09-14/15 baseline; KB changed only by `3e57b3d` (C-01, `00.6` + ticket file); working tree clean.
- **All 30 KB MDP blocks**: zero parse signals (`unknown=invalid=obsolete=0`) after the suite's context-parent injection. Every block error/NOTE is a known artifact (1-atom dummy-system noise, `gen-vel`/`continuation` probe artifact, AWH force-constant NOTE, lambda-state NOTE on the `02.03` delta block). No legacy-alias/deprecation NOTEs.
- **Matrix**: unchanged from baseline; the `Unknown left-hand` lines are the known false-positive classes (topology/pull directives as inline prose spans; `expanded`/`lmc` documented as gone and rejected by the build).
- **00.1–00.5**: version/install claims, command inventory (101 commands), file formats, topology anatomy (all table rows except I-80…I-82), MDP anatomy (MTTK requires Velocity-verlet).
- **00.6 (incl. new C-01 content)**: all 4 referenced FFs present; CHARMM36 correctly noted absent; water/ion file listings match `03_ff_listing.txt`; top-level water `.itp` stubs are `#error` with the KB-quoted text; new carbohydrate (GLYCAM) and inorganic-species sections verified against the build's FF listing and `ant2gmx`/`pdb2gmx` surface.
- **01.1–01.9**: phase playbooks, EM/NVT/NPT blocks, solvation/ions (`gmx solvate`/`ionize` flags), analysis tools, `energygrps` mechanism (01.8), troubleshooting error strings (01.9 — reproduced verbatim).
- **02.01–02.16**: all MD-type files; probe-matrix error strings exact (02.14, 02.16); `gmx insert-molecules` flags (02.15); FEP/LMC semantics (02.03/02.06); metadynamics/AWH/Colvars (02.05); QMMM/NNPot (02.10/02.11 — LibTorch abort verbatim); membranes (02.13); virtual sites (02.16).
- **03.1–03.5**: decision trees, MDP templates (all 10 blocks), checklists, failure diagnosis, performance (env-var inventory incl. `GMX_SIMD` CMake-flag framing).
- **README**: file map matches the tree; `group`/`ns` cutoff-scheme removal framing consistent with the build (`ns` gone; `group` redirects to Verlet); `annealing = group` silently accepted with TPR written (targeted probe); MTTK deprecation framing; API-breakage list (pull, FEP, expanded, annealing, Langevin, thermostats, AWH, modules, removed tools, `-maxwarn`) all re-confirmed.
- **Suite**: context-parent injection added to `probe_suite.sh` (block context header); `block_010` (`02.04:111-114` pull delta block) now `unknown=0` — the prior `unknown=3` was a probe-context artifact, not a KB issue.

## Notes
- **No build drift; KB drift = C-01 content pass** (`3e57b3d`, `00.6` carbohydrate + inorganic sections). The 4 new issues are in `00.4` (3) and `02.03` (1) — pre-existing content, not C-01; the C-01 additions verified clean.
- **Runtime-only claims not re-verified** (require `mdrun`/GPU, out of scope for a CPU-only audit): PLUMED thread-MPI incompatibility (02.05), GPU-resident-update all-bonds→CPU-fallback behavior (01.7/03.5 — static side verified), MTS throughput (03.5).
- **Probe artifacts**: `work/kb-audit/` (suite re-run this pass, incl. `blocks/block_007.mdp` log for I-83, `directives/nonbonded_a.log` / `directives/cgenff_nons_a.log` for I-80/I-81) + ad-hoc targeted probes (position-restraint 4-col vs 5-col, backslash-continuation minimal repro + single-line control, multi-line-no-backslash control, `annealing = group` TPR probe, `[ nonbonded ]` at 4 moleculetype positions).

## Fix pass (2026-09-16 — build 2026.3-dev-20260625-1210900-unknown)

**Scope:** 4 open issues (I-80…I-83) from the 2026-09-16 fifth-pass full-KB audit.
**Result:** 4 fixed, 0 already-fixed (closed), 0 false-positive (closed), 0 left open.

#### I-80 moleculetype table lists a `[ nonbonded ]` section that does not exist in the build — FIXED  ✅ RESOLVED (2026-09-16)
Files: `00-foundations/00.4-topology-anatomy.md`
- **Preflight**: re-probed `[ nonbonded ]` inside a 2-atom DUM moleculetype (after `[ bonds ]`) → `ERROR 1 [file i80_nb.top, line 17]: Invalid directive nonbonded`. Issue confirmed still real.
- **Applied**: deleted the `[ nonbonded ]` row (00.4:56), adopting the recommended fix's *optional* replacement variant, merged with the I-81 row into one informational row: `| (none) | Nonbonded parameters come from `[ atomtypes ]` (per atom type); 1-4 interactions from `[ pairs ]` / top-level `[ pairtypes ]` — there is no `[ nonbonded ]` or `[ cgenff_nons ]` section |`.
- **Evidence**: fix-text tokens verified against the build — `[ pairtypes ]` top-level section accepted by grompp (minimal top with `[ atomtypes ]` + `[ pairtypes ]` + 1-atom moleculetype: no directive error); `[ atomtypes ]`/`[ pairs ]` parse (used throughout the probe tops). Re-probe output above: `Invalid directive nonbonded`.

#### I-81 moleculetype table lists a `[ cgenff_nons ]` section that does not exist in the build — FIXED  ✅ RESOLVED (2026-09-16)
Files: `00-foundations/00.4-topology-anatomy.md`
- **Preflight**: re-probed `[ cgenff_nons ]` inside the 2-atom DUM moleculetype → `ERROR 1 [file i81_cg.top, line 17]: Invalid directive cgenff_nons`; `strings /usr/local/gromacs/lib/libgromacs.so | grep -ci cgenff` → `0`. Issue confirmed still real.
- **Applied**: deleted the `[ cgenff_nons ]` row (00.4:57); merged into the same informational row as I-80 (which names both removed sections as absent).
- **Evidence**: verbatim re-probe output above (directive rejected + zero `cgenff` hits in the binary).

#### I-82 `[ position_restraints ]` format line omits the `type` column — FIXED  ✅ RESOLVED (2026-09-16)
Files: `00-foundations/00.4-topology-anatomy.md`
- **Preflight**: 4-col line `1  1000 1000 1000` → `Invalid position restraint type 1000` (parser reads column 2 as the function type); 5-col line `1  1  1000 1000 1000` passes the restraint line. Issue confirmed still real.
- **Applied**: `atom  fcx  fcy  fcz` → `atom  type  fcx  fcy  fcz` (00.4:55).
- **Evidence**: 5-col grompp output: no `Invalid position restraint` error; topology fully processed (`Generated 331705 of the 331705 non-bonded parameter combinations`); only the known zero-box dummy-system artifacts remain (`Empty diagonal for a 3-dimensional periodic box`, cutoff > half box).

#### I-83 FEP lambda vectors use backslash line continuation, which is invalid MDP — FIXED  ✅ RESOLVED (2026-09-16)
Files: `02-md-types/02.03-alchemical-free-energy.md`
- **Preflight**: minimal repro (`coul-lambdas = 0.00 0.10 0.20 \` + continuation line `0.30 0.40`) → `ERROR 1 [file i83_bs.mdp, line 6]: No '=' to separate .mdp parameter key and value was found on line: '               0.30 0.40'` (the suite's block probe hits the same defect as `Invalid value \ in string in mdp file`). Issue confirmed still real.
- **Applied**: re-emitted both 31-element vectors on single lines (02.03:90-95 → 90-91); dropped the trailing `\` characters. Values unchanged.
- **Evidence**: single-line 31-value `coul-lambdas`/`vdw-lambdas` + `init-lambda-state = 0` + `couple-lambda0 = vdw-q`/`couple-lambda1 = none` → grompp reports no lambda parse error (only the 2 known zero-box artifacts). Post-fix suite: `block_007.mdp (02-md-types/02.03-alchemical-free-energy.md:90-91) exit=1 unknown=0 invalid=0 obsolete=0 errors=2 notes=1` (baseline `errors=4` — the 2 backslash errors gone).

## Notes for the auditor
- **Regression suite (post-fix)**: 30 blocks probed; `03_block_verdicts.txt` identical to the pre-fix baseline except `block_007` `errors=4 → 2` (the I-83 backslash errors resolved; remaining 2 = known zero-box artifacts); `03_matrix_verdicts.txt` byte-identical (the 5 documented false-positive classes). No new parse signals.
- **Stale-text sweep** (KB excl. `issues_kb.md`): zero hits for the I-80/I-81/I-82/I-83 old texts, except the new negative-framing row at `00.4:56` itself (documented false hit, class (b)).
- **Fix-pass probe artifacts**: `work/kb-audit/fixprobes/` (`run_all.sh` / `run_full.sh` + generated tops/mdps) — session dir is wiped by the next suite run; repros are self-contained in the two scripts.

## New issues from full-KB audit (2026-09-16 — sixth pass)

**Method:** All 34 KB content files re-read (`00-foundations` → `01-phases` →
`02-md-types` → `03-playbooks`); every fenced MDP block re-probed through
`gmx grompp` in the transient CPU-only container (30 blocks, zero parse
signals); merged existence matrix re-checked (136 unique options); tool CLIs
re-checked against `snapshot/02_help/<tool>.txt`; topology directive names
re-checked against `06_directive_verdicts.txt`; semantic prose claims
(thermostat/barostat compatibility, removed-option lists, error strings,
`-maxwarn` behavior, MTS, benchmark) reproduced with targeted grompp probes.
CPU-only grompp / tool probes only — no MD run.
**Result:** 1 new issue (I-84), confirmed real against the build.

### I-84 `disre = yes` is not a valid enum value — the build's `disre` is `no`/`simple`/`ensemble`  [M]  ✅ RESOLVED (2026-09-16)
Files: `02-md-types/02.03-alchemical-free-energy.md`
KB line 181 (the "2026.3 section formats" list) says the NMR-style
`[ distance_restraints ]` directive "needs `disre = yes`". The build's `disre`
enum is `No`/`Simple`/`Ensemble` (case-insensitive `no`/`simple`/`ensemble`);
`yes` is not a member. Targeted probe (`disre = yes` on a minimal MDP) →
`ERROR 1 [file adhoc/disre1.mdp, line 4]: Invalid enum 'yes' for variable
disre, using 'No'`, grompp exit 1 (aborts). The same claim is re-verified by
the suite's merged matrix (`03_matrix_verdicts.txt` line 23: `Invalid enum
'yes' for variable disre, using 'No'`). The value that actually enables the
NMR-style restraints is `disre = simple` (probe `disre = simple` → grompp
accepts it; only the known zero-temperature dummy-system NOTE remains). Note
the failure mode: with `-maxwarn` the invalid value is downgraded to a warning
and `disre` silently defaults to `No`, so the restraints would be **off** —
wrong results, not just an abort.
**Recommended fix**: at `02.03:181`, change "needs `disre = yes`" → "needs
`disre = simple`" (or `ensemble`, per the restraint type). Do not change the
option name `disre` — only the value.

## Verified OK (this pass)
- **Drift gate**: build fingerprint `2026.3-dev-20260625-1210900-unknown`
  byte-identical to the 2026-09-14/15/16 baseline; working tree clean.
- **All 30 KB MDP blocks**: zero parse signals (`unknown=invalid=obsolete=0`)
  after the suite's context-parent injection. Every block error/NOTE is a known
  artifact (1-atom dummy-system noise, AWH force-constant NOTE, lambda-state
  NOTE). No legacy-alias/deprecation NOTEs.
- **Matrix**: the only real signal is `disre = yes` (I-84); the remaining
  `Unknown left-hand` lines (`nrexcl`, `fc`, `start`, `type`, `a`, `dim`,
  `geometry`, `rate`, `k`, `r0`) are the documented false-positive class (a) —
  topology/pull directives appearing as inline prose spans, not MDP options.
- **00.1–00.6**: version/install claims, 101-command inventory, file formats,
  topology anatomy, MDP anatomy, FF/water listings (all 4 referenced FFs
  present; CHARMM36 correctly noted absent).
- **01.1–01.9**: phase playbooks, EM/NVT/NPT blocks, solvation/ions flags,
  analysis tools, `energygrps`, troubleshooting error strings (reproduced
  verbatim).
- **02.01–02.16**: all MD-type files. Re-confirmed this pass: integrator
  removals (`langevin`/`brownian`/`npt`/`qmmm` rejected; `tpi`/`tpic` valid);
  `tcoupl = Andersen`/`Andersen-massive` ARE valid tcoupl values (set to `no`
  with `sd`/`bd`; NOT supported with `md`); `pcoupl = Isotropic` correctly
  framed as a legacy Berendsen alias (02.01:21, 02.13); pull API (02.04/02.07);
  FEP soft-core + lambda options (02.03/03.2); AWH dim options (02.05/03.2);
  `lmc-stats = min-variance` rejected (use `minvar`, 02.06); QMMM `qmmm = yes`
  hard-error string exact (02.10); NNPot LibTorch abort string exact +
  `nnpot-mm-group`/`nnpot-nnp-charge` absent (02.11); semiisotropic needs
  exactly 2 values (02.13); FMM `coulombtype = FMM` requirement + error string
  (02.14); `com-pull`/`enforced-rotation`/`shell` removed (02.14);
  `insert-molecules`/`principal` flags (02.15/02.16); MTS options (03.5);
  `gmx benchmark` gone, `nonbonded-benchmark` flags incl. `-all` (03.5).
- **03.1–03.5**: decision trees, all 10 MDP templates, checklists (incl. the
  `-maxwarn` downgrades-"Unknown left-hand"-to-warning claim — reproduced),
  failure diagnosis (7 removed old option names all `Unknown left-hand`),
  performance (`--version` HIP flags show `--offload-arch=gfx1100`; `-npme`
  default -1).
- **README**: file map matches the tree (00–03, no `03-analysis` dir);
  API-breakage list consistent with the build.

## Notes
- **No build drift; working tree clean.** Single finding (I-84) is in pre-existing
  `02.03` prose, not a fenced block — which is why the block suite is clean and
  only the matrix surfaces it.
- **Two candidate findings retracted after re-verification** (not filed):
  (1) `pcoupl = Isotropic` — 02.01:21 already frames it as a legacy Berendsen
  alias; (2) `Andersen`/`Andersen-massive` as tcoupl values — they ARE valid
  tcoupl enums (02.08/02.01 correct).
- **Runtime-only claims not re-verified** (require `mdrun`/GPU, out of scope for
  a CPU-only audit): PLUMED thread-MPI incompatibility (02.05),
  GPU-resident-update all-bonds→CPU-fallback (01.7/03.5), MTS throughput (03.5),
  NNPot/QMMM activation past group-validation (02.10/02.11 — grompp-side
  abort strings verified via binary + targeted probe).
- **Probe artifacts**: `work/kb-audit/adhoc/` (targeted probes: `disre1/2.mdp`,
  `and1-4.mdp`, `semi1/2.mdp`, `fmm1/2.mdp`, `awh2/3.mdp`, `fep3.mdp`, `mts1.mdp`,
  `maxwarn1.mdp`, `oldnames.mdp`, `qmmm1/2.mdp`, `nnpot1/2.mdp`, `pullorigin.mdp`,
  `bd1.mdp`, `anneal1.mdp`, `colvars.mdp`, `tpi1.mdp`, `efield.mdp`, `lmcminvar.mdp`).

## Fix pass (2026-09-16 — build 2026.3-dev-20260625-1210900-unknown)

**Scope:** 1 open issue (I-84) from the 2026-09-16 sixth-pass full-KB audit.
**Result:** 1 fixed, 0 already-fixed (closed), 0 false-positive (closed), 0 left open.

#### I-84 `disre = yes` is not a valid enum value — the build's `disre` is `no`/`simple`/`ensemble` — FIXED  ✅ RESOLVED (2026-09-16)
Files: `02-md-types/02.03-alchemical-free-energy.md` (as listed in the issue)
- **Preflight**: re-ran the minimal probe in a transient CPU-only container (grompp, `base.mdp` + `disre = yes`) → `ERROR 1 [file adhoc/disre_yes.mdp, line 5]: Invalid enum 'yes' for variable disre, using 'No'`, grompp exit 1. Issue confirmed still real.
- **Applied**: `02.03:181` "needs `disre = yes`" → "needs `disre = simple`" (option name unchanged, value only — as recommended; no deviation).
- **Evidence**: `disre = simple` → grompp exit 0 (only the known zero-temperature dummy-system NOTE); `disre = ensemble` → grompp exit 0 (same NOTE); `disre = yes` → exit 1, `Invalid enum 'yes' for variable disre, using 'No'`. Post-fix suite: `03_block_verdicts.txt` byte-identical to the pre-fix baseline (30 blocks, all `unknown=invalid=obsolete=0`); `03_matrix_verdicts.txt` diff vs baseline = only the `Invalid enum 'yes' for variable disre, using 'No'` line removed; remaining lines are the documented false-positive class (a).
- **Stale-text sweep**: old text `disre = yes` survives only in dated T-01 ticket log entries in `tickets_lemkul_import.md` (lines 232, 863 — 2026-09-15 ticket-pass record, documented false-positive class (b)); no stragglers.

## Notes for the auditor
- **Regression suite (post-fix)**: 30 blocks probed; `03_block_verdicts.txt` byte-identical to the pre-fix baseline; `03_matrix_verdicts.txt` = baseline minus the I-84 `disre` line (documented false-positive class (a) lines persist). No new parse signals.
- **Fix-pass probe repro**: `base.mdp` + one appended `disre = <yes|simple|ensemble>` line, grompp with `tmin.gro`/`tmin.top` in the transient container (session dir is wiped by the next suite run).

---

## New issues from T-coupling audit (2026-09-20 — seventh pass)

**Method:** probe suite enhanced (this pass) to (a) flag `exit≠0`/`Fatal error` as a
needs-attention signal, not just unknown/invalid/obsolete, and (b) probe every KB MDP
block against a **protein + water** asset (`assets/probe.gro`/`probe.top`, single ALA +
SPC) instead of the 1-atom DUM — the DUM leaves `Protein`/`Non-Protein` empty so the
T-coupling count check never fired (the blind spot behind A4 in
`issues_agent_run.md`). Full suite re-run: build snapshot + 40 KB files + 30 block
probes + 23 directive probes, CPU-only transient containers (no GPU, no mode switch).
**Result:** 1 new issue (I-85), confirmed real against the build.

### I-85 MDP templates: `tc-grps` has 2 groups but `tau-t`/`ref-t` have 1 value  [H]  ✅ RESOLVED (2026-09-20)
Files: `03-playbooks/03.2-mdp-templates.md` (lines 46-49, 89-92, 135-138, 328-331),
`01-phases/01.5-equilibration.md` (lines 20-22, 62-64), `01-phases/01.6-production.md`
(lines 19-21)

Every NVT/NPT/production template sets `tc-grps = Protein Non-Protein` (2 groups) with a
single `tau-t = 0.1` and single `ref-t = 300`. grompp requires one value per group, so it
fatals. Reproduced verbatim (probe: `kb-audit/blocks/block_021.mdp.log`, and identically
for block_002/003/005/022/023/029):

```
Fatal error:
Invalid T coupling input: 2 groups, 1 ref-t values and 1 tau-t values
```

Confirmed the fix works: the same block with `tau-t = 0.1 0.1` / `ref-t = 300 300`
resolves cleanly (grompp exit 0; `Protein` ≈ 30 DoF, `non-Protein` ≈ 9195 DoF on the
probe asset). Note the KB's own 03.2 §9 (Langevin/Brownian, lines 308-312) already states
the matching-counts rule ("tc-grps + ref-t + tau-t must all be present with matching
counts") — §2-§4 violate it. The 1-group Langevin block (03.2:304-308, `tc-grps = System`
+ single `tau-t`/`ref-t`) is correct and passes (block_028 exit 0).

**Recommended fix**: in each affected block, make `tau-t` and `ref-t` per-group to match
`tc-grps` (2 values each), e.g. `tau-t = 0.1 0.1` and `ref-t = 300 300` (or, for a
physically distinct solvent group, `tau-t = 0.1 0.05` / `ref-t = 300 300`). Apply to all
seven locations listed above. Do NOT change `tcoupl` (already valid: `v-rescale`).

### I-86 Annealing block: `annealing`/`annealing-npoints`/`-time`/`-temp` not per-group  [H]  ✅ RESOLVED (2026-09-20)
File: `03-playbooks/03.2-mdp-templates.md` §10 (Simulated annealing, lines 322-331)

The annealing block sets `tc-grps = Protein Non-Protein` (2 groups) but gives `annealing = single`
and `annealing-npoints = 4` as **single** values, with `annealing-time`/`annealing-temp` as single-group
arrays (4 values). GROMACS requires `annealing` and `annealing-npoints` to be **per tc-grp** (one value
each), and `annealing-time`/`annealing-temp` to have `ngroups × npoints` values. Reproduced (block_029,
surfaced once I-85's T-coupling fatal was fixed):

```
Fatal error:
Wrong number of annealing values: 1 (for 2 groups)
```

The KB's own comment on the `annealing` line says "(one value per tc-grp)" — the value contradicts it.
Confirmed the fix against the build: `annealing = single single`, `annealing-npoints = 4 4`,
`annealing-time = 0 10000 20000 30000 0 10000 20000 30000`, `annealing-temp = 300 300 500 300 300 300 500 300`
→ grompp exit 0, `Simulated annealing for group Protein: Single, 4 timepoints` **and**
`for group non-Protein: Single, 4 timepoints`. (Format per GROMACS issue #4800: one set of
`annealing`/`annealing-npoints` per group, values concatenated group-by-group.)

**Recommended fix**: in 03.2 §10, make all four annealing options per-group: `annealing = single single`,
`annealing-npoints = 4 4`, and duplicate the `annealing-time`/`annealing-temp` arrays (2×4 = 8 values each).

### Verified OK (this pass)
- `tcoupl` values across the KB are all valid enums (`v-rescale`, `V-rescale`, `no`);
  **no** `tcoupl = group` (the old value, now invalid in 2026.3 — see note below) appears
  in any KB file. `disre` (I-84) remains fixed.
- 03.2 §9 Langevin block (single `tc-grps = System` + single `tau-t`/`ref-t`) passes
  (block_028 exit 0).

### Notes (triage of the other probe-surfaced blocks — not KB issues)
- **Expected probe-system noise** (block references a group the minimal protein+water
  asset lacks; correct on a real system): block_006 (`Group JZ4 … not found`),
  block_015 (`Group Protein_DPPC … not found`), block_024 (`Did not find any molecules of
  type 'LIG' for coupling`).
- **Probe limitations** (grompp cannot validate the specialized setup on the minimal
  asset): block_007 (free-energy `Lambda state must be set` — fragment lacks
  `init-lambda`), block_011 (metadynamics/colvars → grompp SIGSEGV, exit 139), block_019
  (large-cutoff `rvdw` > half-box, documented false-positive class), block_027 (C-rescale
  delta block without ensemble temperature).
- **`tcoupl = group` is no longer a valid enum** in 2026.3 (valid: `No` `Berendsen`
  `Nose-Hoover` `yes` `Andersen`). Not a KB issue (the KB uses `v-rescale`/`no`), but the
  **skill assets** (`gromacs-sim/assets/{nvt,npt,md}.mdp`) must be checked for it — see
  `issues_agent_run.md` A4b. Group T-coupling is now `tcoupl = yes` + `tc-grps`.
- **Probe-suite changes (this pass):** `probe_suite.sh` now (1) flags `exit≠0`/`Fatal`
  in the needs-attention trigger, (2) probes blocks against `probe.gro`/`probe.top` with
  `-maxwarn 5`, (3) defaults context-header `gen-vel`/`continuation` to `no` (injecting
  `yes`+`yes` is a hard grompp error that masked real verdicts). Documented in
  `assets/README.md`.

---

## Fix pass (2026-09-20 — build 2026.3-dev-20260625-1210900-unknown)

**Scope:** 1 open issue (I-85) from the 2026-09-20 seventh-pass T-coupling audit.
**Result:** 1 fixed, 0 already-fixed (closed), 0 false-positive (closed), 0 left open.

#### I-85 MDP templates: `tc-grps` has 2 groups but `tau-t`/`ref-t` have 1 value — FIXED  ✅ RESOLVED (2026-09-20)
Files: `03-playbooks/03.2-mdp-templates.md`, `01-phases/01.5-equilibration.md`, `01-phases/01.6-production.md` (as listed in the issue)
- **Preflight**: re-ran the probe suite (30 blocks, protein+water asset); all 7 `tc-grps = Protein Non-Protein` blocks fataled `Invalid T coupling input: 2 groups, 1 ref-t values and 1 tau-t values` (block_002/003/005/021/022/023 + annealing block_029). Issue confirmed real. Verified fix text: `tau-t = 0.1 0.1` / `ref-t = 300 300` → grompp exit 0, `Number of degrees of freedom in T-Coupling group Protein is 29.99 / non-Protein is 9195.01`.
- **Applied**: in all 7 blocks, `tau-t = 0.1` → `tau-t = 0.1 0.1` and `ref-t = 300` → `ref-t = 300 300` (per-group, matching the 2-group `tc-grps`). 03.2: NVT(§2), NPT(§3), Production(§4), Annealing(§10); 01.5: NVT + NPT; 01.6: production. `tcoupl` unchanged (already valid `v-rescale`).
- **Evidence**: post-fix suite: block_002/003/005/021/022/023 now exit=0 fatal=0; `grep -l "Invalid T coupling" blocks/*.log` = 0 files. Matrix verdicts byte-identical to baseline (T-coupling is a count check, not a parse signal). No new parse signals (unknown/invalid/obsolete all 0).

#### I-86 Annealing block: `annealing`/`annealing-npoints`/`-time`/`-temp` not per-group — FIXED  ✅ RESOLVED (2026-09-20)
Files: `03-playbooks/03.2-mdp-templates.md` §10 (as listed in the issue)
- **Preflight**: block_029 fataled `Wrong number of annealing values: 1 (for 2 groups)` (surfaced after I-85's T-coupling fix). Root cause: `annealing`/`annealing-npoints` given as single values for 2 tc-grps. Verified fix text (per GROMACS issue #4800): `annealing = single single`, `annealing-npoints = 4 4`, per-group `annealing-time`/`-temp` (8 values each) → grompp exit 0, `Simulated annealing for group Protein: Single, 4 timepoints` + `for group non-Protein: Single, 4 timepoints`.
- **Applied**: 03.2 §10: `annealing = single` → `single single`; `annealing-npoints = 4` → `4 4`; `annealing-time`/`annealing-temp` duplicated to 2×4 = 8 values each.
- **Evidence**: post-fix suite: block_029 exit=0 fatal=0; `grep -l "annealing values" blocks/*.log` = 0 files. No new parse signals.

## Notes for the auditor
- **New finding (not fixed, per fixer scope):** the annealing block (03.2 §10, block_029) now fatales `Wrong number of annealing values: 1 (for 2 groups)` once the T-coupling is fixed — its `annealing-time`/`annealing-temp` are single-group (4 values) but `tc-grps` has 2 groups. Tried 8 values (2×4 npoints) — still rejected; the correct per-group annealing format needs determination (candidate **I-86**).
- **Regression suite (post-fix):** 30 blocks probed; the 6 pure T-coupling blocks (002/003/005/021/022/023) went exit=1→exit=0; remaining exit=1 blocks (024 LIG, 025 AWH, 026 membrane, 027 C-rescale delta, 029 annealing) are the documented probe-limitation/system-noise class, unchanged in kind. Matrix verdicts = baseline.

---

## New issues from post-sim RCA third-pass validation (2026-09-26)

**Method:** RCA validation for the lysozym 310 K run (10 ns production, OPLS-AA/SPC/E, dodecahedron). All probes CPU-only in transient `gromacs-hip-gfx1100:latest` containers (no GPU, no stack-mode switch): `gmx dssp -h` / `gmx hbond -h` / `gmx msd -h` / `gmx trjconv -h`; live reproduction of the dssp/hbond `.xvg` extension errors and the msd `-dt`/`-trestart` error + warning; and a full MSD pipeline run on the retained 10 ns production trajectory (`trjconv` + `gmx msd`, ~5 min CPU). Build unchanged since the last audit (2026.3-dev-20260625-1210900-unknown).
**Result:** 3 new issues (I-87…I-89). The dssp `.dat` / hbond `.ndx` extension claims in 01.8 are already correct — verified OK, no issue filed.

### I-87 01.8 MSD recipe computes diffusion on a fitted trajectory — water D inflated 3×  [H]  ✅ RESOLVED (2026-09-26)
Files: `01-phases/01.8-analysis.md` (MSD row, line 73; Pitfall note, lines 39-41)

The MSD row says `gmx msd -s md.tpr -f clean.xtc -o msd.xvg` ("Einstein
relation; COM or atom"), and the (a)-section Pitfall note says "Always unwrap
(`-pbc`) and fit before those analyses." Both are wrong for diffusion: the
per-frame `-fit rot+trans -center` applied to `clean.xtc` contaminates the MSD
of atoms far from the fit group. Verified on the lysozym 10 ns production
trajectory (CPU-only): water D from `md.xtc → trjconv -pbc nojump` =
**2.87e-5 cm²/s** (literature SPC/E @310 K ≈ 2.8-3.1e-5) vs **8.90e-5 cm²/s**
(3.1×) from the same trajectory after `-pbc mol → -fit rot+trans -center →
-pbc nojump`. Isolation: `-pbc mol` alone does not change D (2.87e-5); the
fit+center step is the cause. Protein COM diffusion is removed entirely by
the fit (protein atom MSD flat at 0.08 nm² over 10 ns).
**Recommended fix**: MSD row → `gmx msd -s md.tpr -f msd_unwrapped.xtc -o msd.xvg -trestart 100` with a prep line `gmx trjconv -s md.tpr -f md.xtc -pbc nojump -o msd_unwrapped.xtc` (System in/out), and a note: **MSD needs unwrapped but NOT fitted** — derive it directly from the production xtc; a per-frame-fit trajectory inflates solvent D (~3× verified) and removes protein COM diffusion. Split the Pitfall note: RMSD/RMSF/Rg need fit; MSD needs unwrap without fit.

### I-88 01.8 MSD row missing 2026.3 `gmx msd` behavior (dt/trestart, `-mol`, no D printout)  [H]  ✅ RESOLVED (2026-09-26)
Files: `01-phases/01.8-analysis.md` (MSD row, line 73)

Three 2026.3 behaviors are absent from the MSD row, all reproduced live:
1. `-dt` must be ≤ `-trestart` (default 10 ps): on a 20-ps-subsampled
   trajectory `gmx msd -dt 20` fatales verbatim:
   `-dt cannot be larger than -trestart (default 10 ps).`
   With `-dt == -trestart` the run warns: `WARNING: -dt and -trestart are
   equal. Statistics for each tau data point will not be independent.`
2. `-mol` per-molecule output is impractical for bulk solvent: on the full
   10 ns trajectory (7380 waters) it is **Killed** (OOM, exit 137) even with
   `-trestart 100`; on a subsampled file the dt==trestart constraint makes
   per-molecule fits non-independent (D values scatter, including negative
   entries). Use the **collective** MSD (no `-mol`) for the diffusion
   coefficient.
3. 2026.3 `gmx msd` **no longer prints the fitted diffusion coefficient**
   (log ends with `Analyzed 5001 frames, last time 10000.000`); D must be
   fitted from the MSD curve: D = slope(MSD vs τ, linear regime)/6. Also:
   `-com` is gone (no such flag in `gmx msd -h`).
**Recommended fix**: extend the MSD row notes with: `-trestart` (default 10 ps) must be ≥ `-dt` (frame spacing); use `-trestart 100` on a 2 ps trajectory to bound memory; collective MSD (no `-mol`) for D; fit D from the curve (slope/6 over the linear regime, e.g. 100-2000 ps for water, 1000-5000 ps for a protein, in a 10 ns run); `-com` removed.

### I-89 01.8 hbond row missing `-r`/`-t` selections and the `hbnum.xvg` output name  [M]  ✅ RESOLVED (2026-09-26)
Files: `01-phases/01.8-analysis.md` (hbond row, line 64)

The hbond row documents the `.ndx` output and `-num` → `.xvg` (verified
correct) but omits: (a) `gmx hbond -h` shows `[-r <selection>] [-t
<selection>]` — reference/target selection options (a single group via stdin
works; `-r`/`-t` select specific reference/target groups); (b) the `-num`
output file is the **generic name `hbnum.xvg`** (dssp: `num.xvg`) — a second
hbond/dssp run in the same directory overwrites the first. Verified: the
lysozym run's `hbnum.xvg` header shows `gmx hbond ... -num -o hbond.ndx`
producing `hbnum.xvg`.
**Recommended fix**: append to the hbond row: "`-r`/`-t` select reference/target groups (single group via stdin works); `-num` writes the generic `hbnum.xvg` (dssp: `num.xvg`) — copy it to a per-analysis name in the same run."

### I-90 01.5 no practical guidance on NPT length for pressure equilibration  [M]  ✅ RESOLVED (2026-09-26)
Files: `01-phases/01.5-equilibration.md`

The KB says "pressure is noisy — do not chase the exact value" and the gate
uses a ±15 bar band, but it does not state how long NPT typically needs for a
solvated protein, so a Tier B plan can encode an insufficient NPT length.
Evidence: lysozym 310 K run (2026-09-25): 500 ps NPT **failed** the pressure
gate (last-20% mean P = 45.5 bar vs ref 1.0); 1000 ps **passed** (P = 3.5
bar). The 300 K run needed 4000 ps. See `work/projects/lysozym/POST_SIM_RCA.md`
Issue 1.
**Recommended fix**: add a practical note to 01.5: "For a solvated protein in
a dodecahedron box at 310 K, 500 ps NPT is often insufficient for pressure
equilibration. Plan for 1000 ps minimum."

### I-91 01.8 missing pitfall: xvg header lines break NR-based awk statistics  [M]  ✅ RESOLVED (2026-09-26)
Files: `01-phases/01.8-analysis.md`

The KB has no warning that xvg files begin with ~20-30 comment/header lines,
so awk statistics that index data by NR (total file line count) miscount the
data range.
Evidence: check_prod.sh drift bug (skill issue I-9, 2026-09-25): awk used NR
(5025 lines incl. ~24 header lines) as the data range for a first-10% mean,
inflating total-energy drift from 0.05% to 5.07% and failing a passing
production run. Fixed in the script with a sequential data-point counter
(`dp++`). See `work/projects/lysozym/POST_SIM_RCA.md` Issue 2.
**Recommended fix**: add a pitfall note to 01.8: "xvg files begin with
~20-30 header lines. In awk statistics, count data points sequentially
(`dp++`) — never use NR (total line count) as the data index or range."

## Verified OK (2026-09-26)
- 01.8 dssp row: `-o dssp.dat` + `-num` → `.xvg` — matches the build (`gmx dssp -h`: `[-o [<.dat>]] [-num [<.xvg>]]`; `.xvg` for `-o` fatales verbatim).
- 01.8 hbond row: `-o hbond.ndx` + `-num` → `.xvg` — matches the build (`gmx hbond -h`: `[-o [<.ndx>]] [-num [<.xvg>]]`; `.xvg` for `-o` fatales verbatim).
- 01.8 trjconv `-pbc` enum incl. `nojump` — matches the build.
- 01.8 make_ndx `name <nr> <newname>` syntax — unchanged from prior audit.

## Notes
- Source: post-sim RCA third-pass validation (lysozym, 2026-09-26); see `gromacs/work/projects/lysozym/POST_SIM_RCA.md`.
- The skill-side counterparts (analyze.sh, 07-analysis.md) are tracked in the RCA's priority table, not here.
- I-87/I-88 are the KB-side of RCA issues #5 (and the D4 finding); I-89 is the KB-side of #4. The dssp/hbond extension claims themselves needed no KB change (already correct in 01.8).

---

## Fix pass (2026-09-26 — build 2026.3-dev-20260625-1210900-unknown)

**Scope:** 5 open issues (I-87…I-91) from the 2026-09-26 audit section (post-sim RCA third-pass validation).
**Result:** 5 fixed, 0 already-fixed (closed), 0 false-positive (closed), 0 left open.

#### I-87 01.8 MSD recipe computes diffusion on a fitted trajectory — water D inflated 3× — FIXED  ✅ RESOLVED (2026-09-26)
Files: `01-phases/01.8-analysis.md` (as listed in the issue)
- **Preflight**: stale text present (MSD row line 73 `gmx msd -s md.tpr -f clean.xtc -o msd.xvg`; Pitfall lines 39-40 "Always unwrap (`-pbc`) and fit before those analyses"). Re-probe (fixer scope, CPU-only `-h`): every flag of the new command exists in the build — `gmx msd -h`: `-s`, `-f`, `-o`, `-trestart`; `gmx trjconv -h`: `-s`, `-f`, `-o`, `-pbc` enum `none, mol, res, atom, nojump, cluster, whole`. The audit's live MSD-pipeline evidence (D = 2.87e-5 cm²/s unwrapped vs 8.90e-5 after `-pbc mol → -fit rot+trans -center → -pbc nojump`) stands as the record of the issue's reality (the fixer does not re-run tools).
- **Applied**: MSD row → `gmx msd -s md.tpr -f msd_unwrapped.xtc -o msd.xvg -trestart 100` + prep line `gmx trjconv -s md.tpr -f md.xtc -pbc nojump -o msd_unwrapped.xtc` (System in/out) + note "**MSD needs unwrapped but NOT fitted**". Pitfall note split: "RMSD/RMSF/Rg need unwrap (`-pbc`) **and** fit; MSD needs unwrap (`-pbc nojump`) **without** fit (see the MSD row)." Same-file stale claim also corrected (Common pitfalls line 199): "Not unwrapping/fitting before MSD/RMSD." → "Not unwrapping before MSD/RMSD (fit before RMSD/RMSF/Rg — but **not** before MSD; see the MSD row)."
- **Evidence**: `gmx msd -h` (2026.3-dev-20260625): `-o      [<.xvg>]           (msdout.xvg)       (Opt.)`, `-trestart <real>           (10)  Time between restarting points in trajectory (ps)`; `gmx trjconv -h`: `-pbc    <enum>             (none)  PBC treatment (see help text for full description): none, mol, res, atom, nojump, cluster, whole`.
- **Straggler (same stale claim, outside the Files: list)**: `01-phases/01.10-cleanup-retention.md` derived the MSD input from the fitted trajectory — regeneration path "`msd_sub.xtc` from `clean.xtc`: `gmx trjconv -dt 20` (all-atoms group)". Fixed with the same verified text: "`msd_sub.xtc` from `md.xtc`: `gmx trjconv -s md.tpr -f md.xtc -pbc nojump -dt 20 -o msd_sub.xtc` (all-atoms group; **no fit** — MSD needs unwrapped, not fitted; see the 01.8 MSD row)."; retention-table rationale "Regenerable from `md.xtc`/`clean.xtc` (below)" → "Regenerable from `md.xtc` (below)". `trjconv -dt` verified in `snapshot/02_help/trjconv.txt` (`-dt     <time>             (0)`).

#### I-88 01.8 MSD row missing 2026.3 `gmx msd` behavior (dt/trestart, `-mol`, no D printout) — FIXED  ✅ RESOLVED (2026-09-26)
Files: `01-phases/01.8-analysis.md` (as listed in the issue)
- **Preflight**: stale text present (MSD row carried no dt/trestart/`-mol`/D-fitting notes). Re-probe: `gmx msd -h` — `-dt <time> (0)`, `-trestart <real> (10)`, `-mol [<.xvg>] (diff_mol.xvg)` all present; **no `-com` flag** (removed). The audit's live reproductions (the verbatim `-dt cannot be larger than -trestart (default 10 ps).` fatal, the `-mol` OOM on 7380 waters, the log ending `Analyzed 5001 frames, last time 10000.000` with no D printout) stand as the record.
- **Applied**: MSD row note extended: "**2026.3:** `-trestart` (default 10 ps) must be ≥ `-dt` (frame spacing); use `-trestart 100` on a 2 ps trajectory to bound memory; collective MSD (no `-mol`) for D; fit D from the curve (slope/6 over the linear regime, e.g. 100-2000 ps for water, 1000-5000 ps for a protein, in a 10 ns run); `-com` removed."
- **Evidence**: `gmx msd -h` synopsis: `gmx msd [-f [<.xtc/.trr/...>]] [-s [<.tpr/.gro/...>]] [-n [<.ndx>]] [-o [<.xvg>]] [-mol [<.xvg>]] [-b <time>] [-e <time>] [-dt <time>] [-tu <enum>] [-fgroup <selection>] [-xvg <enum>] [-[no]rmpbc] [-[no]pbc] [-sf <file>] [-selrpos <enum>] [-seltype <enum>] [-sel <selection>] [-type <enum>] [-lateral <enum>] [-trestart <real>] [-maxtau <real>] [-beginfit <real>] [-endfit <real>]` — no `-com`; `-trestart <real> (10)`.

#### I-89 01.8 hbond row missing `-r`/`-t` selections and the `hbnum.xvg` output name — FIXED  ✅ RESOLVED (2026-09-26)
Files: `01-phases/01.8-analysis.md` (as listed in the issue)
- **Preflight**: stale text present (hbond row documented only `-o`/`-num`/`-dist`/`-ang`/`-dan`). Re-probe: `gmx hbond -h` synopsis includes `[-r <selection>] [-t <selection>]`; description: "-r specifies reference selection, relative to which the search for hydrogen bonds in target selection will develop. … -t specifies target selection, …". `gmx dssp -h`: `-num    [<.xvg>]           (num.xvg)        (Opt.)`. `hbnum.xvg`: `strings /usr/local/gromacs/lib/libgromacs.so | grep hbnum` → `hbnum` (the deffnm of the hbond `-num` output), plus the audit's live reproduction (the lysozym run's `hbnum.xvg` header).
- **Applied**: hbond row appended: "`-r`/`-t` select reference/target groups (single group via stdin works); `-num` writes the generic `hbnum.xvg` (dssp: `num.xvg`) — copy it to a per-analysis name in the same run."
- **Evidence**: `gmx hbond -h`: `[-r <selection>] [-t <selection>]`; `gmx dssp -h`: `-num    [<.xvg>]           (num.xvg)`; `strings libgromacs.so` → `hbnum`.

#### I-90 01.5 no practical guidance on NPT length for pressure equilibration — FIXED  ✅ RESOLVED (2026-09-26)
Files: `01-phases/01.5-equilibration.md` (as listed in the issue)
- **Preflight**: confirmed — 01.5 carries "do not extend equilibration to chase the exact value" and the generic "Typical length: 0.5–2 ns", but no practical NPT-length guidance for pressure equilibration. No build-visible tokens in the fix text (experience/guidance claim from the lysozym RCA: 500 ps failed the pressure gate, 1000 ps passed, the 300 K run needed 4000 ps).
- **Applied**: bullet added to "NPT convergence: pressure and density": "**NPT length**: for a solvated protein in a dodecahedron box at 310 K, 500 ps NPT is often insufficient for pressure equilibration (repo: lysozym 310 K — 500 ps failed the pressure gate, 1000 ps passed; a 300 K run needed 4000 ps). **Plan for 1000 ps minimum.**"
- **Evidence**: n/a (guidance note; no build-visible tokens). Repo evidence: lysozym 310 K run (2026-09-25), `work/projects/lysozym/POST_SIM_RCA.md` Issue 1.

#### I-91 01.8 missing pitfall: xvg header lines break NR-based awk statistics — FIXED  ✅ RESOLVED (2026-09-26)
Files: `01-phases/01.8-analysis.md` (as listed in the issue)
- **Preflight**: confirmed — 01.8 carries no xvg-header warning (grep "header" = 0 hits). No build-visible tokens in the fix text (awk pitfall from the check_prod.sh drift bug, skill issue I-9, 2026-09-25).
- **Applied**: bullet added to "Common pitfalls": "**xvg header lines break NR-based awk statistics**: xvg files begin with ~20-30 header lines; in awk statistics count data points sequentially (`dp++`) — never use NR (total line count) as the data index or range."
- **Evidence**: n/a (pitfall note; no build-visible tokens).

## Notes for the auditor
- **Straggler fixed (project convention):** `01-phases/01.10-cleanup-retention.md` carried the same I-87 stale claim (MSD input `msd_sub.xtc` derived from the fitted `clean.xtc`); fixed with the same verified text (see the I-87 entry).
- **Regression suite (post-fix, final state):** 30 blocks probed; block verdicts identical to the pre-fix baseline apart from line-number shifts caused by the added prose; zero parse signals (unknown/invalid/obsolete = 0 on every block); matrix verdicts identical (documented false-positive class (a) lines only). New CLI claims introduced by the fixes (`gmx msd -s -f -o -trestart`, `gmx trjconv -s -f -pbc -o`, `gmx trjconv -s -f -pbc -dt -o`) all map to existing flags in `snapshot/02_help/{msd,trjconv}.txt`.
- **Stale-text sweep:** `gmx msd -s md.tpr -f clean.xtc` = 0 hits; "Always unwrap" / "fit before those analyses" = 0 hits; remaining `clean.xtc` mentions are the RMSD row (01.8, correct — RMSD needs fit) and 01.10 file-listing prose (no derivation claim).
- No new problems discovered for the next audit.

## New issues from cross-validation audit (2026-09-26)

**Method:** Targeted cross-validation of KB 01.10 against the gromacs-sim skill's validated analysis pipeline (lysozym fix session 2026-09-26, D values independently reproduced twice). The skill's `_suite.sh` now writes `msd_unwrapped.xtc` via `gmx trjconv -s md.tpr -f md.xtc -pbc nojump -o msd_unwrapped.xtc` (no subsample) and its cleanup whitelist carries that name. CLI claims re-probed via `gmx trjconv -h` in a transient CPU-only container.
**Result:** 1 new issue (I-92), confirmed real against the build.

### I-92 01.10 MSD intermediate name/pipeline diverges from the skill's validated pipeline  [M]  ✅ RESOLVED (2026-09-26)
Files: `01-phases/01.10-cleanup-retention.md`
The KB claims (line 16): "Each run re-writes `clean.xtc`, `step1.xtc`, `msd_sub.xtc`, every …"; (line 35, retention table): "`07_analysis/msd_sub.xtc` (10th-frame subsample)"; (line 56, regeneration): "`msd_sub.xtc` from `md.xtc`: `gmx trjconv -s md.tpr -f md.xtc -pbc nojump -dt 20 -o msd_sub.xtc` (all-atoms group; **no fit** — MSD needs unwrapped, not fitted; see the 01.8 MSD row)." The skill's validated pipeline (lysozym fix session 2026-09-26; water D = 2.8695e-05 cm²/s reproduced by two independent runs) writes `msd_unwrapped.xtc` **without** the `-dt 20` subsample: `gmx trjconv -s md.tpr -f md.xtc -pbc nojump -o msd_unwrapped.xtc`. The retention table is meant to mirror the skill's cleanup whitelist, which lists `msd_unwrapped.xtc` — a project following the skill leaves `msd_unwrapped.xtc` behind, which the KB table does not name.
**Recommended fix**: In `01-phases/01.10-cleanup-retention.md`, align all three occurrences with the skill's validated pipeline: (a) line 16 `msd_sub.xtc` → `msd_unwrapped.xtc`; (b) retention-table row `07_analysis/msd_sub.xtc` (10th-frame subsample) → `07_analysis/msd_unwrapped.xtc` (unwrapped, no fit); (c) regeneration line → "`msd_unwrapped.xtc` from `md.xtc`: `gmx trjconv -s md.tpr -f md.xtc -pbc nojump -o msd_unwrapped.xtc` (all-atoms group; **no fit** — MSD needs unwrapped, not fitted; see the 01.8 MSD row)."

**Verified OK**: `gmx trjconv -h`: `-pbc <enum> (none)` (nojump is a valid enum — used by the validated pipeline), `-dt <time> (0)`, `-o [<.xtc>] (traj.xtc)`. The 01.8 MSD row already matches the skill's pipeline exactly (name, flags, D-fit ranges 100-2000 / 1000-5000 ps).
**Notes**: the old `-dt 20` variant is build-valid (a subsampled input works with `-trestart 100` ≥ `-dt`), so this is a consistency issue, not a correctness issue.


## Fix pass (2026-09-26 — build 2026.3-dev-20260625-1210900)

**Scope:** 1 open issue (I-92) from the 2026-09-26 cross-validation audit.
**Result:** 1 fixed, 0 already-fixed, 0 false-positive, 0 left open.

#### I-92 01.10 MSD intermediate name/pipeline diverges from the skill's validated pipeline — FIXED  ✅ RESOLVED (2026-09-26)
Files: `01-phases/01.10-cleanup-retention.md` (as listed in the issue)
- **Preflight**: stale text present (all three `msd_sub.xtc` occurrences). Re-probe: `gmx trjconv -h` — `-pbc <enum> (none)`, `-dt <time> (0)`, `-o [<.xtc/.trr/...>] (trajout.xtc)`; the skill's validated pipeline command (`-pbc nojump`, no `-dt`) is build-valid and produced the validated D values (lysozym fix session 2026-09-26, two independent runs).
- **Applied**: (a) bloat-source line `msd_sub.xtc` → `msd_unwrapped.xtc`; (b) retention-table row → `07_analysis/msd_unwrapped.xtc` (unwrapped, no fit); (c) regeneration line → "`msd_unwrapped.xtc` from `md.xtc`: `gmx trjconv -s md.tpr -f md.xtc -pbc nojump -o msd_unwrapped.xtc` (all-atoms group; **no fit** — MSD needs unwrapped, not fitted; see the 01.8 MSD row).".
- **Evidence**: `gmx trjconv -h` (snapshot/02_help/trjconv.txt): `-o      [<.xtc/.trr/...>]  (trajout.xtc)`, `-dt     <time>             (0)`, `-pbc    <enum>             (none)`.

## Notes for the auditor
- **Stale-text sweep**: `msd_sub.xtc` = 0 hits in KB content files (only the append-only issues_kb.md history entries remain, as expected).
- **Regression suite (post-fix, final state):** 30 blocks probed; zero parse signals (unknown/invalid/obsolete = 0 on every block); matrix verdicts identical to the documented false-positive class (a) baseline. Prose-only change — no MDP blocks affected; the only CLI tokens in the new text (`gmx trjconv -s -f -pbc -o`) map to existing flags in `snapshot/02_help/trjconv.txt`.
- No new problems discovered for the next audit.

---

## New issues from full-KB audit (2026-09-26 — eighth pass)

**Method:** All 32 KB content files + `README.md` re-read end-to-end (`00-foundations` → `01-phases` → `02-md-types` → `03-playbooks`). Every fenced MDP block re-probed through `gmx grompp` in the transient CPU-only `gromacs-hip-gfx1100:latest` container; tool CLIs re-checked against `snapshot/02_help/<tool>.txt`; topology directive names re-checked against `06_directive_verdicts.txt`; the `pdb2gmx` output format re-checked with a fresh `pdb2gmx` run on a minimal PDB (OPLS-AA, single ALA residue). CPU-only grompp / tool probes only — no MD run, no GPU.
**Result:** 1 new issue (I-93), confirmed real against the build.

### I-93 01.2 claims `pdb2gmx` omits the `[ moleculetype ]`/`[ atoms ]` headers — the build writes both  [M]  ✅ RESOLVED (2026-09-26)
Files: `01-phases/01.2-topology-forcefield.md` (lines 47-52, 54-55)

The KB says (lines 47-52): "**Section headers are omitted** (2026.3, verified): `pdb2gmx` writes the atom block with **no `[ moleculetype ]` and no `[ atoms ]` headers** — the name line (`Protein_chain_A 3`) sits directly above the atoms, which run until `[ bonds ]`. `grompp` parses this fine; scripts that parse the topology must not anchor on those headers (match atom lines by content: numeric `$1`, ≥7 fields, numeric charge in column 7)." The build does the opposite: a fresh `gmx pdb2gmx` run (OPLS-AA, single ALA residue) writes BOTH headers — `[ moleculetype ]` (line 5), the name line (`Protein_chain_A 3`), then `[ atoms ]` (line 8), then the atom lines, then `[ bonds ]` (line 20). The name line does NOT sit directly above the atoms; the `[ atoms ]` header is between them. Lines 54-55 repeat the false premise ("Every `[ molecules ]` name has a moleculetype (header may be omitted — see above)").
**Recommended fix**: correct lines 47-52 to state that `pdb2gmx` writes the standard `[ moleculetype ]` + `[ atoms ]` headers (the name line sits between `[ moleculetype ]` and `[ atoms ]`), and drop the "must not anchor on those headers" parsing advice (the headers ARE present and can be anchored on). Update lines 54-55 to "Every `[ molecules ]` name has a moleculetype (with `[ moleculetype ]`/`[ atoms ]` headers — see above)."

---

## Fix pass (2026-09-26 — build 2026.3-dev-20260625-1210900-unknown)

**Scope:** 1 open issue (I-93) from the 2026-09-26 eighth-pass audit.
**Result:** 1 fixed, 0 already-fixed (closed), 0 false-positive (closed), 0 left open.

#### I-93 01.2 claims `pdb2gmx` omits the `[ moleculetype ]`/`[ atoms ]` headers — the build writes both — FIXED  ✅ RESOLVED (2026-09-26)
Files: `01-phases/01.2-topology-forcefield.md` (as listed in the issue)
- **Preflight**: Fresh `gmx pdb2gmx -f ala1.pdb -o ala1.gro -water none -ff oplsaa -ignh` (OPLS-AA, single ALA residue) in the transient CPU-only container — exit 0; the generated `topol.top` writes BOTH headers, confirming the issue is still real (stale text present at lines 47-52, 54-55).
- **Applied**: (a) lines 47-52: "**Section headers are omitted** … the name line (`Protein_chain_A 3`) sits directly above the atoms … scripts that parse the topology must not anchor on those headers (match atom lines by content: numeric `$1`, ≥7 fields, numeric charge in column 7)." → "**Section headers are written** (2026.3, verified): `pdb2gmx` writes the standard `[ moleculetype ]` + `[ atoms ]` headers — the name line (`Protein_chain_A 3`) sits between `[ moleculetype ]` and `[ atoms ]`, and the atom lines run from `[ atoms ]` until `[ bonds ]`. Scripts that parse the topology may anchor on those headers."; (b) lines 54-55: "(header may be omitted — see above)" → "(with `[ moleculetype ]`/`[ atoms ]` headers — see above)".
- **Evidence**: Fresh `gmx pdb2gmx` run (2026-09-26, OPLS-AA, single ALA residue, `-ignh`, exit 0); generated `topol.top` verbatim (`grep -n`): `23:[ moleculetype ]`, `25:Protein_chain_A     3`, `27:[ atoms ]`, `44:[ bonds ]`, `150:[ molecules ]`, `152:Protein_chain_A     1`. The name line (25) sits between `[ moleculetype ]` (23) and `[ atoms ]` (27); atom lines run from `[ atoms ]` (27) until `[ bonds ]` (44). All fix-text tokens confirmed present in the build output: `[ moleculetype ]` (1), `[ atoms ]` (1), `[ bonds ]` (1), `[ molecules ]` (1), `Protein_chain_A` (2).

## Notes for the auditor
- **Stale-text sweep**: "Section headers are omitted", "no `[ moleculetype ]` and no `[ atoms ]` headers", "sits directly above the atoms", "must not anchor on those headers", "header may be omitted" = 0 hits in KB content files (excluding issues_kb.md). No stragglers.
- **Regression suite (post-fix, final state):** 30 blocks probed; zero parse signals (unknown/invalid/obsolete = 0 on every block, identical to the pre-fix baseline); matrix verdicts byte-identical to the pre-fix baseline. Prose-only change — no MDP blocks or CLI claims affected.
- No new problems discovered for the next audit.

---

## New issues from simulation validation (2026-09-26 — lysozym_test_2 end-to-end sim)

**Method:** Full 8-phase MD simulation (lysozyme 1LYZ, OPLS-AA/TIP3P, 20 ns production) executed against the live build `gromacs-hip-gfx1100:latest` (2026.3-dev-20260625). All gate scripts (`preflight.sh`, `check_prep.sh`, `check_solvation.sh`, `check_em.sh`, `check_equil.sh`, `check_prod.sh`, `analyze.sh`, `cleanup.sh`) exercised in sequence. The only failure was in `analyze.sh` (phase 7), which was diagnosed, fixed in-session, and re-verified.

**Result:** 1 new issue (I-94), confirmed real and fixed during the sim.

### I-94 `analyze.sh` — `make_ndx` invoked with `< /dev/null` fails silently, leaving no index file  [H]  ✅ RESOLVED (2026-09-26)
Files: `.pi/skills/gromacs-sim/scripts/analyze.sh` (line with `make_ndx` invocation)

**Symptom:** `analyze.sh` exits `FAIL|suite|gromacs suite failed: SUITE_FAIL|trjconv|clean.xtc empty`. The cascade: `make_ndx` produces no `index.ndx` → `trjconv` cannot select groups → `clean.xtc` is never written → all downstream `.xvg` files are missing → the entire phase-7 analysis gate fails.

**Root cause (exact):** The script contains the line

```bash
gmx make_ndx -f "$TPR" -o index.ndx < /dev/null > ndx_list.txt 2>&1 || true
```

`gmx make_ndx` is an **interactive** program: it reads the `.tpr`, prints the group listing, then waits for user input (a group selection or `q` to quit). When stdin is redirected from `/dev/null`, `make_ndx` receives EOF immediately and aborts with the fatal error:

```
Fatal error:
Error reading user input
```

The `|| true` on the same line swallows this error, so the script continues. However, because `make_ndx` aborted before the user could press `q` to save, **`index.ndx` is never written**. The subsequent `trjconv` steps (which require `-n index.ndx`) silently produce empty output, and the gate fails.

**Why it was not caught earlier:** The `|| true` pattern is intentional (the script expects `make_ndx` to sometimes fail and continue). The script author likely assumed `< /dev/null` works the same way it does for `gmx pdb2gmx` (which *does* accept EOF gracefully). But `make_ndx` is fundamentally different — it always waits for interactive input before writing the index file.

**Reproduction (standalone):**
```bash
# Inside gromacs-hip-gfx1100:latest, any working dir:
gmx make_ndx -f md.tpr -o index.ndx < /dev/null   # → "Fatal error: Error reading user input"
ls -l index.ndx                                     # → file does not exist
# Fix:
echo "q" | gmx make_ndx -f md.tpr -o index.ndx     # → saves index.ndx correctly
gmx make_ndx -f md.tpr -o index.ndx                 # → interactive, waits for input
```

**The fix applied in-session:**
```diff
- gmx make_ndx -f "$TPR" -o index.ndx < /dev/null > ndx_list.txt 2>&1 || true
+ echo "q" | gmx make_ndx -f "$TPR" -o index.ndx > ndx_list.txt 2>&1 || true
```
This sends `q` to `make_ndx` so it saves the default index and exits cleanly. The `|| true` remains as a safety net for other unexpected failures.

**Recommended fix (for the skill repo):** Apply the same diff to `analyze.sh`. Additionally, consider adding a post-check: `[ -s index.ndx ] || { echo "SUITE_FAIL|ndx|make_ndx produced no index"; exit 1; }` so that if `make_ndx` fails for any reason, the error is caught early with a clear diagnostic rather than cascading into `clean.xtc empty`.

**Evidence:**
- Live reproduction during lysozym_test_2 sim (2026-09-26): `analyze.sh` failed with `FAIL|suite|gromacs suite failed: SUITE_FAIL|trjconv|clean.xtc empty`. Debugging revealed `index.ndx` was missing from `07_analysis/`. Running `make_ndx -f md.tpr -o index.ndx < /dev/null` in the container reproduced the "Fatal error: Error reading user input" immediately. Sending `echo "q" |` fixed it. Re-running `analyze.sh` after the fix passed all checks.
- `gmx make_ndx -h` synopsis: `gmx make_ndx [-f [<.tpr>]] [-n [<.ndx>]] [-o [<.ndx>]] [-natoms <int>]` — no `-quiet` or `-auto` flag to bypass interactivity (verified: `-quiet` still waits for input).

**Severity rationale [H]:** This is a **workflow-breaking** bug. Every simulation that reaches phase 7 (analysis) will fail at `analyze.sh` with this script as-is, because `make_ndx` will always produce no index file. The `|| true` makes it silent — the agent sees `clean.xtc empty` and must debug to find the root cause. For a fully automated simulation pipeline, this is a hard blocker.

## Fix pass (2026-09-26 — build 2026.3-dev-20260625-1210900-unknown)

**Scope:** 1 open issue (I-94) from the 2026-09-26 simulation-validation audit (lysozym_test_2 end-to-end sim).
**Result:** 0 fixed, 1 already-fixed (closed), 0 false-positive (closed), 0 left open.

#### I-94 `analyze.sh` — `make_ndx` invoked with `< /dev/null` fails silently, leaving no index file — ALREADY-FIXED  ✅ RESOLVED (2026-09-26)
Preflight found the fix already applied in the working tree (uncommitted). No edit made.
- **Locate**: the stale line `gmx make_ndx -f "$TPR" -o index.ndx < /dev/null > ndx_list.txt 2>&1 || true` is GONE from `.pi/skills/gromacs-sim/scripts/analyze.sh`; line 46 now carries the fixed form.
- **Current text (verbatim, analyze.sh:46):**
  `echo "q" | gmx make_ndx -f "$TPR" -o index.ndx > ndx_list.txt 2>&1 || true`
- **git diff (the only uncommitted change to analyze.sh — matches the issue's Recommended fix verbatim):**
  ```diff
  -gmx make_ndx -f "$TPR" -o index.ndx < /dev/null > ndx_list.txt 2>&1 || true
  +echo "q" | gmx make_ndx -f "$TPR" -o index.ndx > ndx_list.txt 2>&1 || true
  ```
- **Fix-text tokens verified against the build** (`gmx make_ndx -h`):
  `gmx make_ndx [-f [<.gro/.g96/...>]] [-n [<.ndx> [...]]] [-o [<.ndx>]] [-natoms <int>] [-[no]twin]`
  → `-f` and `-o` present; no `-quiet`/`-auto` flag (consistent with the issue's interactivity claim).
- **Stale-text sweep**: no `make_ndx … < /dev/null` pattern in any KB content file (excl. `issues_kb.md`). Other `make_ndx` mentions are benign (general usage; `00.2-command-surface.md:15` correctly notes "group building is interactive").
- **Regression gate** (full probe suite, post-state): 30 MDP blocks probed, all `unknown=0 invalid=0 obsolete=0`; matrix verdicts only documented false-positive class (a)/(d) (topology/pull directives + virtual-site `a`). No NEW signals (no KB content edits made this pass).

## Notes for the auditor
- I-94's fix is present in the working tree but **uncommitted** (`git status` → ` M .pi/skills/gromacs-sim/scripts/analyze.sh`). The user should commit it; the fixer never commits (hard rule 11).
- Regression-suite summary: 30 MDP blocks probed (all `unknown=0 invalid=0 obsolete=0`), 23 directives, 101 commands; matrix verdicts = documented false positives only. No new problems discovered.

---

## New issues from ninth-pass audit (2026-09-26 — build 2026.3-dev-20260625-1210900-unknown)

**Method:** Full re-audit of `02-md-types/02.14`–`02.16`, `03-playbooks/03.1`–`03.5` against the live build (grompp probes, CLI help, binary strings).

**Result:** 1 new issue (I-95).

### I-95 03.5 GPU-isolation env-var table lists two vars absent from the build  [M]  ✅ RESOLVED (2026-09-26)
Files: `03-playbooks/03.5-performance.md` (GPU selection / isolation table)

The KB table documents five "core GROMACS" GPU env vars and states they "work in this HIP build": `GMX_GPU_ID`, `GMX_GPU_DD_COMMS`, `GMX_GPU_PME_PP_COMMS`, `GMX_GPU_PME_DECOMPOSITION`, `GMX_DISABLE_DIRECT_GPU_COMM`. Binary inspection (`strings` over `bin/gmx` + `lib/*.so`) confirms only three exist in `2026.3-dev-20260625`: `GMX_GPU_ID` ✓, `GMX_GPU_PME_DECOMPOSITION` ✓, `GMX_DISABLE_DIRECT_GPU_COMM` ✓. **`GMX_GPU_DD_COMMS` and `GMX_GPU_PME_PP_COMMS` are absent** (no substring match anywhere in the binary; the full `GMX_GPU*` set in the build is: `GMX_GPUTASKS`, `GMX_GPU_DISABLE_BUFFER_OPS`, `GMX_GPU_ID`, `GMX_GPU_NB_ANA_EWALD`, `GMX_GPU_NB_EWALD_TWINCUT`, `GMX_GPU_NB_TAB_EWALD`, `GMX_GPU_PME_DECOMPOSITION`).
**Recommended fix**: remove the `GMX_GPU_DD_COMMS` and `GMX_GPU_PME_PP_COMMS` rows from the table (or mark them "not present in this build"), keeping the three verified vars.

## Fix pass (2026-09-26 — build 2026.3-dev-20260625-1210900-unknown)

**Scope:** 1 open issue (I-95) from the ninth-pass audit (2026-09-26).
**Result:** 1 fixed, 0 already-fixed (closed), 0 false-positive (closed), 0 left open.

#### I-95 03.5 GPU-isolation env-var table lists two vars absent from the build — FIXED  ✅ RESOLVED (2026-09-26)
Files: `03-playbooks/03.5-performance.md` (GPU selection / isolation table)
- **Preflight**: re-ran the issue's probe — `strings` over `bin/gmx` + `lib/*.so` in the transient container (`gromacs-hip-gfx1100:latest`). Issue confirmed still real: `GMX_GPU_DD_COMMS` and `GMX_GPU_PME_PP_COMMS` have no substring match anywhere in the binary; `GMX_GPU_ID`, `GMX_GPU_PME_DECOMPOSITION`, `GMX_DISABLE_DIRECT_GPU_COMM` are present. Cross-checked against the suite snapshot `snapshot/04_envvars.txt` (identical result).
- **Applied**: removed the two absent rows from the table, keeping the three verified vars:
  - removed: `| `GMX_GPU_DD_COMMS` | Direct GPU↔GPU halo exchange between PP ranks (multi-rank, single node). |`
  - removed: `| `GMX_GPU_PME_PP_COMMS` | Direct PME↔PP GPU communication. |`
  - table now carries exactly: `GMX_GPU_ID`, `GMX_GPU_PME_DECOMPOSITION`, `GMX_DISABLE_DIRECT_GPU_COMM`.
- **Evidence** (verbatim, post-fix `strings` over `bin/gmx` + `lib/*.so`, `grep -oE 'GMX_[A-Z0-9_]*' | sort -u`):
  ```
  GMX_DISABLE_DIRECT_GPU_COMM
  GMX_GPUTASKS
  GMX_GPU_DISABLE_BUFFER_OPS
  GMX_GPU_ID
  GMX_GPU_NB_ANA_EWALD
  GMX_GPU_NB_CLUSTER_SIZE
  GMX_GPU_NB_EWALD_TWINCUT
  GMX_GPU_NB_TAB_EWALD
  GMX_GPU_PME_DECOMPOSITION
  ```
  → all three retained vars present; `GMX_GPU_DD_COMMS` / `GMX_GPU_PME_PP_COMMS` absent (no line). Confirmed by `snapshot/04_envvars.txt` (same nine `GMX_GPU*`/`GMX_DISABLE_DIRECT_GPU_COMM` entries, no `GMX_GPU_DD_COMMS`/`GMX_GPU_PME_PP_COMMS`).
- **Stale-text sweep**: no `GMX_GPU_DD_COMMS` / `GMX_GPU_PME_PP_COMMS` in any KB content file (excl. `issues_kb.md`) except the Pymacs provenance note (`03.5-performance.md:185`) — a source-attribution span (what was adapted from Pymacs), not a build claim; left untouched per hard rule 1 (Notes sections) and flagged below for the auditor.
- **Regression gate** (full probe suite, post-fix): 30 MDP blocks probed, all `unknown=0 invalid=0 obsolete=0`; matrix verdicts identical to the pre-fix baseline (documented false-positive class (a) only). No NEW signals.

## Notes for the auditor
- **Stale provenance claim (not fixed — Notes section, out of fixer scope):** `03-playbooks/03.5-performance.md:185` (Pymacs provenance note) lists `GMX_FORCE_GPU_ID`, `GMX_GPU_DD_COMMS`, `GMX_GPU_PME_DECOMPOSITION` as GPU-isolation env vars "re-verified against the local 2026.3 HIP build." Only `GMX_GPU_PME_DECOMPOSITION` of those three is in the build; `GMX_FORCE_GPU_ID` and `GMX_GPU_DD_COMMS` are absent (no substring match in `bin/gmx` + `lib/*.so`). Candidate for the next audit.
- **Regression-suite summary:** 30 MDP blocks probed (all `unknown=0 invalid=0 obsolete=0`), 23 directives, 101 commands; matrix verdicts = documented false positives only; identical to the pre-fix baseline. No new problems beyond the provenance note above.

---

## New issues from full-KB audit (2026-09-30 — tenth pass)

**Method:** Full re-audit of `01-phases/01.8-analysis.md` (the analysis-tools file) against the live build `gromacs-hip-gfx1100:latest` (`2026.3-dev-20260625-1210900-unknown`). Every tool-CLI claim in the file re-checked flag-by-flag against `gmx <tool> -h` in the transient CPU-only container (no GPU, no MD run). The time-series `gmx analyze` flags and the PCA/covariance workflow (`gmx covar` / `gmx anaeig`) were probed flag-by-flag, and the two suspect flags were reproduced as live `Unknown command-line option` aborts.
**Result:** 2 new issues (I-96, I-97), both confirmed real against the build.

### I-96 01.8 `gmx analyze` row lists `-err` and `-bc` flags that do not exist in the build  [M]  ✅ RESOLVED (2026-09-30)
Files: `01-phases/01.8-analysis.md` (line 53, "Time-series mean / error" row)

The row says: "average + (block) error estimate over one or more `.xvg` columns; `-av` average, `-err` error, `-bc` block size." The build's `gmx analyze` has **no `-err` and no `-bc` flag**. Flag-by-flag probe of `gmx analyze -h`: `-av` ✓, `-ee` ✓, `-errbar` ✓, `-bw` ✓, **`-err` ✗, `-bc` ✗**. Live repro: `gmx analyze -f t.xvg -err` → `Invalid command-line options / Unknown command-line option -err` (exit 1). The real flags are:
- `-av` — average (the KB's `-av` is correct)
- `-ee` — error estimates using **block averaging** (this is the "(block) error estimate"; output `errest.xvg`)
- `-bw` — **block width** (default `0.1`; this is the "block size")
- `-errbar` — enum (`none`/`sd`/`err`/`90`) to add error bars to the plot

So the KB's `-err` → `-ee` (or `-errbar`) and `-bc` → `-bw`.
**Recommended fix**: line 53, change "`-av` average, `-err` error, `-bc` block size" → "`-av` average, `-ee` block-averaging error estimate, `-bw` block width (default 0.1); `-errbar <sd|err|90>` adds error bars".
**Fix deviation (2026-09-30, fix pass):** the Recommended fix text carried two wrong tokens, both corrected against the build before applying. (1) `-bw` is **not** "block width" — `gmx analyze -h` says "Binwidth for the distribution" (the histogram bin width for `-dist`); no block-size flag exists in `gmx analyze`, so the applied text reads "`-bw` bin width for the distribution (default 0.1)". (2) The `-errbar` enum is **not** `<sd|err|90>` — the build's enum is `none`/`stddev`/`error`/`90` (help line "Error bars for -av: none, stddev, error, 90"; GROMACS source `gmx_analyze.cpp`: `static const char* avbar_opt[] = { nullptr, "none", "stddev", "error", "90", nullptr }`), so the applied text reads "`-errbar <stddev|error|90>` adds error bars".

### I-97 01.8 PCA workflow uses `anaeig -in covar.xcm` — `-in` does not exist; the eigendecomposition is `covar -v`  [H]  ✅ RESOLVED (2026-09-30)
Files: `01-phases/01.8-analysis.md` (lines 87-97, "Conformational ensemble (PCA / FES)" block + flag list)

The KB's PCA recipe is:
```
# 1. covariance matrix of a selection (default: backbone; -fit on by default)
gmx covar -s md.tpr -f clean.xtc -n index.ndx -o covar.xcm
# 2. eigendecomposition -> eigenvectors
gmx anaeig -in covar.xcm -v eigenvectors.trr
# 3. project the trajectory onto PC1/PC2 (or -2d 2dproj.xvg for a 2-D dump)
gmx anaeig -in covar.xcm -v eigenvectors.trr -s md.tpr -f clean.xtc \
    -proj proj.xvg
```
and the flag list says "`gmx anaeig` flags: `-in` (matrix), `-v` (eigenvectors), `-eig` (eigenvalues), `-proj` ...". Two defects, both confirmed against the build:
1. **`gmx anaeig` has no `-in` flag.** Flag-by-flag probe of `gmx anaeig -h`: **`-in` ✗** (the only `-in*` flag is `-inpr`, the inner-products matrix). Live repro: `gmx anaeig -in fake.xcm -v fake.trr` → `Invalid command-line options / Unknown command-line option -in` (exit 1). `anaeig` reads the eigenvectors via **`-v`** (the eigenvector trajectory file), not `-in`.
2. **The eigendecomposition is done by `gmx covar -v`, not by `anaeig`.** `covar -v` writes the eigenvectors to a trajectory file ("The eigenvectors are written to a trajectory file (-v) … The eigenvectors can be analyzed with gmx anaeig."). The KB's step 1 (`covar … -o covar.xcm`) never passes `-v`, so no eigenvector file is ever produced for step 2 to read — the recipe is broken at both steps.

The correct workflow (verified against the build):
```
# 1. covariance matrix + eigendecomposition (covar -v writes the eigenvectors)
gmx covar -s md.tpr -f clean.xtc -n index.ndx -o covar.xcm -v eigenvectors.trr
# 2. analyze / project the eigenvectors (anaeig reads them via -v, not -in)
gmx anaeig -v eigenvectors.trr -s md.tpr -f clean.xtc -proj proj.xvg
```
**Recommended fix**: (a) add `-v eigenvectors.trr` to the `covar` line (step 1 does the eigendecomposition); (b) in steps 2-3, drop `-in covar.xcm` and keep `-v eigenvectors.trr` (the eigenvector input file); (c) in the flag list, remove "`-in` (matrix)" and note that `-v` is the eigenvector input file (from `covar -v`).

## Verified OK (this pass)
- 01.8 remaining tool CLIs re-checked flag-by-flag and confirmed: `gmx dssp -o`/`-num`, `gmx hbond -o`/`-num`/`-r`/`-t`, `gmx mindist -o`/`-od`/`-on`, `gmx covar -o`/`-v`/`-av`/`-xpm`, `gmx anaeig -v`/`-eig`/`-proj`/`-2d`/`-nframes`, `gmx msd -s`/`-f`/`-o`/`-trestart`, `gmx trjconv -s`/`-f`/`-pbc`/`-dt`/`-o` — all present in the build.
- 01.8 `analyze` `-av` flag (correct) and the `wham`/`g_wham`-gone framing (line 122) — consistent with prior passes.

## Notes
- **Method note (false-positive guard):** an earlier flag-probe loop in this session used a shell-escaping bug (`\$f` passed `$f` literally to the inner `bash -c`, where it expanded to empty, reducing the grep pattern to `^\s*\s` = "match any whitespace line"), which reported every flag as present. All flag verdicts above were re-run with a corrected pattern (`grep -cE '^\s*-<flag>(\s|[\[])'`) and the two suspect flags were confirmed by live `Unknown command-line option` aborts. No issue was filed on the strength of the buggy loop.
- **Probe artifacts:** ad-hoc live probes in the transient container (`gmx analyze -h`, `gmx anaeig -h`, `gmx covar -h`; live `anaeig -in` / `analyze -err` abort repros). No MDP blocks affected — both issues are tool-CLI claims in 01.8 prose, not fenced MDP blocks.
- **Severity:** I-96 [M] (wrong flag names in a table row; the base command `gmx analyze -f x.xvg -o avg.xvg` is valid). I-97 [H] (the PCA recipe is workflow-breaking: `covar` without `-v` produces no eigenvector file, and `anaeig -in` is an unknown option that aborts).

## Fix pass (2026-09-30 — build 2026.3-dev-20260625-1210900-unknown)

**Scope:** 2 open issues (I-96…I-97) from the 2026-09-30 tenth-pass audit.
**Result:** 2 fixed, 0 already-fixed (closed), 0 false-positive (closed), 0 left open.

#### I-96 01.8 `gmx analyze` row lists `-err` and `-bc` flags that do not exist in the build — FIXED  ✅ RESOLVED (2026-09-30)
Files: `01-phases/01.8-analysis.md` (line 53, "Time-series mean / error" row)
- **Preflight**: re-ran `gmx analyze -h` (snapshot `02_help/analyze.txt` + live transient container). `-av`/`-ee`/`-bw`/`-errbar` present; `-err`/`-bc` absent. Issue confirmed still real.
- **Applied**: line 53, "`-av` average, `-err` error, `-bc` block size" → "`-av` average, `-ee` block-averaging error estimate, `-bw` bin width for the distribution (default 0.1); `-errbar <stddev|error|90>` adds error bars".
- **Evidence**: `gmx analyze -h` (verbatim):
  ```
   -av     [<.xvg>]           (average.xvg)    (Opt.)
   -ee     [<.xvg>]           (errest.xvg)     (Opt.)
   -bw     <real>             (0.1)
           Binwidth for the distribution
   -errbar <enum>             (none)
           Error bars for -av: none, stddev, error, 90
  ```
  and description line: "Option -ee produces error estimates using block averaging."
- **Deviation**: the Recommended fix text had two wrong tokens, both corrected against the build (see the dated Fix-deviation note in the I-96 entry): `-bw` is "Binwidth for the distribution" (not "block width"), and the `-errbar` enum is `none`/`stddev`/`error`/`90` (not `sd`/`err`/`90`).

#### I-97 01.8 PCA workflow uses `anaeig -in covar.xcm` — `-in` does not exist; the eigendecomposition is `covar -v` — FIXED  ✅ RESOLVED (2026-09-30)
Files: `01-phases/01.8-analysis.md` (lines 87-97, "Conformational ensemble (PCA / FES)" block + flag list)
- **Preflight**: re-ran `gmx anaeig -h` + `gmx covar -h` (snapshot `02_help/` + live). `anaeig` has no `-in` (the only `-in*` flag is `-inpr`); `covar -v` writes the eigenvector trajectory. Issue confirmed still real.
- **Applied**: (a) code block — the `covar` line gains `-v eigenvectors.trr` (step 1 now does the eigendecomposition); the separate `anaeig -in … -v …` eigendecomposition step is dropped; the projection step becomes `gmx anaeig -v eigenvectors.trr -s md.tpr -f clean.xtc -proj proj.xvg`. (b) flag list — removed "`-in` (matrix)"; `-v` is now described as "eigenvector input file, from `covar -v`".
- **Evidence**: `gmx anaeig -h` (verbatim; no `-in` option present):
  ```
   -v      [<.trr/.cpt/...>]  (eigenvec.trr)
           Full precision trajectory: trr cpt tng h5md
   -eig    [<.xvg>]           (eigenval.xvg)   (Opt.)
   -proj   [<.xvg>]           (proj.xvg)       (Opt.)
   -2d     [<.xvg>]           (2dproj.xvg)     (Opt.)
   -nframes <int>             (2)
  ```
  `gmx covar -h` (verbatim):
  ```
   -v      [<.trr/.cpt/...>]  (eigenvec.trr)
           Full precision trajectory: trr cpt tng h5md
  ```
  with description: "The eigenvectors are written to a trajectory file (-v). … The eigenvectors can be analyzed with gmx anaeig."

## Notes for the auditor
- **New problem (not fixed — out of scope for I-97):** the `gmx covar` flag list in 01.8-analysis.md describes `-o` as "(matrix)", but in this build `-o` is the **eigenvalues** output (default `eigenval.xvg`); the covariance matrix itself is written by `-ascii` (ASCII) or `-xpm` (image). The I-97 fix retains `-o covar.xcm` in the recipe per the issue's verified workflow, so the recipe now writes eigenvalues to a misleadingly-named `.xcm` file. Candidate for the next audit.
- **Minor:** `gmx anaeig -nframes` is described in the KB as "number of leading PCs to use, default 2"; the build help says "Number of frames for the extremes output" (default 2). The default matches; the wording differs. Left untouched (out of scope for I-97).
- **Regression suite:** 30 MDP blocks probed, all `unknown=0 invalid=0 obsolete=0`; matrix verdicts identical to the pre-fix baseline (documented false-positive class (a) lines only); no new parse signals. Stale-text sweep for the I-96/I-97 old text: no hits outside `issues_kb.md`.

---

## New issues from 01-phases / 02-md-types / 03-playbooks audit (2026-09-30)

**Method:** All 26 KB files in `01-phases/`, `02-md-types/`, `03-playbooks/` re-read. Every tool CLI re-checked against the snapshot help files (`02_help/*.txt`) and live `gmx <tool> -h` in `gromacs-hip-gfx1100:latest`. MDP blocks probed through `gmx grompp` (EM/NVT/NPT/FEP/umbrella/AWH/membrane/Langevin/anneal/MTS/SA/RE/CG/Verlet/vacuo). Semantic claims cross-checked against the `master` source tag (`convparm.cpp` for distance-restraint column order). CPU-only grompp / tool probes only — no MD run (eGPU in use).
**Result:** 4 new issues (I-98…I-101), all confirmed real against the build.

### I-98 01.8 `gmx covar` flag list describes `-o` as "(matrix)" — it is the eigenvalues output  [M]  ✅ RESOLVED (2026-09-30)
Files: `01-phases/01.8-analysis.md` (line 92, "gmx covar flags")
The KB lists `-o` as "(matrix)", but in this build `-o` is the **eigenvalues** output (default `eigenval.xvg`); the covariance matrix is written by `-ascii` (ASCII, `covar.dat`) or `-xpm` (image, `covar.xpm`). The I-97 fix retained `-o covar.xcm` in the PCA recipe, so the recipe now writes eigenvalues to a misleadingly-named `.xcm` file.
- **Evidence**: `gmx covar -h` (verbatim):
  ```
   -o      [<.xvg>]           (eigenval.xvg)
           xvgr/xmgr file
   -v      [<.trr/.cpt/...>]  (eigenvec.trr)
           Full precision trajectory: trr cpt tng h5md
   -ascii  [<.dat>]           (covar.dat)      (Opt.)
           Generic data file
   -xpm    [<.xpm>]           (covar.xpm)      (Opt.)
           X PixMap compatible matrix file
  ```
  The default filename `eigenval.xvg` confirms `-o` carries the eigenvalues; the matrix is `-ascii`/`-xpm`.
**Recommended fix**: line 92, "`-o` (matrix)" → "`-o` (eigenvalues, `.xvg`); the matrix is written by `-ascii` (ASCII) or `-xpm` (image)". Also rename the recipe's `-o covar.xcm` to `-o eigenval.xvg` (or drop it) so eigenvalues are not written to a misleadingly-named `.xcm` file.

### I-99 01.8 `gmx anaeig -nframes` described as "number of leading PCs to use" — it is the extremes-output frame count  [L]  ✅ RESOLVED (2026-09-30)
Files: `01-phases/01.8-analysis.md` (line 96, "gmx anaeig flags")
The KB describes `-nframes` as "number of leading PCs to use, default 2". The build help says "Number of frames for the extremes output" (default 2). The default matches; the wording is wrong (it is not the number of leading PCs).
- **Evidence**: `gmx anaeig -h` (verbatim):
  ```
   -nframes <int>             (2)
           Number of frames for the extremes output
  ```
**Recommended fix**: line 96, "`-nframes` (number of leading PCs to use, default 2)" → "`-nframes` (number of frames for the extremes output, default 2)".

### I-100 01.9 §C + 03.4 quote the wrong GPU-update startup error string  [M]  ✅ RESOLVED (2026-09-30)
Files: `01-phases/01.9-troubleshooting.md` (line 67, §C table), `03-playbooks/03.4-failure-diagnosis.md` (line 18, triage table)
The KB quotes the startup error as `Inconsistency in user input: Update task on the GPU was required, but the following condition(s) were not satisfied: ...`. The build's actual message is `Update task can not run on the GPU, because the following condition(s) were not satisfied:` (no "Inconsistency in user input" prefix, and "can not run on the GPU, because" not "was required, but").
- **Evidence**: `strings libgromacs.so` (verbatim):
  ```
  Update task can not run on the GPU, because the following condition(s) were not satisfied:
  ```
**Recommended fix**:
- 01.9 line 67: replace `Inconsistency in user input: Update task on the GPU was required, but the following condition(s) were not satisfied: ...` with `Update task can not run on the GPU, because the following condition(s) were not satisfied: ...`.
- 03.4 line 18: replace `Update task on the GPU was required ... not satisfied` with `Update task can not run on the GPU ... not satisfied`.

### I-101 02.03 `[ distance_restraints ]` column order is swapped (label before type)  [H]  ✅ RESOLVED (2026-09-30)
Files: `02-md-types/02.03-alchemical-free-energy.md` (line 180, "2026.3 section formats")
The KB claims the NMR-style `[ distance_restraints ]` column order is `ai aj funct type label low up1 up2 weight` (type before label). The build reads **label before type**: `ai aj funct label type low up1 up2 weight`. Following the KB order with a non-zero label puts the label in the `type` slot (fatal if 0, silently mis-assigned if non-zero).
- **Evidence**: Probe `kb-audit/pdr.mdp` with `disre = simple`:
  - Order A (`ai aj funct type label …` = `1 3 1 1 0 0.2 0.3 0.3 1.0`, type=1 col4, label=0 col5): **FATAL** `Value of 'type' in Dis. Rest. is 0, which is smaller than the minimum of 1` (the build read col5=0 as `type`).
  - Order B (`ai aj funct label type …` = `1 3 1 0 1 0.2 0.3 0.3 1.0`, label=0 col4, type=1 col5): **PASS** (TPR generated, exit 0).
  - Source (`src/gromacs/gmxpreprocess/convparm.cpp`, `assign_param` for `DistanceRestraints`): `newparam->disres.label = round_check(old[0], …)` then `newparam->disres.type = round_check(old[1], …)` — confirming `old[0]`=label (col4), `old[1]`=type (col5).
**Recommended fix**: line 180, "(`ai aj funct type label low up1 up2 weight`, needs `disre = simple`)" → "(`ai aj funct label type low up1 up2 weight`, needs `disre = simple`)".

## Verified OK (01-phases / 02-md-types / 03-playbooks)
- **01.1–01.3**: pdb2gmx flags (no `-cys`), `make_ndx`, `solvate`, `genion`, `editconf -bt`, box rules, water/ion matching.
- **01.4**: EM integrators (`steep`/`cg`/`l-bfgs`), `emtol`, `emstep`, GPU-EM constraints, "machine precision" + "not finite" mdrun strings (both in binary).
- **01.5**: NVT/NPT coupling, `refcoord-scaling = com`, `pcoupl = MTTK` (2-value compressibility), v-rescale, C-rescale.
- **01.6**: production NPT, `nstcomm`, output frequencies, `-cpt` checkpointing.
- **01.7**: restart (`-cpi`), parallelization (`-ntmpi`/`-ntomp`), `no domain decomposition for n ranks` error, GPU offload flags.
- **01.8**: analysis tools (`rms`, `rmsf`, `gyrate`, `msd`, `rdf`, `sasa`, `density`, `bar`, `wham`, `analyze`, `covar`, `anaeig`, `make_ndx`, `trjconv`, `trjcat`, `dipoles`, `spatial`) — all flags verified (except I-98/I-99).
- **01.9**: troubleshooting strings, `GMX_LOG_BUFFER`, `1-4 (i,j) interaction not within cut-off!`, `-maxwarn` downgrades (except I-100).
- **02.01–02.16**: all MD types. Key verifications: `cutoff-scheme = Group` → fatal "removed since 2020" (02.14 defensible, 02.16 correct); `pbc = no`/`rcoulomb=rvdw=0`/`pbc=xy`-no-walls all fail as documented; MTS block (`mts`/`mts-levels`/`mts-level2-forces`/`mts-level2-factor`); SA (`annealing`/`annealing-npoints`/`annealing-time`/`annealing-temp`); RE (`repex`/`init-lambda-state`); Langevin (`sd`/`bd`, `tau-t` friction, `tc-grps` all-atoms); AWH (`awh`/`awh1-dim1-coord-provider`/`awh-nstout` multiple of `nstenergy`); pull code (2026.3 API: `pull-coord1-type`/`-geometry`/`-groups`/`-init`/`-rate`/`-k`); virtual sites (`[ virtual_sites_3 ]`); `gmx principal` flags (no `-o`).
- **03.1–03.5**: decision trees, MDP templates (all 11 blocks `unknown=0 invalid=0 obsolete=0`; 4 `exit=1` blocks are system noise from the 1-atom probe topology), checklists, failure triage, performance (GPU env vars `GMX_GPU_ID`/`GMX_GPU_PME_DECOMPOSITION`/`GMX_DISABLE_DIRECT_GPU_COMM` all in binary; `PP task will update and constrain coordinates on the %s` log string in binary; `nonbonded-benchmark` flags).

## Notes
- **I-98/I-99 were already flagged** in the I-97 "Notes for the auditor" (2026-09-30) as candidates for the next audit; this pass confirms and files them.
- **I-101 is the only [H]**: the column-order swap silently mis-assigns `label`/`type` for any NMR-style distance restraint written in the KB's order.
- **02.14 vs 02.16 `cutoff-scheme`**: 02.14 says "only value is Verlet" and 02.16 says "Group is a recognized enum but fatal at runtime". Both are defensible — `Group` parses (recognized enum) but is fatal ("removed since 2020"). No issue.
- **03.2 fep/umb/awh/mem blocks** `exit=1` are system noise (probe topology lacks LIG/Ligand; delta block lacks ensemble temp), not KB issues.

## Fix pass (2026-09-30 — build 2026.3-dev-20260625-1210900-unknown)

**Scope:** 4 open issues (I-98…I-101) from the 2026-09-30 audit (01-phases / 02-md-types / 03-playbooks).
**Result:** 4 fixed, 0 already-fixed (closed), 0 false-positive (closed), 0 left open.

#### I-98 01.8 `gmx covar` flag list describes `-o` as "(matrix)" — it is the eigenvalues output — FIXED  ✅ RESOLVED (2026-09-30)
Files: `01-phases/01.8-analysis.md` (as listed in the issue)
- **Preflight**: `gmx covar -h` re-run in `gromacs-hip-gfx1100:latest`; issue confirmed still real (`-o` default is `eigenval.xvg`, the matrix is `-ascii`/`-xpm`).
- **Applied**: flag list `-o` (matrix) → `-o` (eigenvalues, `.xvg`; the matrix is written by `-ascii` (ASCII) or `-xpm` (image)); PCA recipe `-o covar.xcm` → `-o eigenval.xvg` (eigenvalues no longer written to a misleadingly-named `.xcm`).
- **Evidence**: `gmx covar -h` (verbatim, post-fix build):
  ```
   -o      [<.xvg>]           (eigenval.xvg)
           xvgr/xmgr file
   -ascii  [<.dat>]           (covar.dat)      (Opt.)
           Generic data file
   -xpm    [<.xpm>]           (covar.xpm)      (Opt.)
           X PixMap compatible matrix file
  ```
  The default filename `eigenval.xvg` confirms `-o` carries the eigenvalues; the matrix is `-ascii`/`-xpm`. New text tokens (`-o`, `.xvg`, `-ascii`, `-xpm`) all present in the help.

#### I-99 01.8 `gmx anaeig -nframes` described as "number of leading PCs to use" — it is the extremes-output frame count — FIXED  ✅ RESOLVED (2026-09-30)
Files: `01-phases/01.8-analysis.md` (as listed in the issue)
- **Preflight**: `gmx anaeig -h` re-run; issue confirmed still real (help says "Number of frames for the extremes output", default 2).
- **Applied**: `-nframes` (number of leading PCs to use, default 2) → `-nframes` (number of frames for the extremes output, default 2).
- **Evidence**: `gmx anaeig -h` (verbatim, post-fix build):
  ```
   -nframes <int>             (2)
           Number of frames for the extremes output
  ```
  New text tokens (`-nframes`, default 2, "extremes output") all match the help.

#### I-100 01.9 §C + 03.4 quote the wrong GPU-update startup error string — FIXED  ✅ RESOLVED (2026-09-30)
Files: `01-phases/01.9-troubleshooting.md`, `03-playbooks/03.4-failure-diagnosis.md` (as listed in the issue)
- **Preflight**: `strings /usr/local/gromacs/lib/libgromacs.so` re-run; the build's message is present verbatim and the KB's quoted string is absent (`grep -c "Update task on the GPU was required"` = 0, `grep -c "Inconsistency in user input: Update task"` = 0). Issue confirmed still real.
- **Applied**: 01.9 §C table `Inconsistency in user input: Update task on the GPU was required, but the following condition(s) were not satisfied: ...` → `Update task can not run on the GPU, because the following condition(s) were not satisfied: ...`; 03.4 triage table `Update task on the GPU was required ... not satisfied` → `Update task can not run on the GPU ... not satisfied`.
- **Evidence**: `strings /usr/local/gromacs/lib/libgromacs.so` (verbatim, post-fix build):
  ```
  Update task can not run on the GPU, because the following condition(s) were not satisfied:
  ```
  The new quoted string matches the binary byte-for-byte; the old string is absent.

#### I-101 02.03 `[ distance_restraints ]` column order is swapped (label before type) — FIXED  ✅ RESOLVED (2026-09-30)
Files: `02-md-types/02.03-alchemical-free-energy.md` (as listed in the issue)
- **Preflight**: grompp probe re-run (probe.top ALA+water, `pdr.mdp` with `disre = simple`, restraint atoms 1–3). Order A (`ai aj funct type label …` = `1 3 1 1 0 0.2 0.3 0.3 1.0`): **FATAL** exit 1. Order B (`ai aj funct label type …` = `1 3 1 0 1 0.2 0.3 0.3 1.0`): **PASS** exit 0, TPR generated. Issue confirmed still real (build reads label before type).
- **Applied**: line 180 `(`ai aj funct type label low up1 up2 weight`, needs `disre = simple`)` → `(`ai aj funct label type low up1 up2 weight`, needs `disre = simple`)`.
- **Evidence**: grompp (verbatim, post-fix build), `disre = simple`, restraint `1 3 …`:
  ```
  Order A (type before label):  exit=1
    Value of 'type' in Dis. Rest. is 0, which is smaller than the minimum of 1
  Order B (label before type):  exit=0  (order_b.tpr generated, 61788 bytes)
  ```
  The build reads col4 as `label` and col5 as `type`; the corrected order (label before type) parses clean. New text tokens (`label`, `type`, `disre = simple`) all confirmed by the probe.

## Notes for the auditor
- **Regression suite (post-fix)**: 30 blocks probed, all `unknown=0 invalid=0 obsolete=0`; `03_matrix_verdicts.txt` byte-identical to the pre-fix baseline (only the documented false-positive-class (a) lines persist). Block verdicts identical to baseline modulo the 01.8 source-line-ref shift (133→135, from the +2-line I-98/I-99 edit) and per-run GROMACS reminder-quote log line shifts — no NEW parse signal, no reverts.
- **CLI claims re-checked**: `02_help/covar.txt` (`-o`/`-ascii`/`-xpm`) and `02_help/anaeig.txt` (`-nframes`) match the fixed 01.8 text.
- **Stale-text sweep**: KB content (00–03 + README) is clean of all four old strings. The only remaining `ai aj funct type label` hits are in `tickets_lemkul_import.md` (lines 231, 863) — an import-tracking/provenance document (not KB content per the Paths table), and both are dated 2026-09-15 historical findings. Left untouched (documented false hit, class (b)); flagging here in case the next audit wants to reconcile the tracking file.
- **No deviations, no handbacks.** All four Recommended fixes applied verbatim (I-98 recipe rename used the recommended `-o eigenval.xvg` variant).

## New issues from full-KB regression audit (2026-07-21)

**Method:** All 34 KB content files re-read in full (00-foundations ×5, 01-phases ×10, 02-md-types ×16, 03-playbooks ×5, README). No build drift since 2026-09-30 (image sha256:4d59c576… unchanged; `gmx --version` identical: 2026.3-dev, 101 commands, HIP gfx1100, TNG/Colvars/CP2K/Torch/Plumed, SIMD AVX2_256, VkFFT). No KB content drift (all 34 files + issues_kb.md mtimes 2026-07-16/17, predating the 2026-09-30 pass). Regression re-verification of every tool/flag/option claim against the live build: command inventory (101), removed-tool absence (benchmark/g_wham/trjpos/nmat/pmat/rotinv/axias/solvation/dipole/charge/ion2group/pmx/fit/sander/do_*), MDP option presence (emstep, gen-vel/temp/seed, nstcomm, vdw-modifier, rvdw-switch, verlet-buffer-tolerance, mts/mts-levels/mts-level2-forces/mts-level2-factor, sc-function/sc-r-power/sc-coul/sc-power/sc-sigma, dhdl-derivatives, awh-*, pull-coordN-*, annealing/annealing-npoints/annealing-time/annealing-temp, pcoupl=C-rescale, refcoord-scaling=com, pbc=xyz, comm-mode=angular), CLI flags (check -s1/-s2, make_ndx -[no]twin/-natoms, wham/awh/covar/msd/spatial/dipoles/anaeig/nonbonded-benchmark), GPU env vars (strings sweep of libgromacs.so + bin/gmx). CPU-only grompp/tool probes — no MD run.
**Result:** 1 new issue (I-102), confirmed real against the build. A stale provenance note (flagged in the I-95 fix pass as "candidate for the next audit") claims two absent GPU env vars were "re-verified against the local 2026.3 HIP build."

### I-102 03.5 provenance note lists two absent GPU env vars as "re-verified"  [L]  ✅ RESOLVED (2026-09-30)
Files: `03-playbooks/03.5-performance.md`
The Pymacs provenance note (lines 183–189) claims the GPU-isolation env vars it adapted were "re-verified against the local 2026.3 HIP build":

> **Provenance (Pymacs)**: … the GPU isolation env vars (`GMX_FORCE_GPU_ID`, `GMX_GPU_DD_COMMS`, `GMX_GPU_PME_DECOMPOSITION`), and the "avoid PME-on-GPU for EM" note are adapted from the Pymacs automation suite … **re-verified against the local 2026.3 HIP build.**

Only one of the three is present in the build. A `strings` sweep of `libgromacs.so*` + `bin/gmx` shows the full `GMX_GPU*`/`GMX_DISABLE_DIRECT_GPU_COMM` set is: `GMX_DISABLE_DIRECT_GPU_COMM`, `GMX_GPUTASKS`, `GMX_GPU_DISABLE_BUFFER_OPS`, `GMX_GPU_ID`, `GMX_GPU_NB_ANA_EWALD`, `GMX_GPU_NB_CLUSTER_SIZE`, `GMX_GPU_NB_EWALD_TWINCUT`, `GMX_GPU_NB_TAB_EWALD`, `GMX_GPU_PME_DECOMPOSITION`. Neither `GMX_FORCE_GPU_ID` nor `GMX_GPU_DD_COMMS` appears (no substring match). So the "re-verified" claim is false for 2 of the 3 vars. The main content (the GPU-isolation env-var table at lines 153–157) is already correct (I-95 fixed it to list only `GMX_GPU_ID` / `GMX_GPU_PME_DECOMPOSITION` / `GMX_DISABLE_DIRECT_GPU_COMM`); only the provenance note is stale.
**Recommended fix**: In `knowledge/03-playbooks/03.5-performance.md` line 185, replace the parenthetical `(`GMX_FORCE_GPU_ID`, `GMX_GPU_DD_COMMS`, `GMX_GPU_PME_DECOMPOSITION`)` with `(`GMX_GPU_ID`, `GMX_GPU_PME_DECOMPOSITION`, `GMX_DISABLE_DIRECT_GPU_COMM`)` to match the vars the note actually re-verified (and the main table above). The rest of the provenance sentence is correct as-is.

## Verified OK (2026-07-21 regression pass)
- **Build**: unchanged since 2026-09-30 (image sha256:4d59c576…, `gmx --version` identical, 101 commands).
- **Command inventory**: 101 commands; all removed tools absent (benchmark, g_wham, trjpos, nmat, pmat, rotinv, axias, solvation, dipole, charge, ion2group, pmx, fit, sander, do_rms, do_wham, analysis); all present tools present (nonbonded-benchmark, wham, convert-trj, dipoles, spatial, msd, covar, anaeig, awh).
- **00-foundations**: 00.1 (versions/install), 00.2 (command surface), 00.3 (env-vars), 00.4 (files), 00.5 (options) — all clean.
- **01-phases**: 01.1–01.10 — all clean (I-85/I-90/I-92/I-99/I-100/I-101 fixes in place).
- **02-md-types**: 02.01–02.16 — all clean (I-83/I-84/I-101 fixes in place).
- **03-playbooks**: 03.1–03.5 — all clean except the I-102 provenance note (03.5:185). I-85/I-86/I-95 fixes in place.
- **README**: index, all cross-references valid.
- **CLI flags**: check -s1/-s2 (not -s), make_ndx -[no]twin/-natoms (no -select/-id), wham/awh/covar/msd/spatial/dipoles/anaeig/nonbonded-benchmark flags all present.
- **MDP options**: emstep, gen-vel/temp/seed, nstcomm, vdw-modifier, rvdw-switch, verlet-buffer-tolerance, mts/mts-levels/mts-level2-forces/mts-level2-factor, sc-function/sc-r-power/sc-coul/sc-power/sc-sigma, dhdl-derivatives, awh-*, pull-coordN-*, annealing/annealing-npoints/annealing-time/annealing-temp, pcoupl=C-rescale, refcoord-scaling=com, pbc=xyz, comm-mode=angular — all present and correct.
- **GPU env vars**: GMX_GPU_ID, GMX_GPU_PME_DECOMPOSITION, GMX_DISABLE_DIRECT_GPU_COMM present; GMX_FORCE_GPU_ID, GMX_GPU_DD_COMMS, GMX_GPU_PME_PP_COMMS absent.

## Notes
- **No build drift, no KB drift**: this is a pure regression pass. The only new finding (I-102) is a stale provenance note that was explicitly flagged in the I-95 fix pass (2026-09-30) as "Candidate for the next audit."
- **Probe-suite artifact (not a KB issue)**: `probe-suite/01_matrix/base.mdp` carries `exit = yes` and `unknown = yes` lines (a probe-harness leftover from matrix generation). `grompp` rejects these as "Unknown left-hand side: exit" / "Unknown left-hand side: unknown" — the probe files are not valid standalone MDPs. This does not affect any KB claim; the probe suite is a test harness, not KB content.
- **I-102 severity is [L]**: it is a provenance/source-attribution note, not a build claim in the main content. The main GPU-isolation env-var table (03.5:153–157) is already correct (I-95). The fix is a one-line parenthetical replacement.

## Fix pass (2026-09-30 — build 2026.3-dev-20260625-1210900-unknown)

**Scope:** 1 open issue (I-102) from the full-KB regression audit (2026-07-21).
**Result:** 1 fixed, 0 already-fixed (closed), 0 false-positive (closed), 0 left open.

#### I-102 03.5 provenance note lists two absent GPU env vars as "re-verified" — FIXED  ✅ RESOLVED (2026-09-30)
Files: `03-playbooks/03.5-performance.md` (as listed in the issue)
- **Preflight**: re-ran the issue's probe (strings sweep of `libgromacs.so*` + `bin/gmx` in the transient container). Issue confirmed still real: `GMX_FORCE_GPU_ID` and `GMX_GPU_DD_COMMS` absent (no substring match; the only `GMX_FORCE_*` vars in the build are `GMX_FORCE_GPU_AWARE_MPI` and `GMX_FORCE_UPDATE_DEFAULT_CPU`); `GMX_GPU_ID`, `GMX_GPU_PME_DECOMPOSITION`, `GMX_DISABLE_DIRECT_GPU_COMM` present. Stale text located at 03.5:185 (the provenance note).
- **Applied**: line 185: `(`GMX_FORCE_GPU_ID`, `GMX_GPU_DD_COMMS`, `GMX_GPU_PME_DECOMPOSITION`)` → `(`GMX_GPU_ID`, `GMX_GPU_PME_DECOMPOSITION`, `GMX_DISABLE_DIRECT_GPU_COMM`)`.
- **Evidence**: strings sweep of `/usr/local/gromacs/lib/libgromacs.so` (transient `gromacs-hip-gfx1100:latest` container), sorted `GMX_*` set, relevant lines verbatim:
  ```
  GMX_DISABLE_DIRECT_GPU_COMM
  GMX_GPU_ID
  GMX_GPU_PME_DECOMPOSITION
  ```
  `GMX_FORCE_GPU_ID` / `GMX_GPU_DD_COMMS` appear nowhere in the set. Identical result in the post-fix suite snapshot `snapshot/04_envvars.txt`. The corrected parenthetical now matches the main GPU-isolation env-var table (03.5:107–109) exactly.
- **No deviation**: the Recommended fix was applied verbatim; all three new tokens were confirmed present in the build before applying (rule 4).

## Notes for the auditor
- **Image sha changed since the audit section**: the 2026-07-21 audit records `image sha256:4d59c576…`; the current `gromacs-hip-gfx1100:latest` is `sha256:70c2e747e755f4f7dbd3d72b31fe002c70f2c0db9bb044fe76a584a50a4b8488` (created 2026-09-16). The drift gate passed on the contract's criterion — `gmx --version` = `2026.3-dev-20260625-1210900-unknown` with all Gold-standard attributes identical (TNG on, Colvars on, CP2K off, Torch off, Plumed on, GPU=HIP, SIMD=AVX2_256, VkFFT 1.3.1, 101 commands) — but the sha difference is worth reconciling (rebuild with identical source, or re-tag).
- **Regression suite (post-fix)**: 30 blocks probed, all `unknown=0 invalid=0 obsolete=0`; block summary verdict lines byte-identical to the pre-fix baseline (detail lines identical modulo per-run GROMACS reminder-quote log line shifts); `03_matrix_verdicts.txt` byte-identical to baseline (only the documented false-positive-class (a)/(d) lines plus the documented probe-harness `exit`/`unknown` leftovers). No NEW parse signal, no reverts.
- **Stale-text sweep**: KB content (00–03 + README, excluding issues_kb.md) is clean of `GMX_FORCE_GPU_ID` and `GMX_GPU_DD_COMMS` — no stragglers.
- **No deviations, no handbacks.**
