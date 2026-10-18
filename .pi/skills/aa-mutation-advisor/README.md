# aa-mutation-advisor — bundled knowledge base

Knowledge base for the `aa-mutation-advisor` skill, bundled in the skill's
directory. Provides quantitative AA property data (AAindex 1-3) plus curated
expert chemistry that AAindex lacks, and a prototype advisor script.

## Layout (relative to the skill directory)

```
.
├── SKILL.md                # skill definition
├── SOURCES.md              # FULL attribution: all authors, journals, PMIDs, URLs
├── aaindex_raw/            # raw downloads from genome.jp (aaindex1/2/3, .doc, changelog)
├── data/
│   ├── indices.json        # 551 AAindex1 indices (20 values each)
│   ├── matrices.json       # 86 AAindex2 20x20 matrices
│   ├── contact_potentials.json  # 43 AAindex3 contact potentials
│   ├── references_all.csv  # 680 per-entry references (authors, title, journal, PMID)
│   └── curated/
│       ├── aa_chemistry.json    # pKa, H-bond acceptors, charges (gap-fill; per-field _source)
│       └── chemistry_notes.md   # expert design rules
└── scripts/
    ├── parse_aaindex.py    # raw -> JSON
    ├── advise.py           # prototype advisor (structure-aware)
    ├── pdb_structure.py    # PDB parser + SS (records+DSSP, conservative union) + SASA + Cα neighbors (stdlib only)
    └── advise_structure.sh # one-command structure-aware wrapper (bash+coreutils)
```

**Attribution:** see `SOURCES.md` for the complete source record (database
provenance, primary literature, per-entry references, curated-data sources).

## Sources

**Full attribution is in `SOURCES.md`.** Summary:

- **AAindex** (genome.jp), release 9.2 (Feb 2017) — primary data:
  - AAindex1: 566 single-AA indices (551 parse cleanly)
  - AAindex2: 94 mutation/similarity matrices (86 parse cleanly)
  - AAindex3: 47 statistical contact potentials (43 parse cleanly)
  - Primary literature: Nakai et al. 1988; Tomii & Kanehisa 1996;
    Kawashima & Kanehisa 1999 (PMC102411); Kawashima & Kanehisa 2000;
    Kawashima et al. 2008. Per-entry references (680) in
    `data/references_all.csv`.
- **Curated gap-fill** (`data/curated/`): **fact-checked 2026-07** against
  IMGT (pKa for Asp/Glu/Lys/Arg/His; H-bond donor & acceptor atom counts)
  and Wikipedia (Cys pKa 8.33; Tyr pKa ~10); charge consistent with AAindex
  KLEP840101. Textbooks (Stryer 2015; Lehninger 2017) cited only for the
  protein-pKa-shift caveat. AAindex has no pKa and no H-bond-acceptor data.

## Usage

```bash
# Re-parse raw data (after updating aaindex_raw/)
python3 scripts/parse_aaindex.py aaindex_raw data

# Advise on a substitution (--residue = the residue to mutate)
python3 scripts/advise.py --residue R --goal specificity --context exposed
python3 scripts/advise.py --residue D --goal binding-anion --context exposed
python3 scripts/advise.py --residue E --goal remove-interaction
python3 scripts/advise.py --residue R --goal catalytic

# Structure-aware mode (GROMACS/PDB workflow) — PREFERRED: one-command wrapper.
# Host bash (bash+coreutils only); runs `gmx dssp` (transient gromacs container,
# CPU-only) + advise.py (transient md-prep container); no make gromacs/build/GPU/mode-switch.
scripts/advise_structure.sh structure.pdb 42 specificity
# Equivalent direct call (advise.py reads PDB records + DSSP .dat, conservative union):
python3 scripts/advise.py --pdb structure.pdb --residue 42 --dssp dssp.dat --goal specificity
python3 scripts/advise.py --residue R --structure helix   # no PDB, manual SS
```

**Structure-aware output** adds, for a residue in a defined structure:
- the residue's secondary structure (H/E/T/C), assigned **CONSERVATIVELY** from
  the PDB's HELIX/SHEET records **and** the DSSP `.dat` (helix/strand if
  **EITHER** says so — the two sources genuinely disagree), with the
  per-residue basis (e.g. `PDB records=H, DSSP=T -> H`);
- auto-SASA (exposed/buried) instead of a manual `--context`;
- Chou-Fasman helix/sheet/turn propensity deltas + O'Neil-DeGrado helix ΔΔG;
- **structure warnings** (e.g. *"residue is in an α-helix; Proline is a
  strong helix-breaker (O'Neil-DeGrado ΔΔG +3.0)"*).

## What the data supports

| Question class | Supported by |
|---|---|
| "How much does X→Y change charge/size/polarity?" | `indices.json` (property deltas) |
| "How chemically similar are X and Y?" | `matrices.json` (Grantham, McLachlan) |
| "How often does X evolve to Y?" | `matrices.json` (BLOSUM, PAM) |
| "Is X→Y conservative in an exposed/buried site?" | `matrices.json` (KOSJ context) |
| "Rough stability impact of X→Y?" | `matrices.json` (MJ stability) |
| "Rough pair-energy of X near Y?" | `contact_potentials.json` (MIYS990107; used by `advise.py` in structure-aware mode) |
| "What is the pKa / H-bonding of X?" | `curated/aa_chemistry.json` |
| "Will X→Y break a helix/strand at this residue?" | `indices.json` (CHOP780201/202, ONEK900102) + `pdb_structure.py` |
| "Is this residue exposed or buried?" | `pdb_structure.py` (SASA from PDB) |
| "Which candidates fit goal G for residue R?" | `curated/chemistry_notes.md` + `advise.py` |

## Known gaps / TODO

- [ ] 8 AAindex2 matrices + 4 AAindex3 potentials use non-standard layouts
      (see `parse_aaindex.py` warnings) — not needed for the core workflow.
- [ ] 15 AAindex1 indices skipped (irregular I blocks).
- [x] PDB-aware mode: `--pdb` + residue number → SS (PDB records + gmx dssp,
      conservative union) + auto-SASA + SS-propensity deltas + contact-potential
      dV + structure warnings (see `scripts/pdb_structure.py`).
- [ ] Add more design-goal rules (e.g. `binding-cation`, `pH-tuning`,
      `stability`).
- [ ] Validate the advisor's shortlists against known engineered mutants
      (literature test set).
