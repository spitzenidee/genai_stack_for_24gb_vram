# issues_kb.md — fix-pass section format

Append-only discipline: SKILL.md rule 9 (mirrors the audit's
`references/issue-format.md`). This file defines the section format.

## Fix-pass section (one per fix session)

```markdown
## Fix pass (YYYY-MM-DD — build <version string from gmx --version>)

**Scope:** <n> open issues (I-NN…I-MM) from <audit section date(s)>.
**Result:** <n> fixed, <n> already-fixed (closed), <n> false-positive
(closed), <n> left open (I-NN: <reason>, …).

#### I-NN <title> — FIXED  ✅ RESOLVED (YYYY-MM-DD)
Files: `<path>` (as listed in the issue)
- **Preflight**: <one line — probe re-run, issue confirmed still real>.
- **Applied**: <old text → new text; per file when >1>.
- **Evidence**: <verbatim post-fix build output proving the fixed text is
  correct — `-h` line, grompp exit 0 + `gmx dump` line, listing>.
- **Deviation** (only if the applied fix differs from the Recommended fix):
  <what was wrong in the recommended text, what was applied instead, and
  the build output that decided it>.

#### I-NN <title> — ALREADY-FIXED  ✅ RESOLVED (YYYY-MM-DD)
<Preflight found the KB already reflects the fix. Evidence that the current
text is correct against the build. No edit made.>

#### I-NN <title> — FALSE POSITIVE  ❌ CLOSED (YYYY-MM-DD)
<The issue's claim is disproved by the build; verbatim probe output. No edit
made. (Mirrors the audit's I-17 false-positive convention.)>

#### I-NN <title> — LEFT OPEN (handback to auditor)
**Reason:** UNVERIFIABLE | UNRESOLVABLE | CONTESTED | regression-revert
<What was attempted, and what is needed (e.g. "needs a GPU run", "correct
enum requires source-level check", "conflicts with open I-XX", "regression
suite flagged block_NNN after the edit — reverted").>

## Notes for the auditor
- <new problems discovered during the fix pass — reported, NOT fixed;
  candidates for the next audit>.
- <regression-suite summary: N blocks probed, matrix verdict, CLI claims
  re-checked>.
- <anything else the next audit/fixer should know>.
```

## Status markers (header lines only)

- Fixed or already-fixed: append `  ✅ RESOLVED (YYYY-MM-DD)` to the
  `### I-NN` header line.
- False positive: append `  ❌ FALSE POSITIVE (YYYY-MM-DD — closed by fix
  pass)` to the header line.
- Left open: header line unchanged.

## Additive entry notes (inside an issue entry, after its last line)

Only two kinds, both dated, both additive (the audit's original text stays
untouched):

- `**Fix deviation (YYYY-MM-DD, fix pass):** <corrected fix text + why —
  with the deciding build output>.`
- `**Handback (YYYY-MM-DD, fix pass):** <reason + what is needed>.`

## Conventions

- **Per-issue entries are h4 (`#### I-NN`) on purpose.** The scope grep
  `^### I-` must match only real issue entries — a `LEFT OPEN` fix-pass
  sub-header at h3 would leak into the next fix pass's work list as a
  duplicate. Do not "fix" this back to h3.
- **Evidence is verbatim.** Quoted build output, never paraphrased (same
  standard as the audit's entries).
- **One section per session**, even if the session is resumed and finished
  in a later one (continue the same section; mark it WIP while unfinished).
