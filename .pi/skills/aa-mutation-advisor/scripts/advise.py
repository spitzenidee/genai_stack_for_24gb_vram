#!/usr/bin/env python3
"""AA mutation advisor prototype.

Computes, for a residue to be mutated, a property-delta profile and matrix-based
ranking of all 19 candidate substitutions, then applies role-based design
rules to shortlist candidates.

Usage:
  python3 advise.py --residue R --goal specificity [--context exposed]
  python3 advise.py --residue R --goal binding-anion

Data: ../data/indices.json, ../data/matrices.json, ../data/curated/aa_chemistry.json
"""
import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pdb_structure as ps

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
AA = "ARNDCQEGHILKMFPSTWYV"
AA3 = {"A": "Ala", "R": "Arg", "N": "Asn", "D": "Asp", "C": "Cys",
       "Q": "Gln", "E": "Glu", "G": "Gly", "H": "His", "I": "Ile",
       "L": "Leu", "K": "Lys", "M": "Met", "F": "Phe", "P": "Pro",
       "S": "Ser", "T": "Thr", "W": "Trp", "Y": "Tyr", "V": "Val"}

# Property indices from aaindex1 (acc -> name)
PROP_INDICES = {
    "KLEP840101": "charge",
    "FAUJ880109": "hbond_donors_fauj",  # capacity-based donor count (reference only)
    "KRIW790103": "volume",
    "GRAR740102": "polarity",
    "EISD840101": "hydrophobicity",
    "GRAR740101": "hydrophobicity_grantham",
    "WOEC730101": "polar_requirement",
}

# Matrix acc -> (name, higher_is_more_similar)
MATRIX_ACCS = {
    "HENS920102": ("BLOSUM62", True),
    "HENS920101": ("BLOSUM45", True),
    "DAYM780301": ("PAM250", True),
    "GRAR740104": ("Grantham_distance", False),
    "MCLA720101": ("McLachlan_sim", True),
    "KOSJ950113": ("context_exposed", True),
    "KOSJ950114": ("context_buried", True),
    "MIYS930101": ("MJ_stability", True),
}


def load():
    indices = {e["acc"]: e for e in json.loads((DATA / "indices.json").read_text())}
    matrices = {e["acc"]: e for e in json.loads((DATA / "matrices.json").read_text())}
    contacts = {e["acc"]: e for e in json.loads((DATA / "contact_potentials.json").read_text())}
    chem = json.loads((DATA / "curated" / "aa_chemistry.json").read_text())
    return indices, matrices, contacts, chem


# --- secondary-structure propensity (aaindex1) ---
SS_NAMES = {"H": "alpha-helix", "E": "beta-strand", "T": "turn", "C": "coil",
            "G": "3-10 helix", "I": "pi-helix", "B": "bridge"}
PROP_ACCS = {"helix": "CHOP780201", "sheet": "CHOP780202", "turn": "CHOP780101"}
HELIX_DDG_ACC = "ONEK900102"  # O'Neil-DeGrado experimental helix propensity (kcal/mol)

# Contact potential (aaindex3): rough pairwise interaction energy with neighbors.
# MIYS990107 = Miyazawa-Jernigan 1999 quasichemical (average buried environment).
CONTACT_ACC = "MIYS990107"
CONTACT_CUTOFF = 6.0  # Angstrom, C-alpha-C-alpha neighbor cutoff


def contact_potential_deltas(residue, neighbors, contact_matrix):
    """Per-candidate change in contact-potential energy with the residue's neighbors.

    dV[cand] = sum over neighbors n of (V[cand, n] - V[residue, n]).
    Negative dV = the candidate interacts more favorably with the neighbors.
    Returns {cand: dV}.
    """
    ti = AA.index(residue)
    out = {}
    for cand in AA:
        if cand == residue:
            continue
        ci = AA.index(cand)
        out[cand] = sum(contact_matrix[ci][AA.index(n)] - contact_matrix[ti][AA.index(n)]
                        for n in neighbors)
    return out


def load_propensities(indices):
    """Load SS propensity scales. Returns {name: {aa1: value}}."""
    out = {}
    for name, acc in PROP_ACCS.items():
        e = indices.get(acc)
        if e:
            out[name] = {aa: e["values"][AA.index(aa)] for aa in AA}
    e = indices.get(HELIX_DDG_ACC)
    if e:
        out["helix_ddg"] = {aa: e["values"][AA.index(aa)] for aa in AA}
    return out


def resolve_target(args, struct):
    """Resolve --residue to (aa1, info). With a PDB, a NUMBER selects that residue
    (AA/SS/SASA read from the structure); a 1/3-letter code selects the AA."""
    res = args.residue.upper()
    info = {}
    if struct is not None and res.isdigit():
        num = int(res)
        matches = [r for r in struct["residues"] if r["number"] == num]
        if not matches:
            sys.exit(f"residue {num} not found in PDB")
        r = matches[0]
        key = (r["chain"], r["number"])
        info = {"number": r["number"], "resname": r["name3"], "chain": r["chain"],
                "ss": struct["ss"].get(key, "C"),
                "ss_basis": struct.get("ss_basis", {}).get(key), "key": key,
                "sasa": struct["res_sasa"].get(key)}
        return r["name1"], info
    if len(res) == 3:
        for a, n3 in AA3.items():
            if n3.upper() == res:
                return a, info
        sys.exit(f"unknown 3-letter residue: {res}")
    return res, info


def anti_pattern_warnings(ss_code, cand, drow):
    """Warnings for a candidate substitution in a given secondary-structure context."""
    warns = []
    if ss_code == "H":
        if cand == "P":
            ddg = drow.get("helix_ddg_target")
            msg = "Proline is a strong helix-breaker (no N-H for H-bonding; rigid ring)"
            if ddg is not None:
                msg += f"; O'Neil-DeGrado helix dG={ddg:+.1f} kcal/mol (worst)"
            warns.append(msg)
        elif cand == "G":
            warns.append("Glycine is a helix-breaker (high conformational entropy; no side chain)")
        d = drow.get("d_helix")
        if d is not None and d < -0.5:
            warns.append(f"Chou-Fasman helix propensity drops {d:+.2f}")
    elif ss_code == "E":
        if cand == "G":
            warns.append("Glycine is a beta-strand breaker (too flexible; no side-chain H-bond)")
        d = drow.get("d_sheet")
        if d is not None and d < -0.5:
            warns.append(f"Chou-Fasman sheet propensity drops {d:+.2f}")
    return warns


def build_profiles(indices, chem):
    """Per-AA property vectors from aaindex1 + curated gap-fill."""
    props = {}
    for aa in AA:
        p = {}
        for acc, name in PROP_INDICES.items():
            e = indices.get(acc)
            p[name] = e["values"][AA.index(aa)] if e else None
        p["pka"] = chem["pka_sidechain"].get(aa)
        # H-bond donor/acceptor ATOM counts from IMGT (fact-checked, consistent convention)
        p["hbond_donors"] = chem["hbond_donors"][aa]
        p["hbond_acceptors"] = chem["hbond_acceptors"][aa]
        p["charge_curated"] = chem["partial_charge_sidechain"][aa]
        props[aa] = p
    return props


def delta_table(target, props, prop=None):
    """Property deltas for all 19 candidates vs target (+ SS propensity if prop given)."""
    t = props[target]
    rows = []
    for aa in AA:
        if aa == target:
            continue
        p = props[aa]
        row = {
            "cand": aa,
            "d_charge": p["charge_curated"] - t["charge_curated"],
            "d_hbd": p["hbond_donors"] - t["hbond_donors"],
            "d_hba": p["hbond_acceptors"] - t["hbond_acceptors"],
            "d_volume": p["volume"] - t["volume"],
            "d_polarity": p["polarity"] - t["polarity"],
            "d_hydrophobicity": p["hydrophobicity"] - t["hydrophobicity"],
            "pka": p["pka"],
        }
        if prop:
            for scale in ("helix", "sheet", "turn"):
                s = prop.get(scale, {})
                if s.get(target) is not None and s.get(aa) is not None:
                    row[f"d_{scale}"] = s[aa] - s[target]
            h = prop.get("helix_ddg", {})
            if h.get(target) is not None and h.get(aa) is not None:
                row["helix_ddg_target"] = h[aa]
                row["d_helix_ddg"] = h[aa] - h[target]
        rows.append(row)
    return rows


def matrix_scores(target, matrices):
    """Matrix-based similarity scores for all 19 candidates."""
    scores = {aa: {} for aa in AA}
    ti = AA.index(target)
    for acc, (name, higher_better) in MATRIX_ACCS.items():
        e = matrices.get(acc)
        if not e:
            continue
        for aa in AA:
            if aa == target:
                continue
            scores[aa][name] = e["matrix"][ti][AA.index(aa)]
    return scores


GOAL_DESC = {
    "specificity": "Increase specificity (sharpen substrate discrimination)",
    "binding-anion": "Residue binds an anionic partner (phosphate/carboxylate); keep binding, tune it",
    "remove-interaction": "Remove an unwanted interaction",
    "catalytic": "Residue is catalytic (high risk)",
}

BASIC = "RKH"
ACIDIC = "DE"
POLAR = "NQSTY"
HYDRO = "AFILVMWP"


def shortlist_for(target, goal):
    """Role-based shortlist (from chemistry_notes.md section 2).

    Arg-specific rules are detailed; other targets get class-based heuristics.
    Returns [(cand, why)].
    """
    if goal == "specificity":
        if target == "R":
            return [
                ("K", "Keeps +1 charge, loses bidentate guanidinium -> more directional, weaker off-target binding. Workhorse choice."),
                ("H", "pH-switchable charge; adds H-bond acceptor. Use for pH-tuned specificity."),
                ("Q", "Keeps H-bond donors, removes charge. Use if the charge drives non-specific binding."),
                ("A", "Removes the interaction entirely. Use if Arg mediates off-target contacts."),
            ]
        if target in BASIC:
            return [
                ("K" if target != "K" else "R", "Keeps +1 charge, changes geometry/directionality."),
                ("H", "pH-switchable charge; adds H-bond acceptor."),
                ("Q", "Keeps H-bond donors, removes charge."),
                ("A", "Removes the interaction entirely."),
            ]
        if target in ACIDIC:
            return [
                ("Q", "Keeps H-bond acceptors, removes negative charge."),
                ("N", "Polar neutral; keeps H-bonding, removes charge."),
                ("A", "Removes the interaction entirely."),
                ("S", "Small polar; keeps a weak H-bond."),
            ]
        if target in POLAR:
            return [
                ("A", "Removes the side-chain interaction entirely."),
                ("S" if target != "S" else "T", "Small polar; changes H-bond geometry."),
                ("G", "Removes interaction + adds backbone flexibility."),
            ]
        # hydrophobic
        return [
            ("A", "Smallest; minimal perturbation of the core."),
            ("S", "Introduces a polar contact."),
            ("N", "Introduces H-bonding."),
        ]
    if goal == "binding-anion":
        if target in BASIC:
            return [
                ("K" if target != "K" else "R", "Preserves salt bridge (weaker, single-directional)."),
                ("H", "Preserves salt bridge below pH 6; neutral H-bond at pH 7."),
                ("Q", "Preserves H-bonding to the anion, removes electrostatics."),
            ]
        return [("K", "Introduces a salt bridge to the anion."),
                ("R", "Introduces a bidentate salt bridge."),
                ("H", "pH-dependent salt bridge.")]
    if goal == "remove-interaction":
        return [
            ("A", "Cleanest knock-out of the side chain."),
            ("G", "Knock-out + local flexibility."),
            ("S", "Keeps a weak polar contact."),
        ]
    # catalytic
    if target in BASIC:
        return [
            ("K" if target != "K" else "R", "Only plausible charge-preserving swap; expect activity loss."),
            ("H", "If mechanism tolerates imidazole chemistry."),
        ]
    if target in ACIDIC:
        return [
            ("D" if target != "D" else "E", "Shorter/longer carboxylate; subtle geometry change."),
            ("Q" if target != "Q" else "N", "Keeps H-bonding, removes charge; expect major activity loss."),
        ]
    return [
        ("S", "If the mechanism uses an H-bond; expect activity loss."),
        ("A", "Knock-out control; expect loss of function."),
    ]


def _f(v, width=0, spec=".1f"):
    """Format a number for display; print '-' for NaN/None (e.g. a missing
    matrix entry such as KOSJ context for Gly). width=0 -> no padding."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "-" if width == 0 else "-".rjust(width)
    s = format(v, spec)
    return s if width == 0 else s.rjust(width)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--residue", required=True, help="Residue to mutate, 1-letter AA (e.g. R)")
    ap.add_argument("--goal", default="specificity", choices=list(GOAL_DESC))
    ap.add_argument("--context", default="exposed", choices=["exposed", "buried"],
                    help="manual solvent context (overridden by auto-SASA when --pdb is given)")
    ap.add_argument("--pdb", help="PDB file: enables structure-aware mode (SS + auto-SASA)")
    ap.add_argument("--dssp", help="optional `gmx dssp` .dat file for SS (overrides PDB records)")
    ap.add_argument("--structure", choices=["helix", "sheet", "turn", "coil"],
                    help="manual secondary-structure context (used when no --pdb)")
    args = ap.parse_args()

    indices, matrices, contacts, chem = load()
    prop = load_propensities(indices)
    struct = ps.load_structure(args.pdb, args.dssp) if args.pdb else None
    residue, info = resolve_target(args, struct)
    if residue not in AA:
        sys.exit(f"unknown AA: {residue}")

    props = build_profiles(indices, chem)
    deltas = delta_table(residue, props, prop)
    scores = matrix_scores(residue, matrices)

    # secondary structure: from PDB, else manual --structure, else unknown
    ss_code = info.get("ss")
    if ss_code is None and args.structure:
        ss_code = {"helix": "H", "sheet": "E", "turn": "T", "coil": "C"}[args.structure]

    # context: auto-SASA from PDB, else manual --context
    context = args.context
    sasa_note = ""
    if struct is not None and info.get("sasa") is not None:
        context, sasa_val, _ = ps.classify_exposure(struct["res_sasa"], info["key"])
        sasa_note = f" (auto-SASA {sasa_val:.0f} A2)"

    pos_note = (f" [{info['resname']}{info['number']}"
                + (f",{info['chain']}" if info.get('chain') else "") + "]") if info.get("number") else ""
    print(f"=== Substitution advisor: {residue} ({AA3[residue]}){pos_note} ===")
    if ss_code:
        src = f" [{struct['ss_source']}]" if struct else " [manual]"
        print(f"Secondary structure: {ss_code} ({SS_NAMES.get(ss_code, '?')}){src}")
        basis = info.get("ss_basis")
        if basis:
            p, d = basis
            print(f"  SS basis: PDB records={p}, DSSP={d} "
                  f"(conservative union -> {ss_code})")
    print(f"Goal: {GOAL_DESC[args.goal]}")
    print(f"Context: {context}{sasa_note}\n")

    print("Property deltas (candidate vs residue):")
    hdr = f"{'cand':5s} {'d_chg':>5s} {'d_HBD':>5s} {'d_HBA':>5s} {'d_vol':>7s} {'d_polar':>7s} {'d_hydro':>7s} {'pKa':>6s}"
    print(hdr)
    for r in sorted(deltas, key=lambda x: x["d_volume"]):
        pka = f"{r['pka']:.1f}" if r["pka"] is not None else "  -"
        print(f"{r['cand']:5s} {r['d_charge']:5.0f} {r['d_hbd']:5.0f} {r['d_hba']:5.0f} "
              f"{r['d_volume']:7.1f} {r['d_polarity']:7.1f} {r['d_hydrophobicity']:7.2f} {pka:>6s}")

    print("\nMatrix scores for residue row (higher = more similar, except Grantham):")
    print(f"{'cand':5s} {'BLOSUM62':>9s} {'PAM250':>7s} {'Grantham':>9s} {'McLachl':>8s} {'ctx':>6s}")
    for c in AA:
        if c == residue:
            continue
        s = scores[c]
        ctx = s.get("context_exposed" if args.context == "exposed" else "context_buried", float("nan"))
        print(f"{c:5s} {_f(s.get('BLOSUM62', float('nan')), 9, '.0f')} {_f(s.get('PAM250', float('nan')), 7, '.0f')} "
              f"{_f(s.get('Grantham_distance', float('nan')), 9, '.0f')} {_f(s.get('McLachlan_sim', float('nan')), 8, '.0f')} {_f(ctx, 6, '.1f')}")

    # contact potential (structure-aware only): rough pairwise interaction with neighbors
    if struct is not None and info.get("key") is not None:
        neighbors = ps.find_neighbors(struct["residues"], info["key"], CONTACT_CUTOFF)
        cm = contacts.get(CONTACT_ACC, {}).get("matrix")
        if neighbors and cm:
            cp_dv = contact_potential_deltas(residue, neighbors, cm)
            print(f"\nContact potential ({CONTACT_ACC}; Miyazawa-Jernigan 1999, buried env):")
            print(f"  {len(neighbors)} C-alpha neighbors < {CONTACT_CUTOFF:.1f} A: "
                  f"{' '.join(neighbors)}")
            print(f"  {'cand':5s} {'dV':>8s}   (negative = more favorable with these neighbors)")
            for cand, dv in sorted(cp_dv.items(), key=lambda x: x[1]):
                print(f"  {cand:5s} {dv:+8.2f}")

    # secondary-structure propensity (only when the residue has a defined structure)
    if ss_code in ("H", "E", "T"):
        scale = {"H": "helix", "E": "sheet", "T": "turn"}[ss_code]
        print(f"\n{SS_NAMES.get(ss_code)} propensity (Chou-Fasman {scale}; O'Neil-DeGrado helix dG):")
        print(f"{'cand':5s} {'d_CF_'+scale:>10s} {'dG_helix':>9s}")
        for r in sorted(deltas, key=lambda x: x.get(f"d_{scale}", 0), reverse=True):
            cf = r.get(f"d_{scale}")
            ddg = r.get("d_helix_ddg")
            cfs = f"{cf:+.2f}" if cf is not None else "   -"
            ddgs = f"{ddg:+.1f}" if ddg is not None else "   -"
            print(f"{r['cand']:5s} {cfs:>10s} {ddgs:>9s}")

    print(f"\nRole-based shortlist ({args.goal}):")
    for cand, why in shortlist_for(residue, args.goal):
        s = scores[cand]
        ctx = s.get("context_exposed" if args.context == "exposed" else "context_buried", float("nan"))
        print(f"  {cand} ({AA3[cand]}): {why}")
        print(f"      [BLOSUM62={_f(s.get('BLOSUM62', 0), 0, '.0f')}, Grantham={_f(s.get('Grantham_distance', 0), 0, '.0f')}, ctx={_f(ctx, 0, '.1f')}]")

    # structure-aware anti-pattern warnings
    if ss_code in ("H", "E", "T"):
        warned = []
        for r in deltas:
            for wmsg in anti_pattern_warnings(ss_code, r["cand"], r):
                warned.append((r["cand"], wmsg))
        if warned:
            print(f"\nStructure warnings ({ss_code} = {SS_NAMES.get(ss_code)}):")
            for cand, wmsg in warned:
                print(f"  {cand} ({AA3[cand]}): {wmsg}")

    print("\nCaveats: BLOSUM/PAM = evolutionary frequency, not design suitability.")
    print("Contact potential = rough statistical pair-energy (C-alpha neighbors), not a dG.")
    print("Protein pKa shifts from solution values. Validate with MD (GROMACS) + binding free energy.")


if __name__ == "__main__":
    main()
