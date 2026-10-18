#!/bin/sh
# vuln-scan — vulnerability scanning wrapper (Trivy + Semgrep CE + slopsquatting).
#
# Runs dockerized scanners in transient containers (tmd pattern: sh + docker,
# no host deps). Three subcommands:
#
#   vuln-scan repo <path>    trivy fs (vuln + secret, MEDIUM+) AND semgrep
#                            (explicit rulesets p/python, p/javascript,
#                            p/typescript) AND the slopsquatting tier
#                            (depsafe: Python names; sloppy-joe: 8 ecosystems)
#                            over the repo at <path>
#   vuln-scan image <name>   trivy image <name> (via docker.sock)
#   vuln-scan build          build the local scanner images (depsafe +
#                            sloppy-joe) from docker/*.Dockerfile
#
# Reports (full JSON, one file per scan):
#   work/vuln_scan_results/<repo-short-name>/<UTC-timestamp>-<tool>.json
#   <repo-short-name> = basename of the scanned path (e.g. genai_stack).
#   Override the results root with VULN_SCAN_RESULTS_DIR.
#
# All tunables (images, scanners, severity, rulesets, skip dirs, results
# root, summary cap, slopsquatting images + online mode) are configurable
# via vuln-scan.env next to scripts/ (precedence: explicit env var >
# vuln-scan.env > built-in default). Privacy invariants stay hardcoded
# (see below).
#
# stdout: severity summary (counts + findings) so the reviewer can triage
# without reading the raw JSON.
#
# Privacy (hard requirement):
#   - every trivy invocation: --disable-telemetry --skip-version-check
#   - every semgrep invocation: --metrics off + explicit rulesets only
#     (never --config auto, which phones home to the Semgrep Registry)
#   - slopsquatting tier is OFFLINE by default (VULN_SCAN_SLOPSQUAT_ONLINE=0):
#     depsafe uses its built-in corpus, sloppy-joe runs the fast local
#     guardrail. Online mode (=1) sends only package NAMES to the registries
#     (PyPI JSON API / npm registry / OSV.dev) — never code.
#   - only other outbound traffic = public vuln-DB / rules downloads.
#
# Scanner images are pinned in vuln-scan.env; pulled on demand if not
# present. The two slopsquatting images are local builds (docker/*.Dockerfile)
# and are built on demand (or via `vuln-scan build`) when missing.
# A scanner failure does NOT abort the run: whatever JSON was produced is
# kept and summarized; the wrapper exits 1 only if no report was produced.
#
# Exit codes: 0 = at least one report produced, 1 = no report produced,
#             2 = usage/environment error.

set -u

DIR="$(cd "$(dirname "$0")" && pwd)"
STACK_ROOT="$(cd "$DIR/../../../.." && pwd)"

# ─── config ─────────────────────────────────────────────────────────────────
# Precedence: explicit env var > vuln-scan.env (co-located with the skill)
# > built-in default (defaults = pre-externalization behavior). The env file
# holds plain KEY=value lines. Values are read per key (NOT sourced — a plain
# assignment in a sourced file would clobber an already-set env var).
CONFIG_FILE="$(cd "$DIR/.." && pwd)/vuln-scan.env"

# cfg <key> — value of <key> in CONFIG_FILE (empty if file or key absent).
cfg() {
  [ -f "$CONFIG_FILE" ] || return 0
  sed -n "s/^$1=//p" "$CONFIG_FILE" | tail -n 1
}

_v=$(cfg VULN_SCAN_TRIVY_IMAGE);      TRIVY_IMAGE="${VULN_SCAN_TRIVY_IMAGE:-${_v:-aquasec/trivy:0.76.0}}"
_v=$(cfg VULN_SCAN_SEMGREP_IMAGE);    SEMGREP_IMAGE="${VULN_SCAN_SEMGREP_IMAGE:-${_v:-semgrep/semgrep:1.180.0}}"
_v=$(cfg VULN_SCAN_TRIVY_SCANNERS);   TRIVY_SCANNERS="${VULN_SCAN_TRIVY_SCANNERS:-${_v:-vuln,secret}}"
_v=$(cfg VULN_SCAN_TRIVY_SEVERITY);   TRIVY_SEVERITY="${VULN_SCAN_TRIVY_SEVERITY:-${_v:-MEDIUM,HIGH,CRITICAL}}"
_v=$(cfg VULN_SCAN_SEMGREP_RULESETS); SEMGREP_RULESETS="${VULN_SCAN_SEMGREP_RULESETS:-${_v:-p/python,p/javascript,p/typescript}}"
_v=$(cfg VULN_SCAN_SUMMARY_LIMIT);    SUMMARY_LIMIT="${VULN_SCAN_SUMMARY_LIMIT:-${_v:-40}}"
_v=$(cfg VULN_SCAN_SKIP_DIRS);        SKIP_DIRS="${VULN_SCAN_SKIP_DIRS:-${_v:-.git,work,_dl,hfmodels,models,node_modules,__pycache__,.venv,venv,dist,build}}"
_v=$(cfg VULN_SCAN_RESULTS_DIR);      RESULTS_ROOT="${VULN_SCAN_RESULTS_DIR:-${_v:-$STACK_ROOT/work/vuln_scan_results}}"
# Slopsquatting tier (depsafe + sloppy-joe). Local images are built from
# docker/*.Dockerfile (pinned upstream versions) when not present.
_v=$(cfg VULN_SCAN_DEPSAFE_IMAGE);    DEPSAFE_IMAGE="${VULN_SCAN_DEPSAFE_IMAGE:-${_v:-vuln-scan-depsafe:local}}"
_v=$(cfg VULN_SCAN_SLOPPYJOE_IMAGE);  SLOPPYJOE_IMAGE="${VULN_SCAN_SLOPPYJOE_IMAGE:-${_v:-vuln-scan-sloppy-joe:local}}"
_v=$(cfg VULN_SCAN_SLOPSQUAT_ONLINE); SLOPSQUAT_ONLINE="${VULN_SCAN_SLOPSQUAT_ONLINE:-${_v:-0}}"

TS="$(date -u +%Y-%m-%dT%H-%MZ)"

die() { echo "vuln-scan: $*" >&2; exit 2; }

usage() {
  echo "Usage: vuln-scan repo <path>" >&2
  echo "       vuln-scan image <name>" >&2
  echo "       vuln-scan build" >&2
  exit 2
}

# Local scanner images (slopsquatting tier) are built from the Dockerfiles
# co-located with the skill: docker/<name>.Dockerfile -> vuln-scan-<name>:local.
local_dockerfile() { # <image> -> prints the Dockerfile path (returns 1 if none)
  _base=${1%:*}
  _name=${_base#vuln-scan-}
  _df="$DIR/../docker/$_name.Dockerfile"
  [ -f "$_df" ] || return 1
  printf '%s' "$_df"
}

build_local_image() { # <image>
  _df=$(local_dockerfile "$1") || die "no local Dockerfile for image $1"
  echo "vuln-scan: building $1 from $_df ..." >&2
  docker build -t "$1" -f "$_df" "$DIR/../docker/" || die "docker build failed: $1"
}

ensure_image() {
  docker image inspect "$1" >/dev/null 2>&1 && return 0
  echo "vuln-scan: pulling $1 ..." >&2
  if docker pull "$1" 2>/dev/null; then
    return 0
  fi
  # Not pullable from a registry — build a co-located local image if one exists.
  if local_dockerfile "$1" >/dev/null; then
    build_local_image "$1"
    return 0
  fi
  die "docker pull failed: $1"
}

# Semgrep's --exclude is a repeatable single-pattern flag — it does NOT accept
# a comma-separated list (that form is silently ignored). Expand the
# comma-separated SKIP_DIRS into one "--exclude <name>" per name. (Trivy's
# --skip-dirs DOES accept the comma form, so it keeps using $SKIP_DIRS directly.)
semgrep_excludes() {
  _sd=$SKIP_DIRS
  _out=""
  while [ -n "$_sd" ]; do
    _name=${_sd%%,*}
    [ -n "$_name" ] && _out="$_out --exclude $_name"
    case "$_sd" in
      *,*) _sd=${_sd#*,} ;;
      *) _sd="" ;;
    esac
  done
  printf '%s' "$_out"
}

# Semgrep's --config is a repeatable single-ruleset flag. Expand the
# comma-separated SEMGREP_RULESETS into one "--config <ruleset>" per entry
# (mirrors semgrep_excludes above).
semgrep_configs() {
  _rs=$SEMGREP_RULESETS
  _out=""
  while [ -n "$_rs" ]; do
    _name=${_rs%%,*}
    [ -n "$_name" ] && _out="$_out --config $_name"
    case "$_rs" in
      *,*) _rs=${_rs#*,} ;;
      *) _rs="" ;;
    esac
  done
  printf '%s' "$_out"
}

# run_python <json-file> <kind: trivy|semgrep|depsafe|sloppy-joe> — print the severity summary.
# Host python3 if present, else the semgrep image's python3 (dependency-free
# guarantee: sh + docker only).
run_python() {
  if command -v python3 >/dev/null 2>&1; then
    python3 - "$@"
  else
    docker run --rm -i "$SEMGREP_IMAGE" python3 - "$@"
  fi
}

summarize() { # <json-file> <kind>
  run_python "$1" "$2" "$SUMMARY_LIMIT" <<'PYEOF'
import json, sys

path, kind, limit = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    with open(path) as f:
        d = json.load(f)
except Exception as e:
    print(f"  (could not parse {path}: {e})")
    sys.exit(0)

ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
counts = {}
findings = []

if kind == "trivy":
    for r in d.get("Results") or []:
        target = r.get("Target", "?")
        for v in r.get("Vulnerabilities") or []:
            sev = (v.get("Severity") or "UNKNOWN").upper()
            counts[sev] = counts.get(sev, 0) + 1
            loc = f"{target}:{v.get('PkgName', '?')}"
            findings.append((sev, v.get("VulnerabilityID") or "?",
                             (v.get("Title") or "").replace("\n", " ")[:90], loc))
        for s in r.get("Secrets") or []:
            sev = (s.get("Severity") or "UNKNOWN").upper()
            counts[sev] = counts.get(sev, 0) + 1
            loc = f"{target}:{s.get('StartLine', '?')}"
            findings.append((sev, s.get("RuleID") or "?",
                             (s.get("Title") or "").replace("\n", " ")[:90], loc))
elif kind == "depsafe":
    # severity_counts: {critical,high,medium,low,info}; findings: [{name, rule,
    # rule_name, severity, message, file, ...}]
    for sev, n in (d.get("severity_counts") or {}).items():
        if n:
            counts[sev.upper()] = counts.get(sev.upper(), 0) + n
    for f in d.get("findings") or []:
        sev = (f.get("severity") or "info").upper()
        loc = f"{f.get('file', '?')}:{f.get('name', '?')}"
        msg = (f.get("message") or "").replace("\n", " ")[:90]
        findings.append((sev, f"{f.get('rule', '?')} {f.get('rule_name', '')}".strip(),
                         msg, loc))
elif kind == "semgrep":  # INFO/WARNING/ERROR -> LOW/MEDIUM/HIGH
    sevmap = {"INFO": "LOW", "WARNING": "MEDIUM", "ERROR": "HIGH"}
    for r in d.get("results") or []:
        extra = r.get("extra") or {}
        sev = sevmap.get(extra.get("severity") or "INFO", "LOW")
        counts[sev] = counts.get(sev, 0) + 1
        p = r.get("path", "?")
        if p.startswith("/src/"):
            p = p[len("/src/"):]
        loc = f"{p}:{(r.get('start') or {}).get('line', '?')}"
        msg = (extra.get("message") or "").replace("\n", " ")[:90]
        findings.append((sev, r.get("check_id") or "?", msg, loc))
else:  # sloppy-joe: issues: [{package, check, severity(Error|Warning), message}]
    sevmap = {"ERROR": "HIGH", "WARNING": "MEDIUM"}
    for i in d.get("issues") or []:
        sev = sevmap.get((i.get("severity") or "WARNING").upper(), "MEDIUM")
        counts[sev] = counts.get(sev, 0) + 1
        loc = i.get("package", "?")
        msg = (i.get("message") or "").replace("\n", " ")[:90]
        findings.append((sev, i.get("check") or "?", msg, loc))

parts = [f"{k}: {counts[k]}" for k in ORDER if k in counts]
parts += [f"{k}: {counts[k]}" for k in sorted(counts) if k not in ORDER]
print(f"  severity — {', '.join(parts) if parts else 'none'}")

rank = {k: i for i, k in enumerate(ORDER)}
findings.sort(key=lambda f: (rank.get(f[0], 99), f[3]))
LIMIT = int(limit)
for sev, fid, title, loc in findings[:LIMIT]:
    print(f"  [{sev}] {fid} — {title} ({loc})")
if len(findings) > LIMIT:
    print(f"  ... and {len(findings) - LIMIT} more (see JSON report)")
PYEOF
}

# scan <label> <docker-image> <out-file-in-container> <out-dir> <cmd...>
# Runs the scanner, captures its exit code (never aborts), renames the JSON
# to <TS>-<label>.json, and summarizes it. Returns 0 if a report exists.
# Report source: the mounted file <out-dir>/<cfile> if the scanner wrote one
# (trivy -o, semgrep --json-output); otherwise the scanner's stdout if it is
# JSON (depsafe --json, sloppy-joe --json).
scan() {
  label=$1; image=$2; cfile=$3; outdir=$4; shift 4
  ensure_image "$image"
  echo "vuln-scan: running $label ($image) ..." >&2
  # stdout is captured (JSON for stdout-based scanners; progress logs for
  # file-based ones, discarded); stderr passes through so scanner errors are
  # visible. The summary below is the canonical output.
  docker run --rm -i "$@" >"$outdir/.$label.stdout"
  rc=$?
  base="${cfile#/out/}"
  if [ -f "$outdir/$base" ]; then
    mv "$outdir/$base" "$outdir/$TS-$label.json"
    rm -f "$outdir/.$label.stdout"
    echo "vuln-scan: [$label] exit=$rc report -> $outdir/$TS-$label.json" >&2
    return 0
  fi
  # stdout-based scanner: accept the capture only if it looks like JSON —
  # the first non-whitespace char must be '{' or '[' (a bare '{' anywhere in
  # the first 200 bytes is not enough; progress logs can contain braces).
  _first=$(head -c 200 "$outdir/.$label.stdout" 2>/dev/null | tr -d '[:space:]' | head -c 1)
  if [ -s "$outdir/.$label.stdout" ] && { [ "$_first" = "{" ] || [ "$_first" = "[" ]; }; then
    mv "$outdir/.$label.stdout" "$outdir/$TS-$label.json"
    echo "vuln-scan: [$label] exit=$rc report -> $outdir/$TS-$label.json" >&2
    return 0
  fi
  rm -f "$outdir/.$label.stdout"
  echo "vuln-scan: [$label] exit=$rc, NO report produced (scanner error; see stderr above)" >&2
  return 1
}

cmd=${1:-}
target=${2:-}
[ -n "$cmd" ] || usage
[ "$cmd" = "build" ] || [ -n "$target" ] || usage

case "$cmd" in
  repo)
    [ -d "$target" ] || die "not a directory: $target"
    short=$(basename "$target" | tr ':/' '--')
    outdir="$RESULTS_ROOT/$short"
    mkdir -p "$outdir" || die "cannot create $outdir"
    echo "vuln-scan: repo=$short out=$outdir ts=$TS"

    # Slopsquatting tier mode: offline by default; online (registry
    # existence / OSV.dev, package names only) is opt-in.
    if [ "$SLOPSQUAT_ONLINE" = "1" ]; then
      _sq_mode=online
    else
      _sq_mode=offline
    fi

    ok=0
    scan trivy "$TRIVY_IMAGE" trivy.json "$outdir" \
      -v "$target:/src:ro" -v "$outdir:/out" \
      "$TRIVY_IMAGE" fs \
      --scanners "$TRIVY_SCANNERS" \
      --severity "$TRIVY_SEVERITY" \
      --quiet --disable-telemetry --skip-version-check \
      --skip-dirs "$SKIP_DIRS" \
      --format json -o /out/trivy.json /src && ok=1

    scan semgrep "$SEMGREP_IMAGE" semgrep.json "$outdir" \
      -v "$target:/src:ro" -v "$outdir:/out" \
      "$SEMGREP_IMAGE" semgrep scan \
      $(semgrep_configs) \
      --metrics off --quiet \
      $(semgrep_excludes) \
      --json-output /out/semgrep.json /src && ok=1

    # depsafe: Python typosquatting / slopsquatting (built-in corpus; offline
    # by default, --online = PyPI name queries). JSON on stdout.
    _depsafe_args="--json --no-color /src"
    [ "$SLOPSQUAT_ONLINE" = "1" ] && _depsafe_args="$_depsafe_args --online"
    scan depsafe "$DEPSAFE_IMAGE" depsafe.json "$outdir" \
      -v "$target:/src:ro" -v "$outdir:/out" \
      "$DEPSAFE_IMAGE" $_depsafe_args && ok=1

    # sloppy-joe: 8-ecosystem slopsquatting / typosquatting / provenance.
    # check = fast offline guardrail (manifest, lockfile/sync, provenance,
    # canonical); --full = online tier (registry existence + similarity +
    # OSV.dev). Config is mounted from the skill dir (never from the scanned
    # repo — the tool refuses in-repo config by design). JSON on stdout.
    _sj_args="check --json --dir /src --config /config/sloppy-joe-default-config.json --cache-dir /cache"
    [ "$SLOPSQUAT_ONLINE" = "1" ] && _sj_args="$_sj_args --full"
    mkdir -p "$RESULTS_ROOT/.cache/sloppy-joe" 2>/dev/null || true
    scan sloppy-joe "$SLOPPYJOE_IMAGE" sloppy-joe.json "$outdir" \
      -v "$target:/src:ro" -v "$outdir:/out" \
      -v "$DIR/../docker:/config:ro" \
      -v "$RESULTS_ROOT/.cache/sloppy-joe:/cache" \
      "$SLOPPYJOE_IMAGE" $_sj_args && ok=1

    [ "$ok" = 1 ] || die "no reports produced (all scanners failed)"

    echo ""
    echo "== vuln-scan: $short =="
    for f in "$outdir/$TS-trivy.json" "$outdir/$TS-semgrep.json" \
             "$outdir/$TS-depsafe.json" "$outdir/$TS-sloppy-joe.json"; do
      [ -f "$f" ] || continue
      case "$f" in
        *trivy.json) echo "[trivy: $TRIVY_SCANNERS]"; summarize "$f" trivy ;;
        *semgrep.json) echo "[semgrep: SAST $SEMGREP_RULESETS]"; summarize "$f" semgrep ;;
        *depsafe.json) echo "[depsafe: Python typosquat/slopsquat, $_sq_mode]"; summarize "$f" depsafe ;;
        *) echo "[sloppy-joe: 8-ecosystem slopsquat/provenance, $_sq_mode]"; summarize "$f" sloppy-joe ;;
      esac
    done
    echo ""
    echo "Reports: $outdir/$TS-*.json"
    ;;

  build)
    # Build the local slopsquatting scanner images from docker/*.Dockerfile.
    build_local_image "$DEPSAFE_IMAGE"
    build_local_image "$SLOPPYJOE_IMAGE"
    echo "vuln-scan: local scanner images ready ($DEPSAFE_IMAGE, $SLOPPYJOE_IMAGE)"
    ;;

  image)
    # sanitize: image names contain ':' which breaks docker -v src:dst parsing
    short=$(basename "$target" | tr ':/' '--')
    outdir="$RESULTS_ROOT/$short"
    mkdir -p "$outdir" || die "cannot create $outdir"
    [ -S /var/run/docker.sock ] || die "docker.sock not found (image scan needs the docker daemon)"
    echo "vuln-scan: image=$short out=$outdir ts=$TS"

    ok=0
    scan trivy-image "$TRIVY_IMAGE" trivy-image.json "$outdir" \
      -v /var/run/docker.sock:/var/run/docker.sock -v "$outdir:/out" \
      "$TRIVY_IMAGE" image "$target" \
      --severity "$TRIVY_SEVERITY" \
      --quiet --disable-telemetry --skip-version-check \
      --format json -o /out/trivy-image.json && ok=1

    [ "$ok" = 1 ] || die "no report produced (trivy image failed)"

    echo ""
    echo "== vuln-scan image: $short =="
    echo "[trivy: image vuln]"
    summarize "$outdir/$TS-trivy-image.json" trivy
    echo ""
    echo "Reports: $outdir/$TS-trivy-image.json"
    ;;

  *) usage ;;
esac
