#!/usr/bin/env python3
"""Parse raw AAindex files (aaindex1/2/3) into structured JSON.

Usage: python3 parse_aaindex.py <raw_dir> <out_dir>
Produces (entries with unparseable I/M blocks are skipped; see stderr warnings):
  indices.json           aaindex1: 551 single-AA indices (of 566), values in AA order
  matrices.json          aaindex2: 86 20x20 mutation/similarity matrices (of 94)
  contact_potentials.json aaindex3: 43 statistical contact potential matrices (of 47)
  references_all.csv     680 per-entry references (section, accession, description,
                         authors, title, journal, pmid_refs) — derived from the three JSONs
"""
import csv
import json
import re
import sys
from pathlib import Path

AA = "ARNDCQEGHILKMFPSTWYV"


def split_entries(path):
    text = Path(path).read_text()
    return [e for e in text.split("//\n") if e.strip()]


def parse_header(entry):
    acc = desc = ""
    refs, authors, title, journal, comments = [], "", "", "", []
    for line in entry.split("\n"):
        if line.startswith("H "):
            acc = line[2:].strip()
        elif line.startswith("D "):
            desc = line[2:].strip()
        elif line.startswith("R "):
            refs.append(line[2:].strip())
        elif line.startswith("A "):
            authors = line[2:].strip()
        elif line.startswith("T "):
            title = line[2:].strip()
        elif line.startswith("J "):
            journal = line[2:].strip()
        elif line.startswith("* "):
            comments.append(line[2:].strip())
    return acc, desc, refs, authors, title, journal, comments


def parse_index_values(entry):
    """aaindex1 'I' block: 20 values in AA order (A R N D C Q E G H I L K M F P S T W Y V)."""
    vals = []
    in_i = False
    for line in entry.split("\n"):
        if line.startswith("I "):
            in_i = True
            line = line[2:]
        if not in_i:
            continue
        for tok in line.split():
            if re.match(r"^-?\d", tok):
                vals.append(float(tok))
    return vals if len(vals) == 20 else None


NUM_RE = re.compile(r"^-?\d+\.?\d*$")


def parse_matrix_values(entry):
    """aaindex2/3 'M' block. Handles two layouts:

    1. Upper-triangular: row i has i+1 values (most matrices).
    2. Full matrix with optional gap column: M line lists the AA order, which
       may include a leading '-' (gap). Each row has len(AA_order) values.

    Returns a 20x20 matrix indexed by AA order (ARNDCQEGHILKMFPSTWYV) or None.
    """
    aa_order = None
    rows = []
    in_m = False
    for line in entry.split("\n"):
        if line.startswith("M "):
            in_m = True
            m = re.search(r"rows\s*=\s*([A-Z-]+)", line)
            if m:
                aa_order = m.group(1)
            continue
        if not in_m:
            continue
        parts = line.split()
        if parts and all(NUM_RE.match(p) for p in parts):
            rows.append([float(p) for p in parts])

    if not rows:
        return None

    # Case 2: full matrix (every row same width >= 20)
    if aa_order and len(set(len(r) for r in rows)) == 1 and len(rows[0]) >= 20:
        width = len(rows[0])
        if len(rows) == width and all(len(r) == width for r in rows):
            keep = [i for i, aa in enumerate(aa_order) if aa in AA]
            mat = [[0.0] * 20 for _ in range(20)]
            for i in keep:
                for j in keep:
                    mat[AA.index(aa_order[i])][AA.index(aa_order[j])] = rows[i][j]
            return mat

    # Case 1: upper-triangular, 20 rows of increasing width
    if len(rows) == 20 and all(len(rows[i]) == i + 1 for i in range(20)):
        mat = [[0.0] * 20 for _ in range(20)]
        for i in range(20):
            for j in range(i + 1):
                v = rows[i][j]
                mat[i][j] = v
                mat[j][i] = v
        return mat

    return None


def write_references(indices, matrices, contacts, path):
    """Write per-entry references (680 rows) derived from the three JSON lists."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["section", "accession", "description", "authors", "title", "journal", "pmid_refs"])
        for section, entries in (("AAindex1", indices), ("AAindex2", matrices), ("AAindex3", contacts)):
            for e in entries:
                w.writerow([section, e["acc"], e["desc"], e["authors"], e["title"], e["journal"],
                            "; ".join(e["refs"])])


def main(raw_dir, out_dir):
    raw, out = Path(raw_dir), Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    indices = []
    for e in split_entries(raw / "aaindex1"):
        acc, desc, refs, authors, title, journal, comments = parse_header(e)
        vals = parse_index_values(e)
        if vals is None:
            print(f"WARNING: skipped {acc} (no/invalid I block)", file=sys.stderr)
            continue
        indices.append({
            "acc": acc, "desc": desc, "refs": refs, "authors": authors,
            "title": title, "journal": journal, "comments": comments,
            "aa": AA, "values": vals,
        })

    def parse_matrices(name):
        mats = []
        for e in split_entries(raw / name):
            acc, desc, refs, authors, title, journal, comments = parse_header(e)
            mat = parse_matrix_values(e)
            if mat is None:
                print(f"WARNING: skipped {acc} in {name} (no/invalid M block)", file=sys.stderr)
                continue
            mats.append({
                "acc": acc, "desc": desc, "refs": refs, "authors": authors,
                "title": title, "journal": journal, "comments": comments,
                "aa": AA, "matrix": mat,
            })
        return mats

    matrices = parse_matrices("aaindex2")
    contacts = parse_matrices("aaindex3")

    (out / "indices.json").write_text(json.dumps(indices, indent=1))
    (out / "matrices.json").write_text(json.dumps(matrices, indent=1))
    (out / "contact_potentials.json").write_text(json.dumps(contacts, indent=1))
    write_references(indices, matrices, contacts, out / "references_all.csv")
    print(f"indices: {len(indices)}, matrices: {len(matrices)}, contact potentials: {len(contacts)}, "
          f"references: {len(indices) + len(matrices) + len(contacts)}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
