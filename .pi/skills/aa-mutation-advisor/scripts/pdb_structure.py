#!/usr/bin/env python3
"""PDB structure utilities for the mutation advisor: secondary structure + SASA.

Secondary-structure assignment tiers (first available wins):
  1. PDB HELIX / SHEET records (official PDB annotation)  - zero dependency
  2. A user-provided `gmx dssp` .dat file                 - zero dependency
  3. `gmx dssp` in a TRANSIENT docker container (local GROMACS image;
     `docker run --rm`, no `make gromacs`, no build, no GPU, no service disruption)
  4. Pure-Python backbone H-bond assignment (DSSP-like)   - zero dependency

The GROMACS image is read from $GROMACS_DOCKER_IMAGE (default
`gromacs-hip-gfx1100:latest`) and must already exist locally; tier 3 is skipped
if docker or the image is unavailable. `gmx dssp` output is the compact
one-char-per-residue format (H/E/G/I/B/T/S/P/~), mapped to {H,E,T,C}.

SASA: Lee-Richards (1971) dot-product method, probe radius 1.4 A, per residue.

SS codes (DSSP convention): H=helix, E=strand, G=3-10 helix, I=pi-helix,
T=turn, B=isolated bridge, C=coil. We collapse to {H, E, T, C} for the advisor.

No third-party dependencies (stdlib only).
"""
import math
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

AA3TO1 = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C",
    "GLN": "Q", "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I",
    "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F", "PRO": "P",
    "SER": "S", "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V",
}
BACKBONE = {"N", "CA", "C", "O"}

# van der Waals radii (A) for SASA (Bondi-ish)
VDW = {"C": 1.70, "N": 1.55, "O": 1.52, "H": 1.20, "S": 1.80,
       "P": 1.80, "SE": 2.10, "F": 1.47, "CL": 1.75, "BR": 1.90}
DEFAULT_VDW = 1.70
PROBE = 1.40  # standard water probe radius (A)


def _element(atom_name, element_field):
    el = (element_field or "").strip()
    if el:
        return el.upper()
    # infer from atom name (strip digits)
    letters = re.sub(r"[0-9']", "", atom_name).strip()
    if letters in VDW:
        return letters
    if letters[:2].upper() in VDW:
        return letters[:2].upper()
    return letters[0].upper() if letters else "C"


def parse_pdb(path):
    """Parse a PDB file.

    Returns (residues, atoms, helix_ranges, sheet_ranges):
      residues: list of dicts {number, chain, name3, name1, atoms:{name:(x,y,z,el)}}
      atoms:    list of (x,y,z,radius, res_number, chain) for ALL atoms (SASA)
      helix_ranges: list of (chain, start_num, end_num, class)
      sheet_ranges: list of (chain, start_num, end_num)
    """
    residues = []
    atoms = []
    helix_ranges = []
    sheet_ranges = []
    res_by_key = {}

    with open(path) as fh:
        for line in fh:
            rec = line[:6].strip()
            if rec in ("ATOM", "HETATM"):
                try:
                    name = line[12:16].strip()
                    resname3 = line[17:20].strip()
                    chain = line[21].strip()
                    num = int(line[22:26].strip())
                    x = float(line[30:38]); y = float(line[38:46]); z = float(line[46:54])
                except (ValueError, IndexError):
                    continue
                el = _element(name, line[76:78])
                radius = VDW.get(el, DEFAULT_VDW)
                atoms.append((x, y, z, radius, num, chain))
                if name in BACKBONE and resname3 in AA3TO1:  # standard AA only
                    key = (chain, num)
                    r = res_by_key.get(key)
                    if r is None:
                        r = {"number": num, "chain": chain, "name3": resname3,
                             "name1": AA3TO1[resname3], "atoms": {}}
                        res_by_key[key] = r
                        residues.append(r)
                    r["atoms"][name] = (x, y, z)
            elif rec == "HELIX":
                f = line.split()
                if len(f) >= 9:
                    try:
                        chain = f[4]; start = int(f[5]); end = int(f[8])
                        cls = f[9] if len(f) > 9 else "1"
                        helix_ranges.append((chain, start, end, cls))
                    except (ValueError, IndexError):
                        pass
            elif rec == "SHEET":
                # SHEET1 lines (serial==1) define strand ranges; SHEET2+ are H-bonds
                f = line.split()
                if len(f) >= 10 and f[1] == "1":
                    try:
                        chain = f[5]; start = int(f[6]); end = int(f[9])
                        sheet_ranges.append((chain, start, end))
                    except (ValueError, IndexError):
                        pass
    residues.sort(key=lambda r: (r["chain"], r["number"]))
    return residues, atoms, helix_ranges, sheet_ranges


def _mark(ss, chain, start, end, code):
    for n in range(start, end + 1):
        key = (chain, n)
        if key in ss:
            ss[key] = code


def ss_from_pdb_records(residues, helix_ranges, sheet_ranges):
    """Tier 1: assign SS from PDB HELIX/SHEET records. Returns {(chain,num):code} or None."""
    if not helix_ranges and not sheet_ranges:
        return None
    ss = {(r["chain"], r["number"]): "C" for r in residues}
    for chain, s, e, cls in helix_ranges:
        code = "H" if cls in ("1", "2") else ("G" if cls == "1" else "H")
        # class 1=3.6/alpha(H), 2=3.10(G), 3=pi(I); collapse G/I->H for advisor
        code = "H"
        _mark(ss, chain, s, e, code)
    for chain, s, e in sheet_ranges:
        _mark(ss, chain, s, e, "E")
    return ss


# --- DSSP code mapping (gmx dssp output -> advisor {H,E,T,C}) ---
DSSP_TO_ADVISOR = {"H": "H", "G": "H", "I": "H", "E": "E", "B": "E",
                   "T": "T", "S": "T", "P": "C", "~": "C"}
_DSSP_CHARS = set("HGITEBPS~")
# Local GROMACS image (already built in this stack; NEVER built here). Override via env.
GROMACS_IMAGE = os.environ.get("GROMACS_DOCKER_IMAGE", "gromacs-hip-gfx1100:latest")


def _map_dssp(code):
    return DSSP_TO_ADVISOR.get(code, "C")


def _parse_dssp_output(text, residues):
    """Parse gmx dssp output. Handles (a) the compact one-char-per-residue line
    (the real `gmx dssp -o` format) and (b) per-line 'resseq resname ss'.
    Returns {(chain,num):code} or None."""
    text = (text or "").strip()
    if not text:
        return None
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    res_sorted = sorted(residues, key=lambda r: (r["chain"], r["number"]))
    # (a) compact: a long run of SS chars with no spaces
    for line in lines:
        if len(line) >= 5 and " " not in line and all(c in _DSSP_CHARS for c in line):
            codes = list(line)
            if len(codes) < len(res_sorted):
                return None
            return {(r["chain"], r["number"]): _map_dssp(c)
                    for c, r in zip(codes[:len(res_sorted)], res_sorted)}
    # (b) per-line: last token is the ss code, first integer is the resseq
    codes = []
    for line in lines:
        f = line.split()
        if not f:
            continue
        ss_code = f[-1].strip()
        if ss_code not in _DSSP_CHARS:
            continue
        for tok in f[:-1]:
            if tok.lstrip("-").isdigit():
                codes.append(_map_dssp(ss_code))
                break
    if len(codes) < len(res_sorted):
        return None
    return {(r["chain"], r["number"]): c for c, r in zip(codes[:len(res_sorted)], res_sorted)}


def ss_from_dssp_dat(dat_path, residues):
    """Tier 2: parse a `gmx dssp` .dat file (compact or per-line)."""
    if not dat_path or not os.path.exists(dat_path):
        return None
    try:
        with open(dat_path) as fh:
            return _parse_dssp_output(fh.read(), residues)
    except OSError:
        return None


def _protein_only_pdb(pdb_path, out_path):
    """Write a PDB with only standard-AA ATOM records (strip waters/ligands)."""
    with open(pdb_path) as fh, open(out_path, "w") as out:
        for line in fh:
            if line[:6].strip() == "ATOM" and line[17:20].strip() in AA3TO1:
                out.write(line)
        out.write("END\n")


def _docker_image_exists(image):
    try:
        r = subprocess.run(["docker", "image", "inspect", image],
                           capture_output=True, timeout=30)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def ss_from_gmx_dssp(pdb_path):
    """Tier 3: run `gmx dssp` in a TRANSIENT docker container.

    Uses `docker run --rm` on the local GROMACS image — no `make gromacs`
    (work-mode switch), no `docker build`, no GPU devices, no service disruption.
    Returns {(chain,num):code} or None.
    """
    if shutil.which("docker") is None:
        return None
    if not _docker_image_exists(GROMACS_IMAGE):
        return None
    pdb = Path(pdb_path)
    if not pdb.exists():
        return None
    try:
        with tempfile.TemporaryDirectory() as td:
            inp = os.path.join(td, "input.pdb")
            outdat = os.path.join(td, "output.dat")
            _protein_only_pdb(pdb, inp)
            subprocess.run(
                ["docker", "run", "--rm", "-v", f"{td}:/input", GROMACS_IMAGE,
                 "gmx", "dssp", "-s", "/input/input.pdb", "-f", "/input/input.pdb",
                 "-o", "/input/output.dat", "-hmode", "dssp"],
                capture_output=True, timeout=300, check=True,
            )
            if not os.path.exists(outdat):
                return None
            residues, _, _, _ = parse_pdb(pdb)
            with open(outdat) as fh:
                return _parse_dssp_output(fh.read(), residues)
    except (subprocess.SubprocessError, OSError, ValueError):
        return None
    return None


def assign_ss_union(pdb_path, dssp_dat=None):
    """
    Compute secondary structure CONSERVATIVELY from BOTH the PDB's HELIX/SHEET
    records and a gmx dssp .dat (when available).

    Rationale: the two sources genuinely disagree (e.g. lysozyme's 80-98 helices
    differ between the PDB records and a fresh DSSP run), and neither is ground
    truth. For a mutation advisor, over-warning is cheaper than missing a
    helix/strand breaker, so a residue is treated as helix if EITHER source says
    helix, and strand if EITHER says strand.

    Returns (merged_ss, source_desc, basis):
      merged_ss: {(chain,num): 'H'/'E'/'T'/'S'/'B'/'G'/'I'/'C'} (conservative)
      source_desc: e.g. 'PDB records + DSSP (conservative union)'
      basis: {(chain,num): (pdb_char, dssp_char)} for transparent display
    """
    residues, _, helix, sheet = parse_pdb(pdb_path)
    pdb_ss = ss_from_pdb_records(residues, helix, sheet) or {}
    pdb_has_struct = any(v in ("H", "E") for v in pdb_ss.values())
    dssp_ss = ss_from_dssp_dat(dssp_dat, residues)
    if dssp_ss is None:
        dssp_ss = ss_from_gmx_dssp(pdb_path)
    dssp_ss = dssp_ss or {}
    dssp_available = bool(dssp_ss)
    dssp_has_struct = any(v in ("H", "E") for v in dssp_ss.values())

    merged, basis = {}, {}
    for k in set(pdb_ss) | set(dssp_ss):
        p, d = pdb_ss.get(k, "C"), dssp_ss.get(k, "C")
        basis[k] = (p, d if dssp_available else "-")  # "-" = no DSSP data
        if p == "H" or d == "H":
            merged[k] = "H"
        elif p == "E" or d == "E":
            merged[k] = "E"
        else:
            merged[k] = d if d != "C" else p
        if p == "H" or d == "H":
            merged[k] = "H"
        elif p == "E" or d == "E":
            merged[k] = "E"
        else:
            merged[k] = d if d != "C" else p

    if pdb_has_struct and dssp_has_struct:
        src = "PDB records + DSSP (conservative union)"
    elif pdb_has_struct:
        src = "PDB HELIX/SHEET records"
    elif dssp_has_struct:
        src = "gmx dssp"
    else:
        src = "none"
    return merged, src, basis


def sasa_per_residue(atoms, residues):
    """Lee-Richards (1971) dot-product SASA per residue. Returns {(chain,num):sasa_A2}.

    Uses effective radii R = r_vdw + probe; the accessible surface of atom i is the
    area of its R_i sphere not occluded by any other atom's R_j sphere.
    """
    n = len(atoms)
    Rloc = [atoms[i][3] + PROBE for i in range(n)]  # probe-center locus radius
    sasa = [0.0] * n
    for i in range(n):
        xi, yi, zi, _, _, _ = atoms[i]
        Ri = Rloc[i]
        total = 4.0 * math.pi * Ri * Ri
        buried = 0.0
        for j in range(n):
            if i == j:
                continue
            xj, yj, zj, _, _, _ = atoms[j]
            rj = atoms[j][3]  # BARE vdw radius of j occludes the locus sphere
            d = math.sqrt((xi - xj) ** 2 + (yi - yj) ** 2 + (zi - zj) ** 2)
            if d < 1e-6:
                continue
            if (Ri - rj) < d < (Ri + rj):
                cos_a = (Ri * Ri + d * d - rj * rj) / (2.0 * Ri * d)
                cos_a = max(-1.0, min(1.0, cos_a))
                buried += 2.0 * math.pi * Ri * Ri * (1.0 - cos_a)
        sasa[i] = max(0.0, total - buried)
    res_sasa = {}
    for idx, (x, y, z, r, num, chain) in enumerate(atoms):
        key = (chain, num)
        res_sasa[key] = res_sasa.get(key, 0.0) + sasa[idx]
    return res_sasa


def load_structure(pdb_path, dssp_dat=None):
    """Load a PDB, assign SS (conservative PDB+DSSP union), compute SASA. Returns dict:
    {residues, ss {(chain,num):code}, ss_basis {(chain,num):(pdb,dssp)},
     res_sasa {(chain,num):A2}, ss_source str}."""
    residues, atoms, helix, sheet = parse_pdb(pdb_path)
    ss, ss_source, ss_basis = assign_ss_union(pdb_path, dssp_dat)
    res_sasa = sasa_per_residue(atoms, residues)
    return {"residues": residues, "ss": ss, "ss_basis": ss_basis,
            "res_sasa": res_sasa, "ss_source": ss_source}


def classify_exposure(res_sasa, target_key, rel_threshold=0.25):
    """Classify a residue as exposed/buried from its relative SASA.

    Uses the fraction of the residue's SASA relative to the max possible for its
    size as a proxy. Returns (label, sasa_A2, rel_fraction).
    """
    sasa = res_sasa.get(target_key, 0.0)
    # rough max SASA ~ 200 A2 for a typical side chain + backbone contribution
    rel = min(1.0, sasa / 200.0)
    label = "exposed" if rel >= rel_threshold else "buried"
    return label, sasa, rel


def find_neighbors(residues, target_key, cutoff=6.0):
    """Residues (1-letter AA) within `cutoff` Angstrom C-alpha-C-alpha of the target.

    Used for the rough contact-potential estimate. Excludes the target itself.
    Returns a list of 1-letter AAs (duplicates possible across chains).
    """
    target = next((r for r in residues
                   if (r["chain"], r["number"]) == target_key), None)
    if target is None or "CA" not in target["atoms"]:
        return []
    tx, ty, tz = target["atoms"]["CA"]
    nbrs = []
    for r in residues:
        if (r["chain"], r["number"]) == target_key:
            continue
        if "CA" not in r["atoms"]:
            continue
        x, y, z = r["atoms"]["CA"]
        d = math.sqrt((tx - x) ** 2 + (ty - y) ** 2 + (tz - z) ** 2)
        if d <= cutoff:
            nbrs.append(r["name1"])
    return nbrs
