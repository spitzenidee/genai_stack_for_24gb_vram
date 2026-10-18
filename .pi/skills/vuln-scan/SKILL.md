---
name: vuln-scan
description: >
  Vulnerability scanning for the stack (review phase, tag-triggered).
  Dockerized Trivy (SCA: deps + OS packages + docker images + secrets),
  Semgrep CE (SAST: python/javascript/typescript), and a slopsquatting tier
  (depsafe + sloppy-joe: typosquatting / AI-hallucinated package names) in
  transient containers (tmd pattern). Use when a board card is tagged
  `vuln-scan`, when the reviewer runs the scan phase, or for an optional
  implementer self-check. `vuln-scan repo <path>` scans a repo; `vuln-scan
  image <name>` scans a local docker image; `vuln-scan build` builds the
  local scanner images.
---

# vuln-scan

Vulnerability scanning as a **review phase**: three tiers with disjoint
coverage, run in transient docker containers (same pattern as the `tmd`
wrapper — sh + docker, no host deps).

- **Trivy** — SCA: dependency vulnerabilities (lock files), OS packages,
  docker images, and hard-coded secrets.
- **Semgrep CE** — SAST: source-code patterns for python / javascript /
  typescript (explicit registry rulesets).
- **Slopsquatting tier** — dependency *name* checks (the blind spot of both
  SCA and SAST: a squatted package with no known CVE passes Trivy clean):
  - **depsafe** — Python-only: typosquatting / slopsquatting / homoglyph /
    separator / prefix-suffix checks against a built-in 500+ popular-PyPI
    corpus (`requirements*.txt`, `pyproject.toml`, `Pipfile`).
  - **sloppy-joe** — 8 ecosystems (npm/pnpm/Yarn/Bun, Python, Rust, Go,
    Ruby, PHP, JVM, .NET): manifest + lockfile provenance/sync, canonical
    policy, and (online) registry existence + similarity + OSV.dev.

The four Python-only scanners (safety / pip-audit / pysentry / pyscan) are
redundant with Trivy and are **not** part of this tool.

## Usage

```sh
.pi/skills/vuln-scan/scripts/vuln-scan.sh repo <path>     # common case: all tiers
.pi/skills/vuln-scan/scripts/vuln-scan.sh image <name>    # opt-in: local docker image
.pi/skills/vuln-scan/scripts/vuln-scan.sh build           # build the local scanner images
```

- `repo <path>` — runs **Trivy fs** (vuln + secret, MEDIUM+), **Semgrep**
  (explicit rulesets), **depsafe** and **sloppy-joe** over the repo at
  `<path>`.
- `image <name>` — runs **Trivy image** on a local docker image (via
  `docker.sock`). Only when a card touched a Dockerfile / built an image.
- `build` — builds the two local slopsquatting images from
  `docker/*.Dockerfile` (also done on demand by `repo` when an image is
  missing and not pullable).

## Output

- **Full JSON** (one file per scan) →
  `work/vuln_scan_results/<repo-short-name>/<UTC-timestamp>-<tool>.json`
  (e.g. `work/vuln_scan_results/genai_stack/2026-10-14T05-49Z-trivy.json`).
  `<repo-short-name>` = basename of the scanned path. `work/*` is already
  gitignored — results are **never committed**. Override the root with
  `VULN_SCAN_RESULTS_DIR` (env var or `vuln-scan.env`, see Config).
  A repo scan produces up to four reports: `-trivy.json`, `-semgrep.json`,
  `-depsafe.json`, `-sloppy-joe.json`.
- **Summary → stdout**: count by severity (CRITICAL/HIGH/MEDIUM/LOW) +
  findings (ID, severity, title, file:line, capped at 40) so the reviewer
  can triage without reading the raw JSON.
- Severity mapping for the summary: Semgrep INFO→LOW, WARNING→MEDIUM,
  ERROR→HIGH; sloppy-joe Error→HIGH, Warning→MEDIUM; depsafe severities are
  used as-is (critical/high/medium/low/info).

## Config

All tunables live in `vuln-scan.env` (co-located with this skill, sibling of
`scripts/`). Precedence: **explicit env var > `vuln-scan.env` > built-in
default** (defaults = pre-externalization behavior, so nothing changes on
upgrade).

| Variable | Default | Meaning |
| --- | --- | --- |
| `VULN_SCAN_TRIVY_IMAGE` | `aquasec/trivy:0.76.0` | Pinned Trivy image |
| `VULN_SCAN_SEMGREP_IMAGE` | `semgrep/semgrep:1.180.0` | Pinned Semgrep image |
| `VULN_SCAN_TRIVY_SCANNERS` | `vuln,secret` | Trivy fs scanners (repo scan) |
| `VULN_SCAN_TRIVY_SEVERITY` | `MEDIUM,HIGH,CRITICAL` | Minimum severity (repo + image scans) |
| `VULN_SCAN_SEMGREP_RULESETS` | `p/python,p/javascript,p/typescript` | Comma-separated; expanded to one `--config` per entry |
| `VULN_SCAN_SKIP_DIRS` | `.git,work,_dl,hfmodels,models,node_modules,__pycache__,.venv,venv,dist,build` | Directory names skipped by both scanners |
| `VULN_SCAN_RESULTS_DIR` | *(empty)* | Results root; empty = `$STACK_ROOT/work/vuln_scan_results` |
| `VULN_SCAN_SUMMARY_LIMIT` | `40` | Max findings listed per report in the stdout summary |
| `VULN_SCAN_DEPSAFE_IMAGE` | `vuln-scan-depsafe:local` | depsafe image (local build from `docker/depsafe.Dockerfile`) |
| `VULN_SCAN_SLOPPYJOE_IMAGE` | `vuln-scan-sloppy-joe:local` | sloppy-joe image (local build from `docker/sloppy-joe.Dockerfile`) |
| `VULN_SCAN_SLOPSQUAT_ONLINE` | `0` | `1` = online slopsquatting tier (registry existence / OSV.dev; package names only). `0` (default) = offline |

Example: `VULN_SCAN_TRIVY_SEVERITY=HIGH vuln-scan.sh repo .` (env var wins
over the file).

**Not tunable (privacy invariants, hardcoded in the script):** trivy
`--disable-telemetry --skip-version-check`, semgrep `--metrics off`, explicit
`--config` (never `--config auto`), `:ro` source mount, slopsquatting
offline-by-default (online only via `VULN_SCAN_SLOPSQUAT_ONLINE=1`),
sloppy-joe config mounted from the skill dir (never from the scanned repo).

## Trigger protocol (board)

- The **implementer** adds the `vuln-scan` tag on line 1 when the change
  touches code/containers/scripts (completion-checklist item). The tag is
  **appended** to the existing tag line — never replaces pre-existing tags
  (`[tag:security]` → `[tag:security] [tag:vuln-scan]`).
- The **reviewer** runs the scan at the start of review when the tag is
  present **or** judges it warranted (safety net). Pure
  spec/content/GROMACS/Blender cards → no tag → no scan.
- **Reviewer-only** is the canonical/gating scan. The implementer may use
  the tool for an optional shift-left self-check, but it is not part of the
  completion criteria.

## Slopsquatting scanner (third tier)

**Why:** neither Trivy (SCA: known-CVE database) nor Semgrep (SAST: source
patterns) inspects dependency *names*. A squatted / AI-hallucinated package
with no known CVE passes both clean — the slopsquatting vector (AI agents
hallucinate non-existent package names; attackers register them with
malware). This tier closes that blind spot with two existing open-source
tools (no in-house checker), each in its own transient container.

### depsafe (Python-only, offline core)

- Upstream: `kriskimmerle/depsafe` (MIT, v0.1.0, single zero-dependency
  Python file — vendored in `docker/depsafe.py`, pin in
  `docker/depsafe-VERSION`).
- Checks: Levenshtein 1–2 vs a built-in 500+ popular-PyPI corpus, separator
  confusion, char doubling, homoglyphs, namespace confusion, prefix/suffix
  squatting (rules R01–R06); R07 (PyPI existence/age) only with `--online`.
- Parses `requirements*.txt` (recursive), `pyproject.toml`, `Pipfile`.
- **Offline by default** (built-in corpus, no network). `--online` (opt-in,
  `VULN_SCAN_SLOPSQUAT_ONLINE=1`) queries the PyPI JSON API for package
  names only.

### sloppy-joe (8 ecosystems, offline `check`)

- Upstream: `brennhill/sloppy-joe` (Apache-2.0, Rust single static musl
  binary, v1.1.0 — pinned in `docker/sloppy-joe.Dockerfile` via `ARG`
  VERSION + per-arch sha256; prebuilt release binary, no build step).
- Ecosystems: npm/pnpm/Yarn/Bun, Python, Rust, Go, Ruby, PHP, JVM, .NET.
- **`check` (default, offline):** manifest parsing, lockfile presence +
  sync/provenance (integrity hashes), unresolved-version policy, canonical
  policy. Catches e.g. a dependency declared in `package.json` but missing
  from the lockfile — the signature of a freshly squatted package.
- **`--full` (opt-in, `VULN_SCAN_SLOPSQUAT_ONLINE=1`):** adds the online
  tier — registry existence (hallucinated names), similarity (11 mutation
  generators vs registry, 7-day disk cache under
  `work/vuln_scan_results/.cache/sloppy-joe`), version-age / maintainer /
  install-script metadata, OSV.dev known vulnerabilities. Sends package
  names only.
- **Config:** the tool refuses in-repo config by design (an AI agent must
  not be able to allowlist its own hallucinations). The default config
  (`docker/sloppy-joe-default-config.json`, generated via `sloppy-joe init`)
  is mounted read-only from the skill dir at `/config`.

### Notes

- A scanner failure does not abort the run (existing pattern); the run
  succeeds if at least one report is produced.
- Both tools are intentionally shipped now; the user may drop one later
  after watching project trajectory (see the board card).

## Privacy (hard requirement)

- Every trivy invocation carries `--disable-telemetry --skip-version-check`.
- Every semgrep invocation carries `--metrics off` and uses **explicit
  rulesets** (`--config p/python --config p/javascript --config p/typescript`)
  — never `--config auto` (which sends languages/frameworks/project-URL to
  the Semgrep Registry).
- **Slopsquatting tier is offline by default** (`VULN_SCAN_SLOPSQUAT_ONLINE=0`):
  depsafe uses its built-in corpus, sloppy-joe runs the fast local guardrail
  — no outbound traffic. Online mode (=1) sends only package *names* to the
  registries (PyPI JSON API / npm registry / OSV.dev) — never code —
  analogous to the already-allowed public vuln-DB downloads.
- Only other outbound traffic = public vuln-DB / rules downloads. No code,
  no repo content, no identifying data leaves the LAN.

## Pinned scanner images

- `aquasec/trivy:0.76.0` (registry pull)
- `semgrep/semgrep:1.180.0` (registry pull)
- `vuln-scan-depsafe:local` (local build: `docker/depsafe.Dockerfile`,
  depsafe v0.1.0 @ 067b09d, vendored)
- `vuln-scan-sloppy-joe:local` (local build: `docker/sloppy-joe.Dockerfile`,
  sloppy-joe v1.1.0 @ 3d9d413, prebuilt release binary, sha256-pinned)

Registry images are pulled on demand if not present; local images are built
on demand (or via `vuln-scan build`) if not present. The pins live in
`vuln-scan.env` (`VULN_SCAN_TRIVY_IMAGE` / `VULN_SCAN_SEMGREP_IMAGE` /
`VULN_SCAN_DEPSAFE_IMAGE` / `VULN_SCAN_SLOPPYJOE_IMAGE`) and in the
Dockerfiles (upstream version + checksums) — bump them there, not in the
script, and note the new versions in the board card Log.

## Behavior notes

- **No hard fail**: scanners run without `--exit-code` / `--error`; a
  non-zero scanner exit does not abort the run. Whatever JSON was produced
  is kept and summarized; the wrapper exits 1 only if **no** report was
  produced. The AI sees all findings and judges them.
- **Skip list**: both scanners skip directory *names* in
  `.git,work,_dl,hfmodels,models,node_modules,__pycache__,.venv,venv,dist,build`
  (heavy data / build artifacts, not code — the stack root is ~116G of
  models). Override with `VULN_SCAN_SKIP_DIRS` (comma-separated names; env
  var or `vuln-scan.env`).
- **Bash coverage gap**: the Semgrep Registry has no `p/bash` ruleset
  (verified 14.10.2026: `p/bash` and `p/shell` both 404). Shell scripts are
  covered by Trivy's secret scanner only; SAST for bash is out of scope V1.
- **Slopsquatting coverage nuance**: sloppy-joe's *similarity* detection
  (mutation candidates checked against the registry) is part of the online
  `--full` tier — the offline `check` covers provenance/lockfile/sync +
  canonical policy (e.g. a squat declared in the manifest but absent from
  the lockfile is flagged offline). depsafe's core (Levenshtein vs the
  built-in corpus) is fully offline. depsafe recursively globs
  `**/requirements*.txt`, so files under `work/` (test fixtures) can appear
  in its report — noise the reviewer can ignore. sloppy-joe auto-detects
  manifests recursively (package.json / requirements.txt / pyproject.toml /
  …); a repo with no manifest yields no sloppy-joe report (non-fatal).
- **sloppy-joe known failure mode**: a *broken* venv symlink (e.g.
  `work/yt-commenter-stats/.venv/bin/python` → container-only
  `/usr/local/bin/python`) makes sloppy-joe exit 2 (runtime error, no
  report) when it resolves the Python environment. Non-fatal (the run
  continues with the other tiers); fix by removing the stale venv. No
  skip-dirs flag exists upstream.
- **sloppy-joe lockfile behavior** (verified 16.10.2026):
  - *Missing lockfile* (manifest present, no lockfile): sloppy-joe exits 2
    with **no** JSON report — a hard fail, because it cannot run
    version-sensitive checks without a lockfile. Non-fatal: the wrapper logs
    "NO report produced" and continues with the other tiers.
  - *Out-of-sync lockfile* (manifest declares a package absent from the
    lockfile): sloppy-joe exits 1 **with** a JSON report containing
    `resolution/missing-lockfile-entry` (Error) + `resolution/no-exact-version`
    (Error) issues and `full_scan_recommended: true`. Both map to HIGH in the
    summary — this is the squatter signature the offline `check` is designed
    to catch (a freshly squatted dep declared in the manifest but never
    resolved in the lockfile).
- **Secrets**: covered by Trivy's secret scanner. Allowlist known test
  fixtures via trivy's `--secret-config` if needed (not wired by default).
- **DB freshness**: Trivy auto-updates its vuln DB at runtime (daily TTL;
  host has internet).

## Scope

The repo the card targets (default: the stack root, `genai_stack`).
Extensible to other Gitea repos later (per-repo subfolders under
`work/vuln_scan_results/`).
