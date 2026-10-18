# Tickets — Ligand Scope Expansion (agent + skill + KB)

**Purpose**: track the expansion of the `gromacs-md` agent / `gromacs-sim`
skill from protein-only to **protein–ligand** simulations. One ticket per
workstream. This is a *scope* ticket, not a pure KB-content ticket — it spans
agent, skill, KB, and container tooling. It is persisted here for
finetuning/resolution before any implementation.

**Ticket IDs**: `L-NN` (ligand scope), distinct from audit `I-NN`, content
`C-NN`, and import `T-NN`.

**Motivation (2026-07-24)**: ligand MD is a first-class, well-supported use
case in the field, while our agent currently **refuses** ligand
parameterization (Tier C) even though the KB already documents the
parameterization routes. We reviewed the Pymacs suite (`gromacs/work/Pymacs`)
and used its content to inform this ligand-scope expansion. User decision:
extend agent scope to ligands. Details to be finetuned in review.

**Global rules** — same discipline as the other trackers: build
`gromacs-hip-gfx1100:latest` (2026.3) is the gold standard; every MDP/flag
added must be grompp/`-h`-verified against the build; provenance lines for
external sources; no known defects propagated.

---

## L-01 — Agent/skill/KB ligand support (umbrella)

- **Status**: [ ] OPEN (proposal — awaiting finetuning)
- **Target**:
  - `.pi/agents/gromacs-md.md` (Tier C → ligand in scope; Tier A ligand questions)
  - `.pi/skills/gromacs-sim/` (new ligand runbook + gate; phase 5/6 surgery)
  - `.pi/skills/gromacs-sim/knowledge/` (`00.6`, `01.3`, `01.5`, `02.02`, `03.2`)
  - `gromacs/Dockerfile.mdprep` (v1.1 tooling — see open question D2)
- **Related (integration)**: `C-01` (carbohydrate/inorganic parameterization,
  RESOLVED — its routes plug into the same ligand phase), `00.6` CGenFF
  worked example (JZ4).

### Story

As a user who wants a **protein–ligand** MD simulation ("run me a simulation
of this drug bound to this protein"), I want the agent to accept a ligand,
parameterize it (or integrate a user-supplied `.itp`), build the complex
topology, run the standard pipeline with ligand-aware settings (ligand
restraints, coupling groups, cutoff inflation), and report ligand-relevant
metrics — instead of being told "ligand parameterization is out of scope".

### Why this is a gap (evidence, 2026-07-24)

- **Agent** (`.pi/agents/gromacs-md.md`, Tier C): "out of scope: new force
  fields, **ligand parameterization**, membrane systems → refuse and say why."
- **Skill**: no ligand phase, no ligand gate, no ligand posre, no ligand
  `tc-grps` handling. Phase 2 (`02-topology.md`) is protein-only.
- **KB**: `00.6` already documents AMBER (`antechamber`/ACPYPE), CHARMM
  (CGenFF, full JZ4 worked example incl. penalty-score gate), OPLS (ACPYPE),
  GROMOS (manual) routes + validation step ("short vacuo/EM test is stable
  before solvating") — **knowledge exists, no workflow consumes it**.
  `02.02` covers protein posre only (no ligand posre). No large-ligand
  cutoff-inflation guidance anywhere (a large ligand/PROTAC needs
  `cutoff ≥ max(1.5 nm, ligand_span + 0.1 nm)` so it never straddles the
  cutoff; rule informed by Pymacs).
- **Tooling**: `md-prep` is python3+matplotlib only. `Dockerfile.mdprep`
  header already plans **v1.1: ACPYPE + AmberTools (antechamber/sqm) +
  PROPKA + PDB2PQR + MDAnalysis** — not yet built.
- **FF constraint**: build ships `amber14sb`, `oplsaa`, `charmm27`,
  `gromos54a7` — **no `charmm36.ff`**. The CGenFF route needs `charmm36.ff`
  added (data-only drop-in, no rebuild); the AMBER route works with shipped
  FFs.

### Proposal (to be finetuned)

**Tier design**

| Tier | What | Examples |
|------|------|----------|
| **A** (user decides) | which ligand(s); protonation state / input 3D structure; parameterization route (ACPYPE vs CGenFF vs user-supplied `.itp`) | "ligand UNK, pH 7.4, use ACPYPE" |
| **B** (agent executes, records in `state.json`/`RUNLOG.md`) | running the parameterization, topology integration, ligand posre, `tc-grps` surgery, cutoff inflation, ligand-relevant analysis choices | ACPYPE invocation, `#include "unk.itp"`, `genrestr -fc 1000` |
| **C** (still refused) | new force fields, membrane systems, QM/MM, alchemical FEP (separate tickets if ever wanted) | unchanged |

**Workstreams**

- **L1 — KB content** (small, independent):
  1. `02.02`: ligand position restraints — `gmx genrestr -f LIG.gro -n
     index_LIG.ndx -o posre_LIG.itp -fc 1000 1000 1000` on non-H atoms;
     include inside the ligand moleculetype; on for equilibration, off for
     production.
  2. `01.5` + `03.2`: ligand-aware `tc-grps` — `Protein_LIGAND
     Water_and_ions` (merged solute group) vs `Protein Non-Protein`; when to
     merge (ligand < 10% of atoms → merge into protein group to avoid the
     DoF NOTE).
  3. `01.3` + `01.5`: large-ligand cutoff inflation — `rvdw/rcoulomb/rlist ≥
     max(1.5 nm, ligand_span + 0.1 nm)` so a large ligand/PROTAC never
     straddles the cutoff; span = max inter-atom distance of the ligand GRO.
  4. `00.6`: CHARMM+SPC note — SPC coordinates (`spc216.gro`) acceptable with
     any 3-site model; SPC+CHARMM36 common in literature, TIP3P remains the
     canonical CHARMM partner.
- **L2 — Skill** (medium):
  1. New runbook `references/02b-ligand.md` (entry: phase 1 passed; actions:
     route execution / `.itp` intake → validation → topology integration).
  2. New gate `scripts/check_ligand.sh`: ligand `.itp` present; ligand charge
     integer; atom names consistent with `.gro`; vacuo-EM stable (short
     `steep` run, no `force not finite`); CGenFF penalty score < 50 recorded
     (gate on < 10 "use as-is", 10–50 "flag for user", > 50 "refuse" — per
     `00.6` table).
  3. Phase 5 (`05-equilibration.md`): ligand posre include + `tc-grps`
     surgery + cutoff-inflation check before grompp.
  4. Phase 6: no posre in production (unchanged); ligand group in analysis.
  5. `SKILL.md` phase table: insert `2b ligand` (gate `check_ligand.sh`),
     conditional (only when a ligand is present).
- **L3 — Agent** (small): remove "ligand parameterization" from Tier C; add
  ligand questions to Tier A; description line updated.
- **L4 — Tooling** (decision-gated, see D2): md-prep v1.1 (ACPYPE +
  AmberTools) and/or `charmm36.ff` into the gromacs image.

**Sequencing proposal**: L1 (KB, small) → L3 (agent) → L2 (skill) → L4
(tooling, per decision). L2's gate makes the workflow deterministic; L4 only
needed for the *agent-runs-parameterization* variant.

### Open questions (resolve before implementation)

- **D1 — FF route**: add `charmm36.ff` to the gromacs container (enables the
  CGenFF route, data-only drop-in), or start **AMBER-only**
  (antechamber/ACPYPE with shipped `amber14sb`)?
- **D2 — Tooling**: build md-prep v1.1 (ACPYPE + AmberTools) now so the agent
  can *run* parameterization, or scope ligands to **user-supplied `.itp`
  first** (agent integrates + validates + simulates; no new tooling)?
- **D3 — Tier split**: confirm route = Tier A, execution = Tier B (per
  proposal), or make the whole ligand step Tier A-confirmed?
- **D4 — Ligand count**: single ligand only, or multiple ligands/cofactors?
  Proposal: single primary ligand + optional retained cofactors.
- **D5 — Analysis scope**: which ligand metrics enter `analyze.sh` /
  REPORT.md? Proposal: ligand RMSD/RMSF (backbone-fit), ligand–protein
  interaction energy (`energygrps` recipe, KB `01.8`), H-bond counts;
  contact maps/networks deferred.

### Verification plan (against build 2026.3)

- **V1 (KB)**: every added MDP block grompp-verified; `genrestr` flags via
  `-h`; cutoff-inflation rule stated as a check, not a command.
- **V2 (gate)**: `check_ligand.sh` tested green on the JZ4 CGenFF example
  (KB `00.6`) and red on a deliberately broken `.itp` (non-integer charge).
- **V3 (end-to-end)**: one protein–ligand sim through phases 1→8 with the
  new phase 2b; all gates pass; REPORT.md contains the ligand metrics.
- **V4 (agent)**: Tier A/B/C behavior exercised with a ligand request
  (agent asks route, executes, records; membrane request still refused).

### Out of scope

- PROTAC/ternary-complex workflows — separate ticket if wanted.
- Alchemical ligand free energy (FEP/TI) — `02.03` territory, separate effort.
- Covalent ligands (the default workflow stays non-covalent).
- Membranes, QM/MM, new FFs (remain Tier C).

### References

- **Provenance**: `gromacs/work/Pymacs` (schurerlab/Pymacs) — content used to
  inform this ligand-scope expansion; full comparison in
  `gromacs/work/Pymacs_comparison_report.md` (2026-07-24). Paper: Schulz,
  Reynolds, Schürer, *Eur. J. Med. Chem.* (2026) 316:119038,
  doi:10.1016/j.ejmech.2026.119038.
- KB: `00.6` (routes + CGenFF example), `00.4` (topology), `01.2` (assembly),
  `01.3` (box/cutoff), `01.5` (equilibration), `02.02` (posre), `03.2`
  (templates), `C-01` (carbohydrate/inorganic routes).

### Resolution notes

(none yet)

---

## Resolution log

| Ticket | Resolved | Probe/verification evidence (summary) |
|--------|----------|----------------------------------------|
| —      | —        | —                                      |
