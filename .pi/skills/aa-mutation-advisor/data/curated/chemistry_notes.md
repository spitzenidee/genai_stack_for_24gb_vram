# Expert Chemistry Notes — Amino Acid Substitution Design

Curated domain knowledge that complements the quantitative AAindex data.
The index data tells you *how much* a substitution changes each property;
these notes tell you *what that means functionally* and *which candidates
fit which design goal*.

**Fact-check status (2026-07):** The chemical characterizations below are
standard biochemistry, verified against Wikipedia (Arginine, Cysteine, Amino
acid) and IMGT. The candidate classes by catalytic/binding role are verified
against **Harris & Turner (2002), *IUBMB Life* 53(2):85-98 (PMID 12049200)**,
which documents the general-acid / general-base / nucleophile / anion-binding
roles of each residue in enzyme active sites. Full citations in
`SOURCES.md` (in this skill's directory).

## 1. Arginine chemistry (the "source" residue)

*Verified: Wikipedia "Arginine" (guanidinium group, amphipathic side chain,
H-bonding + salt bridges, guanidinium pKa 13.8 free / ~12.5 in proteins); IMGT
pKa 12.5.*

- **Guanidinium group**: planar, +1 charge at all physiological pH (pKa ~12.5),
  3 N-H donors, bidentate geometry. This makes Arg the strongest, most
  geometrically flexible cationic binder in proteins.
- **Signature interactions**:
  - Salt bridges / cation-π with carboxylates (Asp, Glu), phosphates (ATP,
    phospholipids, phosphorylated substrates), and aromatic rings (Phe, Tyr, Trp).
  - Bidentate H-bonds to carbonyls, phosphates, and nucleic-acid bases.
- **Consequence**: Arg at a binding site is usually a *specificity and affinity
  hotspot* — it binds anionic/dipolar partners strongly and directionally.
  Mutating it is a high-impact move.

## 2. Candidate classes for replacing Arg (by design goal)

*Candidate roles verified against Harris & Turner 2002 (IUBMB Life 53(2):85-98,
PMID 12049200): His = general acid AND base (serine-protease triad); Ser and
Cys = nucleophiles; Asp = general acid; Glu and Tyr = general base; Arg =
phosphate/carboxylate binder (guanidinium); Lys = Schiff-base / nucleophile.*

### Goal A: Keep the positive charge, change the binding character
| Candidate | What changes | When to use |
|---|---|---|
| **Lys** | Keeps +1; loses bidentate guanidinium → single-directional, weaker salt bridge; side chain 5 Å³ smaller, more flexible | Sharpen directionality; reduce binding to off-target anions that only fit the bidentate geometry. Classic first choice. |
| **His** | +1 only below pH ~6; at pH 7 mostly neutral with H-bond donor/acceptor | Introduce pH-dependent behavior; "switchable" residue. Use when you want activity to be pH-regulated. |
| **Gln** | Neutral polar; keeps 2 H-bond donors, loses charge | Keep H-bonding, remove electrostatics. Good when the charge causes non-specific binding but the H-bond pattern is useful. |

### Goal B: Remove the interaction (reduce off-target / increase selectivity)
| Candidate | What changes | When to use |
|---|---|---|
| **Ala** | Removes side chain almost entirely (105 → 27.5 Å³); no charge, no H-bonding | The standard "knock-out" of an interaction. If Arg mediates off-target binding, R→A is the cleanest test. |
| **Gly** | Smallest; adds backbone flexibility | When you also want to loosen local structure. |
| **Ser/Thr** | Small polar, keeps one H-bond | When you want to keep a weak polar contact without charge. |

### Goal C: Preserve function, trade affinity for specificity
- **Lys** (see A) is the workhorse: keeps the electrostatic "on" state,
  breaks the bidentate geometry → often *lower affinity, higher specificity*.
- **His** adds a tunable dimension (pH, metal coordination, H-bond acceptor).
- **Gln** when the partner is a H-bond acceptor network, not an anion.

### Goal D: Arg is catalytic
- Rarely safe to mutate. If the mechanism uses the guanidinium
  (e.g., transition-state stabilization, proton relay), only Lys/His are
  plausible, and activity will likely drop.
- Check the mechanism (e.g., BRENDA, literature) before proposing anything.

## 3. Reading the quantitative data (AAindex)

- **BLOSUM/PAM scores** (aaindex2): measure *evolutionary* substitution
  frequency at conserved positions — NOT functional design suitability.
  Arg→Lys = -1 (BLOSUM62) means "disfavored by evolution", not "bad design".
  Use these to gauge how *conservative* a swap is, not how *good* it is.
- **Grantham chemical distance** (GRAR740104): composite of composition,
  polarity, hydrophobicity. Lower = more chemically similar.
  Arg's nearest: P(27), T(58), G(60), V(64), M(84), **H(86)**, **Q(91)**, **K(106)**.
- **McLachlan similarity** (MCLA720101): chemical similarity; Arg nearest: G, P, S, T.
- **Context-dependent matrices** (KOSJ950101-115): pick by residue environment.
  Active-site residues are usually *exposed* → use KOSJ950113 (exposed) or
  the structure-specific ones (KOSJ950101-104).
- **Miyazawa-Jernigan stability matrix** (MIYS930101): rough stability impact
  of the swap in a buried environment.
- **Property deltas** (aaindex1): always report Δcharge, ΔHBD, Δvolume,
  Δpolarity, Δhydrophobicity for each candidate — this is the transparent
  basis for the ranking.

## 4. Design workflow (what the agent should do)

1. **Clarify the role** of the target residue:
   - Binding (which partner? anion? H-bond network? cation-π?)
   - Catalytic (which step?)
   - Structural/stabilizing
   - Unknown → ask the user, or infer from structure (contacts < 4 Å)
2. **Clarify the goal**: increase specificity? reduce off-target?
   tune pH response? keep affinity?
3. **Compute the property-delta profile** for each of the 19 candidates
   (scripts/advise.py does this).
4. **Rank with the right matrix** for the context (exposed vs buried).
5. **Apply the role-based rules** above to shortlist 2-4 candidates
   with explicit rationale.
6. **Flag caveats**: pKa shifts in the protein environment, possible
   destabilization (check Δvolume, Δburied surface), and the fact that
   BLOSUM/PAM ≠ design suitability.
7. **Suggest validation**: MD of WT vs mutant (GROMACS), check the
   interaction of interest is preserved/removed as intended;
   binding free energy (MM/PBSA or alchemical) if needed.

## 5. Known limitations

- AAindex is a *property catalog*, not a design oracle. The indices
  quantify; the rules above decide.
- No pKa or H-bond-acceptor data in AAindex → curated/aa_chemistry.json fills this.
- Protein pKa values shift **dramatically** from solution values (e.g. active-site
  Cys 9.1→3.5-7.5, His 7.5→10.3-12.1, Asp 3.9→>9); treat solution pKa as a guide
  only. See Harris & Turner 2002 (PMID 12049200).
- Contact potentials (aaindex3) give rough pair-energy estimates, not
  reliable ΔΔG for a specific site.
