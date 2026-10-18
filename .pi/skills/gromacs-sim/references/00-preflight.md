# Phase 0 — Preflight

Run before any phase. `--cpu` for phases 1–4 and 7 (any stack mode);
`--gpu` for phases 5–6 and large-system GPU-EM (gromacs mode required).

```bash
scripts/preflight.sh <sim_dir> --cpu     # any mode
scripts/preflight.sh <sim_dir> --gpu     # gromacs mode; exit 2 + MODE line otherwise
```

Also run `scripts/check_templates.sh` at phase 0 (mandatory — grompp smoke test
of the assets; a FAIL is a real asset bug, e.g. the I-85 T-coupling defect —
stop and report).

- Exit 2 + `MODE` line → you are not in `gromacs` mode. Self-check: `PI_PROVIDER`
  must contain `:8093` (your LLM on the iGPU). If yes → `make gromacs`
  (autonomous). If no → hard-stop and escalate; the switch would kill your own
  compute. Never switch to any other mode, never switch away from `gromacs`.
- Disk check reads `prod_time_ps` from `state.json` (default 10 ns); requires
  ≥ 2× the §15 estimate.
- `--gpu` also verifies: gromacs-rocm running, VRAM idle (< 512 MiB),
  `gmx --version` shows HIP + gfx1100.
- **Never fall back to CPU for phases 5-6.** If `--gpu` cannot pass (container
  dead, wrong mode, VRAM busy) → **hard stop and report to the user**. Do NOT
  run a phase-5/6 mdrun in a transient CPU container "to make progress" — a CPU
  equilibration is not a valid phase-5 result and `check_equil.sh` fails its
  GPU-offload gate (log shows `GPU detection failed`).

## Tier A / Tier B questions

**Tier A (must ask the user — no silent default):** system identity and anything
that changes the physics or the box.
- Protein ID / PDB code (or structure source), and the biological question.
- **Protonation**: pH (default 7.0), His protonation states, crystal waters (keep/remove).
- **Box type + margin** (e.g. cubic/dodecahedron, 1.0 nm).
- Ion concentration (default 0.15 M).
- Force field + water model (default OPLS-AA + SPC/E on this stack).
- **Temperature + pressure** (default 300 K / 1.0 bar) — state them; 310 K for physiological.
- **Production length** (e.g. 200 ps, 10 ns) — the scientific target; no silent default.

**Tier B (defaults — state them, confirm before phase 5):** simulation length and
algorithm choices. Defaults on this stack:
- EM: `steep`, `emtol = 10` (large systems → `cg`).
- NVT: 100 ps; NPT: 500 ps (membranes/large → longer).
- **Position restraints: NOT used in the shipped assets** — state this to the user; add posre if the system needs it.
- Sampling: `nstenergy`/`nstlog`/`nstxout-compressed = 1000` (2 ps).
State the Tier B plan and get confirmation before launching phase 5.

## state.json schema

Fixed keys (do not invent variants — the disk check reads `prod_time_ps`):

```json
{
  "sim": "<name>", "created": "<YYYY-MM-DD>", "phase": "<n>", "phase_status": "<status>",
  "system": "<PDB id>", "ff": "oplsaa", "water": "spce", "pH": 7.0, "ion_mol": 0.15,
  "box": "cubic", "margin_nm": 1.0,
  "em_tol": 10, "nvt_ps": 100, "npt_ps": 500, "prod_time_ps": 10000,
  "ref_t": 300, "ref_p": 1.0
}
```

Optional tracking sections (added as phases complete — NOT Tier A plan fields,
so they do not violate "fixed keys" above):
- `gates.<phase>.<check>` — gate outcomes (e.g. `"gates": {"em": {"algo": "sd"}}`).
- `files.<phase>_out` — the canonical output (e.g. `"files": {"em_out": "04_em/em.gro"}`).
- `runs.<run>` — for detached runs: `expected_end`, `restarts`, `profile`
  (see `monitoring.md`).

Create `state.json` + `RUNLOG.md` at phase 0. Append to `RUNLOG.md` after
**every** completed step (timestamp, action, gate result). `created` must be the
real date — never a fabricated one.

## Operating rules

- **KB-usage:** read the phase's cited KB sections (the runbook's `KB:` line)
  before first use; on any grompp/mdrun failure, read KB `01.9` (failure
  catalog) before retrying.
- **Verbatim commands:** runbook commands are verbatim. Any deviation (extra
  flags, reordered steps) must be justified in `RUNLOG.md`.
- **Duplicate-run check:** when the user suspects a duplicate run, **check**
  (`check_running.sh`, `pgrep`, `docker ps`) — don't theorize.

KB: `00.1` (stack layout), `00.4` (modes).
