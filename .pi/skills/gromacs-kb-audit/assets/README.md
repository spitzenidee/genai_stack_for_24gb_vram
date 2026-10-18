# Probe assets — verified against build 2026.3-dev-20260625

`tmin.gro` + `tmin.top` form a minimal, fully self-contained 1-atom system for
`grompp` option probes. `base.mdp` is the minimal MDP. All three were run
end-to-end (`grompp` exit 0, TPR confirmed via `gmx dump -s`) before being
frozen here. **Do not "fix" or reflow them** — the shapes below are traps that
were hit and verified:

## Mechanical traps (why these files look the way they do)

1. **`.gro` is fixed-width.** Columns: resnr (5), resname (5), atomname (5),
   atomnr (5), then 8-char coordinates. The atom name in the `.gro` (`LIG1`)
   must match the `.top` atom name exactly, or grompp warns
   `atom name 1 in tmin.top and tmin.gro does not match (LIG1 - …)` and
   pollutes probe stderr. (The old `/work/kbval/t_min.gro` is misaligned —
   the parser reads its atom name as "DU" — do not reuse it.)
2. **Box must be ≥ 3 nm.** With the default `rvdw = 1.0` and Verlet lists, a
   2 nm box fails: `The cut-off length is longer than half the shortest box
   vector … Increase the box size or decrease rlist.`
3. **Atomtype mass must be > 0.** Mass 0 fails: `atom LIG1 (Res LIG-1) has
   mass 0 (state A) / 0 (state B)`. (The old `/work/kbval/t_min.top` has mass
   0 and fails in this build — do not reuse it.)
4. **`gmx dump` takes `-s <.tpr>`, not a positional argument** (this build).
   `gmx dump probe.tpr` → `Positional argument 'probe.tpr' cannot be accepted`.
5. **Pipes mask exit codes.** `grompp … | grep …` returns grep's status — a
   failing grompp looks like success. Capture the log, check `$?`.
6. **Large-cutoff blocks hit the box-size limit (expected noise).** The probe
   box is 3 nm (half-vector 1.5 nm). A KB block with `rvdw`/`rcoulomb` > 1.5 nm
   (e.g. `rvdw = 4.5` for a large-cutoff method) fails with `The cut-off length
   is longer than half the shortest box vector …` — that is **system noise**
   (box too small for the cutoff), **not** an option-parsing problem. Do not
   file it; the option itself is fine.

## `probe.gro` + `probe.top` — protein + water system (T-coupling / group probes)

A small **single ALA residue + SPC water** system (oplsaa), built so that
`tc-grps = Protein Non-Protein` resolves to two **non-empty** groups. This is
the substrate for the per-block MDP probes (see `probe_suite.sh`): the 1-atom
`tmin` system splits its lone atom into "Other", leaving both `Protein` and
`Non-Protein` empty, so grompp **skips the T-coupling count check** and a block
with `tc-grps = Protein Non-Protein` + a single `tau-t`/`ref-t` passes clean
(issues_agent_run.md A4). Against this asset the same block fatales with
`Invalid T coupling input: 2 groups, 1 ref-t values and 1 tau-t values`.

Verified against 2026.3-dev-20260625:
- `grompp -f <2-value block> -c probe.gro -p probe.top -maxwarn 5` → **exit 0**
  (T-coupling resolves: Protein ≈ 30 DoF, non-Protein ≈ 9195 DoF).
- `grompp -f <1-value block> …` → **exit 1**, `Invalid T coupling input: …`.

Traps hit while building it (do not "fix"):
1. **`.gro` needs a title line.** Line 1 = title, line 2 = atom count. Omitting
   the title makes grompp read the count line as the title and collapse the
   frame to 1 atom (see `tmin.gro` — it has a ` test` title line).
2. **`tcoupl = group` is no longer valid** in 2026.3. Valid enum:
   `'No' 'Berendsen' 'Nose-Hoover' 'yes' 'Andersen'`. Group T-coupling is now
   `tcoupl = yes` (plus `tc-grps`).
3. **`-maxwarn 5` is required** in the probe command: the minimal system emits
   ~3 benign warnings, and grompp's default `maxwarn = 0` turns them into a
   `Too many warnings` fatal that would mask the real verdict. Hard fatals
   (T-coupling, atom mismatch, unknown option) are **not** warnings and still
   fatal under `-maxwarn 5`.
4. **Water count must match the topology.** `solvate` records `SOL N` in the
   `.top`; pin `N` to the actual `.gro` water count (`grep -c SOL probe.gro / 3`)
   or grompp fatales on the atom-count mismatch.

## Directive probe templates (topology `[ … ]` name/usability probes)

`dir_probe_a.tpl` and `dir_probe_b.tpl` are minimal topologies with a `%DIR%`
slot, built on the same verified core as `tmin.top` (oplsaa include, DUM
atomtype, 1-atom `LIG` moleculetype). Verified against
2026.3-dev-20260625:

- **Stage A (name check)** — `dir_probe_a.tpl`, `%DIR%` at **line 1**. An
  unknown name there always yields `ERROR …: Invalid directive <name>`
  (exit 1); a known name yields any other signal (order complaint, duplicate,
  content parse error) — never `Invalid directive <name>`. This is the ONLY
  valid name check.
- **Stage B (usability)** — `dir_probe_b.tpl`, `%DIR%` at the canonical
  position (after the moleculetype, before `[ system ]`), known names only:
  exit 0 = usable there; `Invalid order for directive <name>` = not usable
  there (top-level tables, `molecules`). Duplicate-name cases (`system`,
  `molecules`) parse as exit 0 — harmless.
- **SILENT-SKIP TRAP (2026.3)**: an *unknown* directive at the end of a
  moleculetype (after the last subsection, before `[ system ]`) is **silently
  ignored** — grompp exits 0. Never use stage B (or any end-of-moleculetype
  injection) for name verdicts.
- **`Invalid order` can name the *next* directive**: an unknown directive
  followed by a known one at top level may surface as `Invalid order for
  directive <next>` (e.g. bogus + `[ system ]`). The line-1 stage-A
  convention avoids this; when probing ad hoc, read the whole log.
- **Controls**: the suite always runs `ctl_bad` (`[ bondtyps ]`, stage A —
  must yield `Invalid directive bondtyps`) and `ctl_good` (`[ bonds ]`,
  stage B — must exit 0); a control mismatch dies the suite.

## Water box (for tool probes needing real water)

If `/work/probe/box.gro` + `/work/probe/box.top` exist in the container
(5832-water SPC-E box, self-contained, verified clean), use them for tool
probes that need a solvated system (e.g. `solvate`, `genion`,
`insert-molecules`). Prior-session material — read-only. If absent, build a
small box with `gmx solvate` from a minimal solute in the session dir.
