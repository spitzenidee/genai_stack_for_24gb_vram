# SOURCES — Full Attribution

Every source used to build this knowledge base, with authors, journals,
PMIDs, and URLs in full. Per-entry references for all 680 indices, matrices,
and contact potentials are in **`data/references_all.csv`** (columns:
`section, accession, description, authors, title, journal, pmid_refs`), and are
also embedded in `data/indices.json`, `data/matrices.json`,
`data/contact_potentials.json` (fields `refs`, `authors`, `title`, `journal`).

**Accuracy note:** all aaindex entry references below were taken verbatim from
the AAindex raw data (via `references_all.csv`), not from memory. Curated
values are attributed to verifiable standard references only.

## 1. AAindex database (primary data source)

**Database:** AAindex — Amino Acid Index Database, **Release 9.2 (February 2017)**
**Maintainer:** Shuichi Kawashima, Database Center for Life Science, RIKEN, Japan
(per `aaindex_raw/aaindex.doc`)

### URLs
| Resource | URL |
|---|---|
| Database home / entry browser | https://www.genome.jp/aaindex/ |
| FTP download directory | https://www.genome.jp/ftp/db/community/aaindex/ |
| File: `aaindex1` (551 KB, 2017-02-13) | https://www.genome.jp/ftp/db/community/aaindex/aaindex1 |
| File: `aaindex2` (231 KB, 2020-06-22) | https://www.genome.jp/ftp/db/community/aaindex/aaindex2 |
| File: `aaindex3` (80 KB, 2017-02-13) | https://www.genome.jp/ftp/db/community/aaindex/aaindex3 |
| File: `aaindex.doc` (format + references) | https://www.genome.jp/ftp/db/community/aaindex/aaindex.doc |
| File: `changelog` | https://www.genome.jp/ftp/db/community/aaindex/changelog |
| Original FTP (historical) | ftp://ftp.genome.ad.jp/db/genomenet/aaindex/ |

**Downloaded:** 2026 (this project), into `aaindex_raw/`.
**Content:** AAindex1 = 566 single-AA indices (551 parsed); AAindex2 = 94
20×20 mutation/similarity matrices (86 parsed); AAindex3 = 47 statistical
contact potentials (43 parsed).

### Primary literature for the database itself
(as listed in `aaindex_raw/aaindex.doc` and https://www.genome.jp/aaindex/)

1. **Nakai, K., Kidera, A., and Kanehisa, M.** (1988). Cluster analysis of
   amino acid indices for prediction of protein structure and function.
   *Protein Engineering* **2**(2), 93-100. PMID: 3244698.
   DOI: 10.1093/protein/2.2.93
2. **Tomii, K. and Kanehisa, M.** (1996). Analysis of amino acid indices and
   mutation matrices for sequence comparison and structure prediction of
   proteins. *Protein Engineering* **9**(1), 27-36. PMID: 9053899.
   DOI: 10.1093/protein/9.1.27
3. **Kawashima, S., Ogata, H., and Kanehisa, M.** (1999). AAindex: amino acid
   index database. *Nucleic Acids Research* **27**(2), 368-369. PMID: 9847231.
   DOI: 10.1093/nar/27.2.368 — free full text:
   https://pmc.ncbi.nlm.nih.gov/articles/PMC102411/
4. **Kawashima, S. and Kanehisa, M.** (2000). AAindex: amino acid index
   database. *Nucleic Acids Research* **28**(1), 374. PMID: 10592278.
   DOI: 10.1093/nar/28.1.374
5. **Kawashima, S., Pokarowski, P., Pokarowska, M., Kolinski, A., Katayama, T.,
   and Kanehisa, M.** (2008). AAindex: amino acid index database, progress
   report 2008. *Nucleic Acids Research* **36**(Database issue), D202-D205.
   PMID: 17998252. Publisher page:
   https://academic.oup.com/nar/article/36/suppl_1/D202/2508449

### Per-entry references (the 680 data entries)
Every parsed entry carries its own original publication. Extracted to
**`data/references_all.csv`** (680 rows: 551 AAindex1 + 86 AAindex2 +
43 AAindex3). The entries used by the advisor, with their exact original
references (verbatim from the AAindex data):

| Accession | Entry | Original reference (verbatim from AAindex) |
|---|---|---|
| HENS920102 | BLOSUM62 | Henikoff, S. and Henikoff, J.G. (1992). Amino acid substitution matrices from protein blocks. *Proc. Natl. Acad. Sci. USA* 89, 10915-10919. PMID: 1438297 |
| HENS920101 | BLOSUM45 | Henikoff, S. and Henikoff, J.G. (1992). *PNAS* 89, 10915-10919. PMID: 1438297 |
| HENS920104 | BLOSUM50 | Henikoff, S. and Henikoff, J.G. (1992). *PNAS* 89, 10915-10919. PMID: 1438297 |
| DAYM780301 | PAM250 | Dayhoff, M.O., Schwartz, R.M. and Orcutt, B.C. (1978). A model of evolutionary change in proteins. In *Atlas of Protein Sequence and Structure*, Natl. Biomed. Res. Found. |
| GRAR740104 | Grantham chemical distance | Grantham, R. (1974). Amino acid difference formula to help explain protein evolution. *Science* 185, 862-864. PMID: 4843792 |
| GRAR740101 | Grantham hydrophobicity | Grantham, R. (1974). *Science* 185, 862-864. PMID: 4843792 |
| GRAR740102 | Grantham polarity | Grantham, R. (1974). *Science* 185, 862-864. PMID: 4843792 |
| MCLA720101 | McLachlan chemical similarity | McLachlan, A.D. (1972). Repeating sequences and gene duplication in proteins. *J. Mol. Biol.* 64, 417-437. PMID: 5023183 |
| KOSJ950113 | Context matrix, exposed | Koshi, J.M. and Goldstein, R.A. (1995). Context-dependent optimal substitution matrices. *Protein Engineering* 8, 641-645. PMID: 8577693 |
| KOSJ950114 | Context matrix, buried | Koshi, J.M. and Goldstein, R.A. (1995). *Protein Engineering* 8, 641-645. PMID: 8577693 |
| MIYS930101 | Miyazawa-Jernigan stability | Miyazawa, S. and Jernigan, R.L. (1993). A new substitution matrix for protein sequence searches. *Protein Engineering* 6, 267-278. PMID: 8506261 |
| FAUJ880109 | H-bond donor counts | Fauchere, J.L., Charton, M., Kier, L.B. and Verli, H. (1988). Amino acid side chain parameters for correlation studies. *Int. J. Peptide Protein Res.* 32, 269-278. PMID: 3209351 |
| KLEP840101 | Net charge | Klein, P., Kanehisa, M. and DeLisi, C. (1984). Prediction of protein function from sequence properties. *Biochim. Biophys. Acta* 787, 221-226. PMID: 6547351 |
| KRIW790103 | Side-chain volume | Krigbaum, W.R. and Komoriya, A. (1979). Local interactions as a structure determinant for proteins. *Biochim. Biophys. Acta* 576, 204-228. PMID: 760806 |
| EISD840101 | Eisenberg hydrophobicity | Eisenberg, D. (1984). Three-dimensional structure of membrane and surface proteins. *Ann. Rev. Biochem.* 53, 595-623. PMID: 6383201 |
| WOEC730101 | Polar requirement | Woese, C.R. (1973). Evolution of genetic code. *Naturwiss.* 60, 447-459. PMID: 4588588 |
| CHOP780201 | Chou-Fasman **helix** propensity | Chou, P.Y. and Fasman, G.D. (1978). Prediction of the secondary structure of proteins from their sequence. *Adv. Enzymol. Relat. Areas Mol. Biol.* 47, 45-148. |
| CHOP780202 | Chou-Fasman **sheet** propensity | Chou, P.Y. and Fasman, G.D. (1978). *Adv. Enzymol. Relat. Areas Mol. Biol.* 47, 45-148. |
| CHOP780101 | Chou-Fasman **turn** propensity | Chou, P.Y. and Fasman, G.D. (1978). Empirical predictions of protein conformation. *Ann. Rev. Biochem.* 47, 251-276. |
| ONEK900102 | O'Neil-DeGrado **helix** propensity (ΔG, kcal/mol) | O'Neil, K.T. and DeGrado, W.F. (1990). A thermodynamic scale for the helix-forming tendencies of the amino acids. *Science* 250, 646-651. |
| MIYS990107 | Miyazawa-Jernigan **contact potential** (quasichemical, buried env) | Miyazawa, S. and Jernigan, R.L. (1999). Self-consistent estimation of inter-residue protein contact energies. *Proteins* 34, 49-68. PMID: 10336383 |

The last four are used by the **structure-aware advisor** (`advise.py --pdb`):
CHOP780201/202/101 give per-residue helix/sheet/turn propensity deltas, and
ONEK900102 gives the experimental helix-forming free energy (Pro is worst,
+3.0 kcal/mol) that backs the helix-breaker warnings. Secondary structure is
assigned CONSERVATIVELY from the PDB's HELIX/SHEET records AND `gmx dssp`
(a residue is helix/strand if either says so — the two sources genuinely
disagree, and neither is ground truth); SASA is computed by the Lee-Richards
(1971) dot-product method, and Cα neighbors (< 6 Å) are scored with the
MIYS990107 contact potential for a rough pairwise interaction estimate.

## 2. Curated gap-fill data (`data/curated/`)

Data NOT present in AAindex, added by this project. Per-field sources are
embedded in `data/curated/aa_chemistry.json` (`_source` keys). Summary:

### Side-chain pKa (`pka_sidechain`) — **fact-checked 2026-07**
Aqueous side-chain pKa values, each verified against a fetched source:
| Residue | pKa | Source |
|---|---|---|
| Asp | 3.9 | IMGT (below) |
| Glu | 4.2 | IMGT (below) |
| Cys | 8.33 | Wikipedia, Cysteine infobox (thiol pKa) |
| His | 6.0 | IMGT (below) |
| Lys | 10.5 | IMGT (below) |
| Arg | 12.5 | IMGT (below) |
| Tyr | ~10.0 | Wikipedia, Amino acid (phenolic hydroxyl "pKa = ~10") |

- **IMGT** — International ImMunoGeneTics Information System. "Charge, hydrogen
  donor and acceptor atoms, and polarity of the amino acid side chains." URL:
  https://www.imgt.org/IMGTeducation/Aide-memoire/_UK/aminoacids/charge/index.html
  (accessed 2026-07). Table 1 gives side-chain pK: Asp 3.9, Glu 4.2, Lys 10.5,
  Arg 12.5, His 6.0.
- **Wikipedia** — "Cysteine" (infobox: thiol pKa 8.33) and "Amino acid"
  (Tyr phenolic pKa ~10). URLs:
  https://en.wikipedia.org/wiki/Cysteine ,
  https://en.wikipedia.org/wiki/Amino_acid (accessed 2026-07).

**Caveat** — in proteins these values shift substantially (especially His, Cys,
Asp, Glu) depending on local environment; discussed in standard textbooks
(Stryer 2015; Lehninger 2017).

### H-bond donor & acceptor counts (`hbond_donors`, `hbond_acceptors`) — **fact-checked 2026-07**
Both are now **side-chain H-bond atom counts from IMGT Table 3** (same URL as
above) — a single, consistent, fetchable source. Replaces earlier memory-based
acceptor values that were inconsistent (e.g. Arg/Cys/Pro acceptors, His count).
- Donor atoms: R=3 (NE,NH1,NH2), N=1, Q=1, H=2, K=1, S=1, T=1, W=1, Y=1; others 0.
- Acceptor atoms: D=2, E=2, H=2, N=1, Q=1, S=1, T=1, Y=1; others 0 (protonated
  Arg/Lys counted as 0 acceptors).
- **Convention note:** counts are protonation-state dependent. The AAindex1 entry
  **FAUJ880109** (Fauchere et al. 1988; PMID 3209351) gives an alternative
  *capacity-based* donor count (R=4, K=2, ...); it is retained in `advise.py`
  as the reference field `hbond_donors_fauj`.

### Net side-chain charge (`partial_charge_sidechain`)
Consistent with attributed AAindex1 entry **KLEP840101** (Klein, Kanehisa &
DeLisi 1984; PMID 6547351; full reference above) and IMGT (5 charged side
chains at pH 7: D,E negative; K,R,H positive). His counted as 0 (≈10%
protonated at pH 7 per Wikipedia).

### Expert design rules (`data/curated/chemistry_notes.md`) — **fact-checked 2026-07**
Synthesis of standard protein-chemistry knowledge (guanidinium/salt-bridge
chemistry, candidate classes by design goal, matrix interpretation). Verified
against:
- **Harris, T.K. and Turner, G.J.** (2002). Structural basis of perturbed pKa
  values of catalytic groups in enzyme active sites. *IUBMB Life* 53(2),
  85-98. DOI: 10.1080/15216540211468. PMID: 12049200. — source for the
  general-acid / general-base / nucleophile / anion-binding **candidate
  classes** and for the **protein-pKa-shift** caveat (active-site Cys 9.1→3.5-7.5,
  His 7.5→10.3-12.1, Asp 3.9→>9). Accessed via the LSU Health Science Center
  Biochemistry course PDF.
- **Wikipedia** — "Arginine" (guanidinium, amphipathic side chain, H-bonding +
  salt bridges; guanidinium pKa 13.8 free), "Cysteine", "Amino acid".
  URLs: https://en.wikipedia.org/wiki/Arginine ,
  https://en.wikipedia.org/wiki/Cysteine ,
  https://en.wikipedia.org/wiki/Amino_acid (accessed 2026-07).
- **IMGT** — side-chain pKa (see above).
- Textbooks (Stryer 2015; Lehninger 2017) cited as general background only.

## 3. Tooling / code

- `scripts/parse_aaindex.py` — original work for this project (parses the
  AAindex raw format documented in `aaindex_raw/aaindex.doc`).
- `scripts/advise.py` — original work for this project (prototype advisor).
- No third-party Python packages required (stdlib only: `argparse`, `json`,
  `math`, `os`, `pathlib`, `re`, `shutil`, `subprocess`, `sys`, `tempfile`).

## 4. Provenance summary

| Artifact | Derived from |
|---|---|
| `data/indices.json` | `aaindex_raw/aaindex1` (AAindex 9.2) |
| `data/matrices.json` | `aaindex_raw/aaindex2` (AAindex 9.2) |
| `data/contact_potentials.json` | `aaindex_raw/aaindex3` (AAindex 9.2) |
| `data/references_all.csv` | the three JSON files above |
| `data/curated/aa_chemistry.json` | **Fact-checked 2026-07**: pKa from IMGT + Wikipedia (Cysteine, Amino acid); H-bond donor/acceptor atom counts from IMGT Table 3; charge consistent with AAindex KLEP840101. (Textbooks Stryer 2015 / Lehninger 2017 cited for the protein-pKa-shift caveat only.) |
| `data/curated/chemistry_notes.md` | **Fact-checked 2026-07**: candidate classes + pKa-shift caveat from Harris & Turner 2002 (IUBMB Life 53(2):85-98, PMID 12049200); chemical characterizations from Wikipedia (Arginine/Cysteine/Amino acid) + IMGT |
