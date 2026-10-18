# issues_kb.md — entry format

Append only. Never rewrite, reorder, or delete existing sections or entries.
The file already contains the gold-standard header, prior audit passes, and
resolved issues — your new section goes at the **end** of the file.

## Section header (one per audit session)

```markdown
## New issues from <scope> audit (YYYY-MM-DD)

**Method:** <what was probed — e.g. "all 34 KB files re-read; every tool CLI
re-checked via `gmx <tool> -h`; MDP templates re-run through `gmx grompp`
(EM/NVT/NPT/…); install tree re-listed; semantic claims cross-checked against
the `v<version>` source tag and `manual.gromacs.org/<version>`. CPU-only
grompp / tool probes only — no MD run (eGPU in use).">
**Result:** <N new issues (I-X…I-Y), all confirmed real against the build.>
```

If the build changed since the last audit, add a **Gold standard** note at the
top of the section with the new `gmx --version` string and feature flags
(TNG/Colvars/CP2K/Torch/Plumed, GPU backend, SIMD, VkFFT, command count).

## Issue entry

```markdown
### I-NN <short imperative title>  [H|M|L]
Files: `<path1>`, `<path2>`
<What the KB claims (quote the KB line) vs what the build does (verbatim
build output, quoted). One paragraph per distinct sub-claim. Cite the probe
file where it lives (`kb-audit/probe.mdp`).>
**Recommended fix**: <the exact edit the fixer session should make — option
name, value, sentence replacement, old text → new text. Not applied by this
audit.>
```

## Conventions

- **Numbering**: continue from the last I-NN in the file. Never reuse or
  renumber.
- **Severity**:
  - `[H]` — breaks a workflow or produces wrong results
  - `[M]` — stale name / value, needs update
  - `[L]` — cosmetic / doc-only
- **Files:** — every KB file containing the claim, paths relative to
  `knowledge/`. A claim duplicated across files is **one** issue with all
  files listed.
- **Evidence** — verbatim build output in quotes: `gmx` error text, grompp
  NOTE/warning lines, `-h` lines, `gmx dump` TPR lines, directory listings.
  No paraphrased evidence.
- **Recommended fix** — precise enough that a fixer can apply it mechanically.
  This audit never applies it.
- **False positives** — if re-checking disproves an old issue, do **not**
  delete the old entry; add a note in the new section referencing the issue
  number (I-17 pattern: "FALSE POSITIVE — corrected in place").
- **Verified OK** — close the section with a list of what was checked and
  confirmed fine (tools, options, files), so the next audit can skip it.
- **Notes** — build drift, unverified-needs-GPU items, and anything the fixer
  should know that is not itself an issue.

## Status updates

Do **not** mark issues RESOLVED — that is the fixer session's job. If you find
an open (unresolved) issue from a prior pass is already fixed in the KB, note
it in the new section's Notes ("I-NN: KB already reflects the fix; ready to
close by the fixer").
