---
name: aa-mutation-advisor
description: >
  Expert advisor for protein / amino-acid chemistry and site-directed
  mutagenesis design. Use when the user asks which amino acid to substitute
  for a residue (e.g. "I want to mutate this active-site arginine to increase
  specificity — what are the prime candidates?"), about AA physicochemical
  properties, active-site engineering, specificity/affinity trade-offs, or
  when planning GROMACS validation of a designed mutant. Grounds every
  recommendation in the quantitative AAindex knowledge base plus curated
  chemistry notes.
---

# aa-mutation-advisor

Advises on amino-acid substitutions with expert protein-chemistry reasoning,
grounded in a quantitative knowledge base (AAindex 1-3 + curated gap-fill).

The core principle: **AAindex quantifies; the chemistry notes decide.**
The index data tells you *how much* a substitution changes each property;
the curated rules tell you *what that means functionally* and *which
candidates fit which design goal*. Never present a raw matrix score as a
design recommendation — always interpret it through the role-based rules.

## Knowledge base (bundled with this skill)

All assets are bundled in this skill's own directory (the directory
containing this SKILL.md — call it `<skill_dir>`). All paths below are
relative to `<skill_dir>`. Verify with `ls` before first use.

| Path | Contents |
|---|---|
| `SOURCES.md` | **Full attribution**: all authors, journals, PMIDs, URLs (database + per-entry + curated) |
| `data/references_all.csv` | 680 per-entry references (accession, authors, title, journal, PMID) |
| `data/indices.json` | 551 AAindex1 single-AA property indices (20 values each, AA order `ARNDCQEGHILKMFPSTWYV`) |
| `data/matrices.json` | 86 AAindex2 20×20 mutation/similarity matrices (BLOSUM, PAM, Grantham, McLachlan, KOSJ context, MJ stability) |
| `data/contact_potentials.json` | 43 AAindex3 statistical contact potentials |
| `data/curated/aa_chemistry.json` | Gap-fill NOT in AAindex: side-chain pKa, H-bond donor/acceptor counts, partial charges |
| `data/curated/chemistry_notes.md` | Expert rules: Arg chemistry, candidate classes by design goal, how to read each matrix, the design workflow, limitations |
| `scripts/advise.py` | Prototype engine: property-delta table + matrix ranking + role-based shortlist + SS-aware warnings |
| `scripts/advise_structure.sh` | **Preferred structure-aware entry point**: host bash wrapper (bash+coreutils only) that runs `gmx dssp` (transient gromacs container) + `advise.py` (transient `md-prep` container). No `make gromacs`/build/GPU/mode-switch. |
| `scripts/pdb_structure.py` | PDB parser + SS (PDB records + gmx dssp, conservative union) + SASA + Cα neighbors (stdlib only) |
| `scripts/parse_aaindex.py` | Re-parse raw AAindex files into the JSON above |
| `aaindex_raw/` | Raw downloads (aaindex1/2/3, .doc, changelog) |

## Workflow

When the user asks a substitution question:

1. **Clarify the role** of the target residue (ask if not given):
   - Binding (which partner? anion? H-bond network? cation-π?)
   - Catalytic (which step?)
   - Structural / stabilizing
   - Unknown → infer from structure if a PDB is available (contacts < 4 Å),
     otherwise ask the user.
2. **Clarify the goal**: increase specificity? reduce off-target binding?
   tune pH response? preserve affinity?
3. **Run the advisor** for the quantitative backbone:
   ```
   # structure-aware (PREFERRED when you have a PDB) — one command, no build/GPU/mode-switch:
   <skill_dir>/scripts/advise_structure.sh <structure.pdb> <NUMBER> <goal>
   # no PDB: pass the AA and a manual context / structure
   python3 <skill_dir>/scripts/advise.py --residue <AA> --goal <goal> --context <exposed|buried> [--structure <helix|sheet|turn|coil>]
   ```
   `advise_structure.sh` is a host bash wrapper (standard bash + coreutils only)
   that runs two transient `docker run --rm` containers — `gmx dssp` on the
   local GROMACS image (CPU-only, no GPU) and `advise.py` in the `md-prep`
   sidecar — then cleans up its temp dir. It never triggers `make gromacs` /
   a work-mode switch / a `docker build`/pull, and never disturbs running
   services. `--goal` choices: `specificity`, `binding-anion`,
   `remove-interaction`, `catalytic`.

   **Secondary structure is assigned CONSERVATIVELY**: the PDB's HELIX/SHEET
   records and the DSSP `.dat` are merged, and a residue is treated as
   helix/strand if **EITHER** source says so. (The two sources genuinely
   disagree — e.g. lysozyme's 80–98 helices differ between them — and neither
   is ground truth; over-warning is cheaper than missing a helix/strand
   breaker.) The output prints the per-residue basis, e.g.
   `SS basis: PDB records=H, DSSP=T (conservative union -> H)`. The
   **solvent context is auto-computed from SASA** (replaces `--context`).
   The advisor then adds SS-propensity deltas, a **contact-potential ΔV**
   (rough pair-energy with Cα neighbors, MIYS990107), and **structure warnings**
   (e.g. helix → Pro/Gly, strand → Gly). Without a PDB, `--context` is manual
   (active-site residues are usually `exposed`; `buried` for core) and
   `--structure` optionally forces the SS context.
4. **Interpret through the chemistry notes**
   (`data/curated/chemistry_notes.md`, section 2). The advisor prints a
   role-based shortlist; confirm each candidate against the notes and the
   property-delta table.
5. **Present the answer**:
   - 2-4 ranked candidates, each with an explicit rationale tied to the
     role + goal (e.g. "Lys keeps the +1 charge but loses the bidentate
     guanidinium → more directional, weaker off-target binding").
   - The property-delta table (Δcharge, ΔHBD, Δvolume, Δpolarity,
     Δhydrophobicity) so the user can see the basis.
   - Matrix scores with the correct interpretation:
     **BLOSUM/PAM = evolutionary frequency, NOT design suitability.**
     Grantham = chemical distance. KOSJ context = environment-specific
     similarity.
6. **Respect the structure warnings**: if the advisor flags a candidate as a
   helix/strand breaker (Pro/Gly in a helix, Gly in a strand), treat that as a
   hard constraint — those substitutions will likely disrupt the local
   structure, regardless of the property-delta score.
7. **Flag caveats** (chemistry_notes.md section 5): protein pKa shifts from
   solution values; possible destabilization (check Δvolume / buried
   surface); contact potentials are rough, not a ΔΔG.
8. **Suggest GROMACS validation** (hand off to the `gromacs-sim` skill):
   MD of WT vs mutant, verify the interaction of interest is
   preserved/removed as intended; binding free energy (MM/PBSA or
   alchemical) if the user wants a number.

## Key facts to keep in mind

- **Arg** = guanidinium, +1 at all physiological pH (pKa ~12.5), 3 N-H
  donors, bidentate. The strongest, most geometrically flexible cationic
  binder. Mutating it is high-impact.
- **Lys** = +1, single-directional, weaker salt bridge. The workhorse
  "keep charge, change character" swap.
- **His** = pH-switchable (pKa ~6.0), adds an H-bond acceptor. The
  "tunable" residue.
- **Gln** = neutral polar, keeps 2 H-bond donors, loses charge.
- **Ala** = cleanest interaction knock-out (105 → 27.5 Å³).
- BLOSUM62 Arg row ranking (evolutionary): K > Q > H=E > N=S > A=D=T > ...
  This is *not* the design ranking — it is the conservation ranking.

## Limitations

- This is a design *advisor*, not an oracle. Final calls need structural
  context (PDB contacts, mechanism) and experimental/MD validation.
- AAindex has no pKa or H-bond-acceptor data → the curated file fills that.
- 86/94 AAindex2 matrices and 43/47 AAindex3 potentials parse cleanly; the
  rest use non-standard layouts (see `parse_aaindex.py` warnings).
