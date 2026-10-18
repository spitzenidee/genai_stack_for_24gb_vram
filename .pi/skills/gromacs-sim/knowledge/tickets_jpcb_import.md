# Tickets — Import of Lemkul JPCB Tutorials (`gmx_tutorials_jpcb`)

**Purpose**: track the incorporation of valuable content from the external repo
`https://github.com/Lemkul-Lab/gmx_tutorials_jpcb` and its accompanying article
into this knowledge base. This file is the ticketing system: one ticket per
addition. When a ticket's work is implemented **and validated**, mark it
`RESOLVED` with the date.

**Assessment**: comparison assessment delivered 2026-09-24 (8 actions approved;
chat context — the tickets below are self-contained). All content was
**verified against the local gromacs-rocm build** (2026.3-dev-20260625) before
being written into the KB: grompp parse tests (umbrella + SMD MDPs built clean
TPRs), `gmx <tool> -h` flag checks, and a live `ns_type` obsolete-entry
reproduction.

---

## Source & attribution (applies to ALL tickets)

**Primary source (attribute in every KB file that incorporates its content):**

> **Provenance (JPCB)**: extended from J. A. Lemkul, *Introductory Tutorials
> for Simulating Protein Dynamics with GROMACS*, J. Phys. Chem. B 2024, 128,
> 9418–9435, doi:10.1021/acs.jpcb.4c04901 (CC BY 4.0); input files:
> https://github.com/Lemkul-Lab/gmx_tutorials_jpcb (MIT, © 2024 The Lemkul Lab
> at Virginia Tech).

- The **article** is **CC BY 4.0** — reuse is permitted with attribution.
- The **repo** is **MIT** — reuse is permitted with attribution (copyright
  notice retained in the provenance line).
- Attribution is required **even when content is paraphrased/re-implemented**.
- Add the provenance line as a `> **Provenance (JPCB)**: ...` blockquote at the
  end of each modified KB file (appended after the existing LiveCoMS
  provenance where present).
- **Scripts**: do NOT copy script code verbatim. `find_windows.py` and
  `write_wham_files.py` (repo) are simple Python; document the *algorithm and
  parameters* in KB style (both algorithms are now described in `02.04` and
  `01.8` without copying code). `calc_2d_histogram.pl` (Perl) and
  `plot_free_ener.m` (MATLAB) are **not** ported — the equivalent is ~10 lines
  of numpy in the Python sidecar (stack is Python-only; no Perl/MATLAB).
- **Version note**: the article/repo target GROMACS **2024.1**; this KB is
  pinned to **2026.3**. Where they differ, the 2026.3 build wins (verified):
  `ns_type` is obsolete (ignored), `make_ndx` rename syntax changed to
  `name <nr> <newname>`. The KB documents the 2026.3 behavior and notes the
  delta.

## Source clone

Cloned at `gromacs/work/gmx_tutorials_jpcb/` (gitignored); article text
extracted to `gromacs/work/article_jpcb.txt`. **Do not delete until all
tickets are RESOLVED** (validation re-checks need it).

Key source paths (relative to the clone):
- `inputs/01_ubiquitin/` — protein in water (EM/NVT/NPT/MD + PCA/FES scripts)
- `inputs/02_complex/` — protein dimer/complex (capped PDB, CHARMM36m MDPs)
- `inputs/03_chignolin/` — umbrella sampling (`us.tmpl`, `find_windows.py`,
  `write_wham_files.py`, `run_umbrella_sampling.sh`)

## Ticket status legend

`[ ] OPEN` · `[~] IN PROGRESS` · `[x] RESOLVED (YYYY-MM-DD)`

---

## J-01 — `ns_type` obsolete-entry note

- **Status**: [x] RESOLVED (2026-09-24)
- **Target**: `00-foundations/00.5-mdp-anatomy.md` (section map + invariants)
- **Content**: `ns_type` is obsolete in 2026.3 — grompp prints
  `Ignoring obsolete mdp entry 'ns_type'` and ignores it. Every tutorial MDP
  (2024.1) carries `ns_type = grid`; ported MDPs should drop it.
- **Verification**: reproduced the warning live in the gromacs-rocm container
  (2026.3-dev); grompp proceeds without it.

## J-02 — PCA → FES workflow

- **Status**: [x] RESOLVED (2026-09-24)
- **Target**: `01-phases/01.8-analysis.md` — new section
  "Conformational ensemble (PCA / FES)"
- **Content**: `gmx covar` → `gmx anaeig` → `gmx anaeig -proj`/`-2d`
  (all GROMACS-native) → 2-D histogram + `FES = −k_BT·ln(P_i/P_max)` via the
  Python sidecar (numpy). Replaces the repo's Perl (`calc_2d_histogram.pl`) /
  MATLAB (`plot_free_ener.m`) scripts — not ported, algorithm documented.
- **Verification**: `gmx covar -h` / `gmx anaeig -h` confirm `-proj`, `-2d`,
  `-nframes`, `-eig` flags in 2026.3.

## J-03 — `gmx wham` bootstrap (PMF error bars)

- **Status**: [x] RESOLVED (2026-09-24)
- **Target**: `01-phases/01.8-analysis.md` (WHAM row) +
  `02-md-types/02.04-pmf-umbrella.md` (Analysis)
- **Content**: built-in Bayesian bootstrap — `-nBootstrap <N>`, `-bs-method`,
  `-bs-tau`, `-bs-seed`; results to `-bsres`, profiles to `-bsprof`.
- **Verification**: `gmx wham -h` confirms all flags in 2026.3.

## J-04 — CHARMM36 nonbonded "standard settings" + `rlist` auto-tuning

- **Status**: [x] RESOLVED (2026-09-24)
- **Target**: `03-playbooks/03.2-mdp-templates.md` — new §11 + Notes
- **Content**: CHARMM36 convention block (`rcoulomb`/`rvdw` 1.2,
  `vdw-modifier force-switch`, `rvdw-switch 1.0`, `rlist 1.4`, `pme-order 4`,
  `fourierspacing 0.16`, `dispcorr no`) treated as part of the force field;
  `rlist` auto-tuned by `verlet-buffer-tolerance` (used directly only if
  `verlet-buffer-tolerance = -1`).
- **Verification**: grompp on a CHARMM-style MDP (force-switch + 1.2 nm
  cutoffs) parsed clean; log shows `Determining Verlet buffer … Set rlist …
  to 1.200 nm`.

## J-05 — `make_ndx` rename syntax (2026.3)

- **Status**: [x] RESOLVED (2026-09-24)
- **Target**: `01-phases/01.8-analysis.md` (trajectory preparation, step 1)
- **Content**: rename is `name <nr> <newname>` in 2026.3; the older
  `<nr> <newname>` form (used in the 2024.1 tutorial) is a syntax error.
- **Verification**: reproduced both forms live — `1 Gly1_CA` → `Syntax
  error`; `name 1 Gly1_CA` → accepted.

## J-06 — Umbrella: `dim` Y/N shorthand, bias-free per-window equilibration,
window length, box rule

- **Status**: [x] RESOLVED (2026-09-24)
- **Target**: `02-md-types/02.04-pmf-umbrella.md`
- **Content**: `pull-coord1-dim` accepts `Y`/`N` shorthand (verified); second
  per-window equilibration variant (JPCB: NVT 100 ps + NPT 500 ps **without**
  bias, then umbrella production from `-c npt.gro -t npt.cpt`) alongside the
  existing under-umbrella (LiveCoMS) variant; 50 ns/window production data
  point (26 windows, 0.5–3.0 nm, Δξ 0.1, k=1000); box ≥ 2× max RC rule
  (7.0 nm dodecahedron for 3.0 nm RC) + dodecahedron volume rationale.
- **Verification**: umbrella (`start=no`+`init`, k=1000) and SMD
  (`start=yes`, rate 0.005, k=2000) MDPs from the tutorial built clean TPRs
  on 2026.3.

## J-07 — Disulfide threshold, `-merge`, capping (ACE/NME)

- **Status**: [x] RESOLVED (2026-09-24)
- **Target**: `01-phases/01.1-structure-preparation.md` (pdb2gmx step)
- **Content**: Sγ–Sγ detection threshold 2 Å ± 10% (≈1.8–2.2 Å,
  `specbond.dat`); `-[no]merge` (`no`/`all`/`interactive`) for intermolecular
  disulfides; capping — `-[no]ter` default ionized (NH3⁺/COO⁻), neutral caps
  as named `ACE`/`NME` residues in the input PDB (AMBER: `N`/`C`-prefixed
  terminal residue names, incompatible with `-ter`).
- **Verification**: `gmx pdb2gmx -h` confirms `-merge` enum and the
  ACE/NME/`-ter` behavior in 2026.3.
- **Note**: no external editor is named in the KB (stack policy: no PyMOL
  dependency); cap atoms may be built with any editor.

## J-08 — Small tool additions

- **Status**: [x] RESOLVED (2026-09-24)
- **Target**: `01-phases/01.8-analysis.md` (`gmx analyze`, `rmsf -res`, DSSP
  `MainChain+H`) + `01-phases/01.7-restart-parallelization.md`
  (`convert-tpr -until`/`-extend`, `mdrun -noappend`)
- **Content**: `gmx analyze` (time-series mean/block error); `gmx rmsf
  -[no]res` (per-residue average); DSSP backbone H-bond term needs the
  `MainChain+H` group; `convert-tpr -until <time>` (absolute end time) vs
  `-extend` (add time) vs `-nsteps`; `mdrun -noappend` (fresh output files
  instead of appending).
- **Verification**: all flags confirmed via `-h` on the 2026.3 build.

---

## Not adopted (assessed, deliberately excluded)

- **PyMOL-based capping** — external GUI dependency; KB documents the
  GROMACS-side mechanism only (J-07).
- **Perl/MATLAB plotting scripts** — Python sidecar covers the equivalent
  (J-02).
- **`md_test.mdp`** (repo `01_ubiquitin/inputs/`) — stale leftover from an
  earlier tutorial revision (OPLS lysozyme title, Parrinello-Rahman); not
  used as a reference.
- **`minim.mdp` comment typo** (repo says "max force < 1000.0" with
  `emtol = 500.0`) — repo quirk, no KB impact.
