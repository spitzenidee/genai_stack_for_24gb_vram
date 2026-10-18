# GROMACS MD Expert — Knowledge Specification

A version-pinned (GROMACS **2026.x**) knowledge base for an expert agent that
**prepares, sets up, and executes molecular dynamics (MD) simulations with
GROMACS**. Organized along two axes:

- **Primary axis — MD phase** (`01-phases/`): the pipeline in execution order.
- **Secondary axis — MD type** (`02-md-types/`): each simulation type,
  cross-referencing the phases it modifies.

Supporting material lives in `00-foundations/` (tool/version/file context) and
`03-playbooks/` (agent-facing decision guidance, templates, checklists).

## How to use this spec

1. **Confirm the stack mode first** (Phase 0, `03.3`): this stack's eGPU
   modes are mutually exclusive and share VRAM — the `gromacs` mode must be
   active and the VRAM free before any `grompp`/`mdrun`. A startup crash here
   is a mode/VRAM issue, not a physics blow-up.
2. **Start at the phase** that matches the user's current step (most requests
   are "I have a structure, run me a simulation" → begin at `01.1`).
3. **Identify the MD type** the user wants (default: standard NPT, `02.01`).
   The type file tells you which phase sections to deviate from.
4. **Consult the playbooks** (`03/`) for decision trees, annotated MDP
   templates, per-phase checklists, failure diagnosis, and performance tuning.
4. Every phase file follows: *purpose → tools/commands → key MDP options
   (recommended value + rationale) → common errors → validation criteria →
   outputs*. Every type file follows: *when to use → prerequisite phases →
   setup → MDP deltas vs. standard → analysis → pitfalls*.

## File map

```
knowledge/
├── README.md                          ← this file
├── 00-foundations/
│   ├── 00.1-versions-install.md       versions, what's new, env vars, validation
│   ├── 00.2-command-surface.md        gmx subcommands: purpose + key flags
│   ├── 00.3-file-formats-dataflow.md  .pdb/.gro/.top/.itp/.tpr/.xtc/.edr/.cpt/.ndx
│   ├── 00.4-topology-anatomy.md       .top/.itp sections, ordering, charge groups
│   ├── 00.5-mdp-anatomy.md            MDP sections, units, option conventions
│   └── 00.6-force-fields-water.md     force fields, water models, ligand parameterization
├── 01-phases/
│   ├── 01.1-structure-preparation.md  PDB curation, hydrogens, pdb2gmx
│   ├── 01.2-topology-forcefield.md    topology assembly, restraints, ligands
│   ├── 01.3-solvation-ions-box.md     solvate, genion, box size rules
│   ├── 01.4-energy-minimization.md    steep/cg/l-bfgs, emtol, Fmax
│   ├── 01.5-equilibration.md          NVT→NPT, thermostats, barostats
│   ├── 01.6-production.md             integrator, dt, output, drift
│   ├── 01.7-restart-parallelization.md  checkpoints, convert-tpr, MPI/GPU
│   ├── 01.8-analysis.md               trajectory processing + all gmx analysis tools
│   ├── 01.9-troubleshooting.md        error catalog + blowing-up diagnosis
│   └── 01.10-cleanup-retention.md     #name.N# auto-backups, retention policy, disposal
├── 02-md-types/
│   ├── 02.01-standard-ensembles.md    NVE/NVT/NPT/NPH + integrator compatibility
│   ├── 02.02-position-restraints.md   genrestr, staged relaxation
│   ├── 02.03-alchemical-free-energy.md  FEP/TI, lambda, soft-core, BAR/WHAM
│   ├── 02.04-pmf-umbrella.md          pull code, umbrella, WHAM combination
│   ├── 02.05-metadynamics-awh-colvars.md  PLUMED, AWH (native), Colvars
│   ├── 02.06-expanded-ensemble-replica-exchange.md  free-energy=expanded, MC moves
│   ├── 02.07-nemd-pulling.md          pulling (2026.3 pull API), shear, Jarzynski
│   ├── 02.08-langevin-brownian.md     sd/bd integrators, tau-t friction, bd-fric
│   ├── 02.09-simulated-annealing.md   annealing protocol (2026.3 annealing-time/temp)
│   ├── 02.10-qmmm.md                  qmmm-cp2k module, mimic integrator, GEEP
│   ├── 02.11-nnpot.md                 nnpot module (neural-network potentials)
│   ├── 02.12-coarse-grained.md        Martini, CG workflow
│   ├── 02.13-membranes.md             semiisotropic coupling, bilayer setup
│   ├── 02.14-specialized.md           E-fields, FMM, DGS, TPI, walls, NMR
│   ├── 02.15-biphasic-interfaces.md   water/oil boxes, insert-molecules, vdwradii trick
│   └── 02.16-virtual-sites.md         mass centers, linear molecules, in-vacuo MoI
└── 03-playbooks/
    ├── 03.1-decision-trees.md         goal → MD type → phase sequence routing
    ├── 03.2-mdp-templates.md          annotated .mdp templates per phase/type
    ├── 03.3-checklists.md             pre-flight + post-run validation per phase
    ├── 03.4-failure-diagnosis.md      failure → diagnosis → fix table
    └── 03.5-performance.md            hardware → ntomp/ntdd/GPU/PME tuning
```

## Sources & attribution

This knowledge base is **adapted (not copied)** from:

> J. A. Lemkul, *From Proteins to Perturbed Hamiltonians: A GROMACS
> Tutorial*, LiveCoMS **1**(1):5068 (2019).
> doi:10.33011/livecoms.1.1.5068.
> https://github.com/jalemkul/gmx_tutorials_livecoms (CC BY 4.0).

> J. A. Lemkul, *Introductory Tutorials for Simulating Protein Dynamics with
> GROMACS*, J. Phys. Chem. B **128**:9418–9435 (2024).
> doi:10.1021/acs.jpcb.4c04901 (CC BY 4.0).
> https://github.com/Lemkul-Lab/gmx_tutorials_jpcb (MIT).

- Every imported section has been **re-verified against the local 2026.3
  build** (gromacs-rocm, 2026.3-dev) — commands, flags, MDP options, enums,
  and force-field details are confirmed against the build, not taken from the
  source at face value. Where 2026.3 diverges from the source (e.g. the
  removed `group`/`ns` cutoff schemes, renamed topology directives), the build
  is authoritative and the divergence is called out.
- Each file carries a **per-file provenance line** (a `> **Provenance**: ...`
  blockquote near the end) naming the specific tutorial/section and the probe
  directory it was verified against. Files that draw on the JPCB tutorial
  carry an additional `> **Provenance (JPCB)**: ...` line.
- Import tracking: `tickets_lemkul_import.md` (LiveCoMS) and
  `tickets_jpcb_import.md` (JPCB) — one ticket per imported addition, with
  per-ticket verification evidence.

## Version pinning & change notes

- **Target: GROMACS 2026.x** (this stack builds **2026.3** with the HIP
  backend for gfx1100). 2027 is the in-development series.
- Where 2026 guidance differs from older tutorials, the change is called out
  inline with a `**2026:**` marker. Key deltas vs. pre-2026 docs:
  - **Berendsen thermostat/barostat** are now explicitly discouraged for new
    production runs (use **v-rescale** / **C-rescale**).
  - **MTTK barostat deprecated** (use C-rescale or Parrinello-Rahman).
  - New force fields **AMBER14SB / AMBER19SB**; new water models **OPC / OPC3**.
  - **NNPot** (neural-network potentials) module; hybrid NNP/MM supported.
  - **TNG** is a first-class trajectory format (coords/velocities/forces/
    energies); `.xtc` remains the default compressed output.
  - **Full HIP** (AMD GPU) support; GPU-resident update requires
    `-ntmpi 1`; `constraints = h-bonds` is performance-recommended
    (all-bonds falls back to CPU).
- **2026.3 API breaks** (verified against this build — see `issues_kb.md`):
  - **Pull engine rewritten**: `pull = yes` + `pull-ncoords`/`pull-ngroups`/
    `pull-groupN-name` + `pull-coordN-*` (type/geometry/groups/dim/vec/init/
    rate/k). Old `pull-coord`, `pull-coordN-group1/2`, `-increment`,
    `-force-constant`, `-flat-bottom`, `umswitch` are gone.
  - **FEP**: `free-energy-group` gone (alchemical group is in the topology,
    or `couple-moltype`/`couple-lambda0/1`); soft-core renamed (`sc-function`,
    `sc-r-power`, `sc-coul`, `sc-power`, `sc-sigma`); `dhdl-derivatives` is
    yes/no; `dhdl-file`/`gmx pmx`/`gmx g_wham` gone (use `gmx wham`).
  - **Expanded ensemble**: `lmc-mc-move` → `lmc-move`; `min-variance` →
    `minvar`; `lmc-weights-equil` added; `lmc = yes`/`expanded = yes` gone
    (use `free-energy = expanded`).
  - **Annealing**: `annealing-t`/`annealing-p` gone → `annealing-npoints` +
    `annealing-time` + `annealing-temp`; `annealing = group` no longer means
    per-group annealing — the build silently accepts it (and any string) and
    treats it as `No`; use one `no`/`single`/`periodic` value per temperature
    group.
  - **Langevin**: `tau-bfric` gone (`tau-t` is the friction for `sd`);
    `langevin`/`brownian`/`npt`/`qmmm` integrators gone (Langevin = `sd`,
    Brownian = `bd`). Test-particle insertion = `integrator = tpi`/`tpic` +
    `rtpi` (insertion radius — an MDP option, not an integrator).
  - **Thermostats**: new `Andersen`/`Andersen-massive` (not with `md`);
    `md-vv-avek` is validation-only. `pcoupl = Isotropic` is a **legacy
    Berendsen alias** (grompp rewrites it to `Berendsen`; discouraged), not a
    new correct-NPT value.
  - **AWH**: `awh1-ndim` + `awh1-dimN-coord-provider`/`-coord-index` mapping;
    `awh1-target`, `awh1-growth`, `awh1-error-init`, ... added.
  - **Modules** (flat `module-option` MDP names): `qmmm-cp2k-*` (+
    `integrator = mimic`), `nnpot-*`, `fmm-backend` (+ `coulombtype = FMM`),
    `density-guided-simulation-*`, `electric-field-x/y/z = E0 omega t0 sigma`,
    `colvars-active`/`colvars-configfile`.
  - **Removed tools**: `trjpos`→`convert-trj`, `benchmark`→
    `nonbonded-benchmark`, `pmx`, `g_wham`; `do_*` aliases gone.
  - **`-maxwarn` pitfall**: downgrades "Unknown left-hand" errors and runs
    with *default* values for removed options (→ `01.9` §B).
- Experimental features (CUDA graphs, NVSHMEM, ...) require env vars / build
  flags and are **not** for production — see `00.1`.

## Ground rules for the agent

1. **Never guess MDP values.** Use the recommended values in the phase/type
   files or `03.2` templates; always state the rationale.
2. **Always validate** after each phase (see `03.3` checklists) before
   advancing. A bad EM poisons every later phase.
3. **Read error messages literally** — GROMACS errors are descriptive. Map
   them via `01.9` / `03.4` before changing parameters.
4. **Respect the minimum-image rule**: cutoff < half the shortest box vector.
5. **Match force field ↔ water model ↔ ion parameters** (see `00.6`).
6. **Prefer `constraints = h-bonds`** (not `all-bonds`) to keep GPU-resident
   update available on this stack.
7. **Single-rank GPU** (`-ntmpi 1`) for full offload; FEP / domain
   decomposition / replica exchange are incompatible with GPU-resident update.
8. **Keep checkpoints** (`mdrun -cpt`, in minutes) for any run longer than a
   few ns so progress is never lost. (`nstcheckpoint` in the MDP is obsolete
   and silently ignored in 2026.3.)
