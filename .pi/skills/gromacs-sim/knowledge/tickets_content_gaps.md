# Tickets — KB Content Gaps

**Purpose**: track *content* additions the knowledge base should make that are
not audit findings (see `issues_kb.md`) and not Lemkul-import items (see
`tickets_lemkul_import.md`). A content gap is a topic the KB is expected to
cover but currently does not (or covers only partially). One ticket per gap.
When the work is implemented **and validated** against the build, mark the
ticket `RESOLVED` with the date and add a resolution-log row.

**Ticket IDs**: `C-NN` (content), distinct from audit `I-NN` and import `T-NN`.

**Global rules (apply to every ticket here)** — same discipline as the import
tracker:

**Build & container.** Build `gromacs-hip-gfx1100:latest` runs in container
`gromacs-rocm` (compose profile `gromacs`). If not running:
`cd /home/<user>/docker/genai_stack && make gromacs`. **The GPU is used by
the agent — every GROMACS run here is CPU-only** (`-nb cpu -pme cpu`); no
`mdrun`/GPU work (matches the audit skill's no-GPU rule).

1. **Adapt to the build.** This KB is pinned to **2026.3**
   (`gromacs-hip-gfx1100:latest`). Any MDP block added must be
   **grompp-verified** against the build; any CLI flag must be confirmed with
   `gmx <tool> -h`. Where an external tool (web server, app) is the source of
   parameters, verify the *output format* against the build's conventions, not
   the tool itself.
2. **Build is the gold standard.** Where external docs and the build disagree,
   the build wins.
3. **Provenance.** If a section incorporates a specific external source
   (tool docs, paper), add a `> **Provenance**: ...` line to the target KB
   file. Cite standard literature where the science is used.
4. **Do not propagate known defects** in external sources; flag any
   reconstruction choice the sources don't pin down.
5. **Match the KB's format.** Model the new sections on the existing
   "Ligand / small-molecule parameterization" + CGenFF worked-example
   sections in `00.6`: a short "When to use" lead-in, numbered steps,
   cross-refs written as `(see 0X.Y)`, and a trailing `> **Provenance**: ...`
   blockquote where an external source is used.

---

## C-01 — Carbohydrate & inorganic-species parameterization

- **Status**: [x] RESOLVED (2026-09-16)
- **Target**: `00-foundations/00.6-force-fields-water.md` — two new
  subsections, inserted **after the CGenFF worked-example section**
  ("CGenFF (CHARMM) workflow — worked example (2-propylphenol, `JZ4`)"),
  within the "Ligand / small-molecule parameterization" area: (A)
  "Carbohydrates / sugars", (B) "Inorganic species".
- **Related (integration)**: `00.4-topology-anatomy.md` ("Ligand / custom
  molecule"), `01.2-topology-forcefield.md` (assembly). No changes expected
  there — both already describe the generic parameterize → `#include` →
  `[ molecules ]` → regen `.tpr` flow that these two subsections plug into.

### Story

As an agent asked to set up a system containing a **sugar** (glycoprotein,
glycan, polysaccharide, sugar-containing ligand) or an **inorganic species**
(buffer/metal ion, metalloprotein, phosphorylated metabolite, coordination
complex), I want the KB to document the correct parameterization route and its
force-field-matching constraints, so I don't silently apply an organic-ligand
route (antechamber/CGenFF) to a case it does not cover.

### Why this is a gap (evidence from the current KB)

`00.6` covers **organic small-molecule** parameterization with a force-field
route table (AMBER `antechamber`/ACPYPE, CHARMM CGenFF, OPLS ACPYPE/manual,
GROMOS manual) and a full CGenFF worked example (2-propylphenol, `JZ4`).
Grep of the whole KB (2026-09-15) shows:

- **No carbohydrate route.** Zero hits for `GLYCAM` (the standard
  carbohydrate toolchain). Sugars/glycans are not addressed at all.
- **No inorganic-species section.** No content on metal-ion / inorganic-anion
  / coordination-complex parameterization. The ion content that exists is
  limited to standard neutralizing ions via `genion` (see `01.3`).

So both requested classes fall outside the KB's current parameterization
coverage. This ticket closes that.

### Scope & content spec

#### (A) Carbohydrates / sugars — new subsection

> **Research required (do not write from memory).** Source this section from
> GLYCAM's official documentation (glycam.org) and give it a provenance line.
> Confirm against the docs before writing: the current GLYCAM carbohydrate FF
> (GLYCAM06 is the standard — verify it is still current), the access method
> (web server and/or Mordred app), the exact GROMACS output files (`.itp`
> moleculetype + `.gro` + `.mol2`), the AMBER protein FF it pairs with, and
> reducing-end / anomeric-configuration handling. If the docs are
> unreachable, mark the section **"unverified — needs GLYCAM docs"** and do
> **not** invent details.

1. **When to use**: glycoproteins, free glycans, polysaccharides,
   sugar-containing ligands/substrates. Distinguish from organic ligands
   (the CGenFF/antechamber routes do **not** apply to carbohydrates).
2. **The GLYCAM route (the standard)**:
   - GLYCAM web server / Mordred app (glycam.org) → **GLYCAM06** parameters
     (AMBER-based).
   - Workflow: prepare the glycan (PDB/mol2, defined glycosidic linkages and
     anomeric configuration) → submit → receive `.itp` (a full
     `[ moleculetype ]`) + `.gro` (+ `.mol2`).
   - Note the reducing-end / linkage handling and that glycans are typically
     neutral (no net charge → no `genion` neutralization for the glycan).
3. **Force-field matching (critical)**: GLYCAM06 is **AMBER-compatible** →
   pair with an AMBER protein FF (this build ships `amber14sb.ff`,
   `amber19sb.ff`, `amber99sb.ff`, …) + TIP3P. Do **not** mix GLYCAM with
   CHARMM (CGenFF) or OPLS parameter sets.
4. **Integration**: identical to the existing ligand flow — `#include` the
   glycan `.itp` before `[ system ]`, add to `[ molecules ]`, append
   coordinates in matching order, regen `.tpr` (cross-ref `00.4` / `01.2`).
5. **Caveats**: glycan conformational flexibility, multiple glycoforms
   (mixture → separate moleculetypes or a representative), QM validation of
   new linkages.

#### (B) Inorganic species — new subsection

1. **Standard inorganic ions already in the FF**: each FF directory ships
   ions **bundled per water model** in `ions_<model>.itp` (e.g.
   `amber14sb.ff/ions_tip3p.itp`, `ions_spc.itp`, `ions_opc.itp`, …). In this
   build `ions_tip3p.itp` defines a broad set — `NA`, `CL`, `K`, `MG`, `CA`,
   `LI`, `ZN`, `FE`/`FE2`, `MN`, `AG`/`AG2`, `AL`, `BA`, … (with
   oxidation-state variants). **Pick the `ions_<model>.itp` matching your
   water model** (ion LJ parameters are water-model-specific) and add them
   via `gmx genion` (cross-ref `01.3`). Full list: see V1.
2. **Non-standard / exotic inorganic species** (specific coordination
   complexes, unusual oxidation states, inorganic anions not in the FF):
   - No standard parameters → **manual parameterization**: QM-derived partial
     charges, bonded terms from literature/experiment; document the source.
   - **Metal coordination is hard**: d-electron/polarizability effects mean a
     fixed-charge additive FF is often inadequate. Note the options:
     restrained/position-restrained metal, dedicated ion models, polarizable
     FFs (Drude), or QM/MM for the active site. Flag as a case-by-case,
     high-uncertainty setup.
3. **Inorganic functional groups on organic molecules** (phosphate, sulfate,
   nitrate — e.g. phosphorylated metabolites, nucleotides): check FF
   availability (some are in CGenFF/CGenFF-Silicon / standard nucleotide
   residues); where absent, manual parameterization as in (2).

### Verification plan (against build 2026.3)

- **V1 (inorganic, build-verified)**: enumerate the `ions_<model>.itp` files
  per FF directory and the `[ moleculetype ]` names each defines
  (`docker exec gromacs-rocm sh -c 'grep -A2 "\[ moleculetype \]"
  /usr/local/gromacs/share/gromacs/top/*.ff/ions_*.itp'`),
  and confirm `gmx genion -h` accepts them. The subsection's ion list and the
  water-model-bundling note must match the build exactly (this build ships 62
  ion types per water model, e.g. `NA`, `CL`, `K`, `MG`, `CA`, `NH4`, `CE4`,
  `FE`/`FE2`, …).
- **V2 (CLI)**: confirm any referenced flags (`genion`, `pdb2gmx` for
  standard residues) against `gmx <tool> -h` in 2026.3.
- **V3 (carbohydrate, external-source-verified)**: GLYCAM is external (not in
  the build). Verify the **output format** (GLYCAM06 `.itp` = a standard
  `[ moleculetype ]`) against the build's topology conventions (`00.4`), and
  confirm the AMBER FFs it pairs with (`amber14sb.ff`/`amber19sb.ff`) are
  present in the build. Cross-check the route against GLYCAM documentation.
- **V4 (placement / xref)**: both subsections sit under the `00.6`
  parameterization area; xrefs to `00.4`/`01.2`/`01.3` resolve; provenance
  line(s) present where an external source is used.

### Out of scope

- Actually parameterizing a specific sugar/inorganic molecule (that is
  user-specific work; the KB documents the *route*, not a specific result).
- Polarizable-FF / Drude setup details (note as an option; a full Drude
  playbook is a separate, larger ticket if ever needed).

### References

- `00-foundations/00.6-force-fields-water.md` (existing ligand section +
  CGenFF worked example — the model for format).
- `00-foundations/00.4-topology-anatomy.md`, `01-phases/01.2-topology-forcefield.md`
  (integration), `01-phases/01.3-solvation-ions-box.md` (`genion`).
- GLYCAM documentation (glycam.org) for the carbohydrate route.

### Related (separate, not part of this ticket)

The deferred **topology-directive probe** enhancement to the audit skill
(see the 2026-09-15 skill review) is a *verification* concern: it would
mechanically check `[ … ]` directives in the KB. This ticket is a *content*
concern. If C-01 adds topology-heavy examples (GLYCAM `.itp`, ion
moleculetypes), the deferred probe would gain more value — revisit it if this
ticket lands.

### Resolution notes (2026-09-16)

Implemented in `00.6` as two `###` subsections immediately after the CGenFF
worked example. Two spec premises did not survive verification (build/docs are
the gold standard) and were written as the verified facts instead:

1. **GLYCAM server output is AMBER, not GROMACS.** The current GLYCAM-Web
   Carbohydrate Builder's "Download Files For MD Simulation" archive contains
   `prmtop`/`parm7` + `inpcrd`/`rst7` (verified against
   glycam.org/docs/help/tag/carbohydrate-builder/, accessed 2026-09-16) —
   not `.itp`/`.gro`/`.mol2`. The subsection therefore documents the
   AMBER→GROMACS conversion step (ACPYPE / manual / doGlycans). Also
   build-verified: `ant2gmx` is **not a command in 2026.3**
   (`'ant2gmx' is not a GROMACS command`), so the conversion cannot rely on
   it.
2. **Ion counts differ per water model.** `amber14sb.ff`/`amber19sb.ff`
   `ions_tip3p.itp` defines 62 types, `ions_opc.itp`/`ions_opc3.itp` 60 (no
   `NH4`/`H3O`), `ions_spc.itp`/`ions_spce.itp`/`ions_tip4pew.itp` 57 (no
   `AG`/`CU1`/`NH4`/`H3O`/`TL`) — not "62 per water model". Other FF
   directories ship a single plain `ions.itp` (oplsaa 11, charmm27 8,
   gromos54a7 7, amber99sb-ildn 10 types). The top-level `ions.itp` is a
   `#error` stub in 2026.3. The subsection states the per-model counts.

Verification (all against `gromacs-rocm`, 2026.3-dev-20260625, CPU-only):
- **V1**: `ls`/`grep` of `top/*.ff/ions*.itp` — files, per-model type counts,
  and the 14sb-vs-19sb set identity confirmed (diff of sorted moleculetype
  lists).
- **V2**: `gmx genion -h` (flags + "monoatomic ions" + insert-molecules
  recommendation quoted verbatim), `gmx insert-molecules -h`, `gmx pdb2gmx -h`.
- **V3**: GLYCAM06 current revision 06j + 12SB amino variants confirmed on
  glycam.org "All Parameters" page; `amber14sb.ff`/`amber19sb.ff` present in
  build; `ant2gmx` absent (build-verified).
- **V4**: subsections sit in the `00.6` parameterization area after the CGenFF
  example; xrefs to `00.4` ("Ligand / custom molecule"), `01.2`, `01.3`
  resolve; provenance lines present in both subsections.

---

## Resolution log

| Ticket | Resolved | Probe/verification evidence (summary) |
|--------|----------|----------------------------------------|
| C-01   | 2026-09-16 | V1: per-model ion sets enumerated (amber14sb/19sb: tip3p=62, opc/opc3=60, spc/spce/tip4pew=57; other FFs plain `ions.itp`; top-level `ions.itp` = `#error` stub). V2: `genion`/`insert-molecules`/`pdb2gmx` flags via `-h`. V3: GLYCAM06j + AMBER output files confirmed on glycam.org; `amber14sb.ff`/`amber19sb.ff` present; `ant2gmx` absent in build. V4: placement after CGenFF example, xrefs to 00.4/01.2/01.3 resolve, provenance lines present. Two spec deviations documented in Resolution notes. |
