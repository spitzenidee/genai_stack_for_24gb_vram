#!/usr/bin/env bash
# probe_suite.sh — deterministic GROMACS KB-audit probe suite
#
# One command -> full build snapshot + mechanical claim extraction from the
# LIVE knowledge base. Everything is regenerated on every run; nothing
# KB-derived is stored in the skill.
#
# Probe model:
#   - Every fenced MDP code block in the KB is probed AS-IS (it carries its
#     own parent options) -> per-block verdicts.
#   - A merged top-level existence matrix (all unique non-context-dependent
#     options, first value) -> one consolidated existence answer.
#   - CLI claims (fenced lines + inline `gmx ...` spans) -> mapped by the
#     auditor against snapshot/02_help/<tool>.txt.
#   No GROMACS API knowledge is hardcoded here: contexts and parent values
#   come from the KB blocks themselves.
#
# Usage:
#   bash probe_suite.sh            # full run (build snapshot + claims + probes)
#   bash probe_suite.sh build      # build snapshot only
#   bash probe_suite.sh claims     # claim extraction + MDP probes only
#
# Container model: every probe runs in a TRANSIENT container
# (docker run --rm) with the session dir mounted at /work. CPU-only by
# construction — no GPU devices are ever passed — so the suite is safe in
# ANY eGPU stack mode and never requires a running container or a mode
# switch (switching modes would rugpull the agent's own compute).
#
# Env overrides:
#   STACK_ROOT  (default /home/<user>/docker/genai_stack)
#   KB_DIR      (default $STACK_ROOT/.pi/skills/gromacs-sim/knowledge)
#   IMAGE       (default gromacs-hip-gfx1100:latest)
#   SESSION_DIR (default $STACK_ROOT/gromacs/work/kb-audit; must stay under
#                gromacs/work; the suite mounts it at /work in each
#                transient container)
#
# Outputs: $SESSION_DIR (transient container: /work)
#   — the session dir is wiped and regenerated on EVERY run: no cross-run
#     persistence. The only durable state is knowledge/issues_kb.md.
#   — session dir layout (snapshot/, claims/, blocks/, matrix/) is
#   documented in SKILL.md step 1; probe assets + traps: assets/README.md.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
ASSETS="$SKILL_DIR/assets"

STACK_ROOT="${STACK_ROOT:-/home/<user>/docker/genai_stack}"
KB_DIR="${KB_DIR:-$STACK_ROOT/.pi/skills/gromacs-sim/knowledge}"
IMAGE="${IMAGE:-gromacs-hip-gfx1100:latest}"

log() { echo "[probe-suite] $*"; }
die() { echo "[probe-suite] ERROR: $*" >&2; exit 1; }

SESSION_HOST="${SESSION_DIR:-$STACK_ROOT/gromacs/work/kb-audit}"
case "$SESSION_HOST" in
  "$STACK_ROOT"/gromacs/work/*) : ;;
  *) die "SESSION_DIR must be under $STACK_ROOT/gromacs/work (the projects dir)" ;;
esac
SNAP="$SESSION_HOST/snapshot"
CLAIMS="$SESSION_HOST/claims"
BLOCKS="$SESSION_HOST/blocks"
MATRIX="$SESSION_HOST/matrix"
# All container access is transient (docker run --rm) and CPU-only by
# construction: no GPU devices are ever passed, so this is safe in ANY stack
# mode and never touches the eGPU. No long-running container, no mode switch,
# no "start" step. The session dir is mounted at /work (the -w), so relative
# paths resolve inside it.
ctr() { docker run --rm -w /work -v "$SESSION_HOST":/work "$IMAGE" "$@"; }
gmx() { ctr gmx "$@"; }
# NOTE: grep -c inside $( ) must ALWAYS get an explicit file argument —
# a bare grep reads the loop's stdin and silently eats the manifest.
count() { # count <pattern> <file>   (grep -c, never stdin)
  [ $# -eq 2 ] || { echo "count: usage count <pattern> <file>" >&2; return 2; }
  grep -c "$1" "$2" 2>/dev/null || true
}

# --- image check (no running container needed — probes are transient) --------
docker image inspect "$IMAGE" >/dev/null 2>&1 \
  || die "image $IMAGE not found. Tell the user to build it (cd $STACK_ROOT && docker compose build gromacs-rocm). Do NOT switch the eGPU stack mode (make ...) — that would rugpull your own compute."

# --- fresh session dir (no cross-run persistence) -----------------------------
# Wipe inside a transient container: leftovers from older runs may be
# root-owned (the container writes as root) and a host-side rm would fail on
# them. mkdir on the HOST first: the bind target must exist and stay
# host-user-owned (a root-owned dir would block host-side cp/mkdir, while
# root writes fine into a host-user-owned dir).
mkdir -p "$SESSION_HOST"
log "wiping session dir: $SESSION_HOST"
ctr sh -c 'find /work -mindepth 1 -delete' \
  || die "session dir wipe failed: $SESSION_HOST"

# --- build snapshot -----------------------------------------------------------
run_build() {
  mkdir -p "$SNAP/02_help"
  rm -f "$SNAP/02_help"/*.txt   # stale tools from a previous build
  cp "$ASSETS/tmin.gro" "$ASSETS/tmin.top" "$ASSETS/probe.gro" "$ASSETS/probe.top" "$SESSION_HOST/"

  log "00: version + fingerprint"
  gmx --version > "$SNAP/00_version.txt" 2>&1
  sed -n 's/.*gmx, \([^ (]*\).*/\1/p' "$SNAP/00_version.txt" | head -1 \
    > "$SNAP/fingerprint.txt"

  log "01: command inventory"
  gmx help commands > "$SNAP/01_commands.txt" 2>&1
  grep -E '^    [a-z]' "$SNAP/01_commands.txt" | awk '{print $1}' \
    | sort -u > "$SNAP/01_command_names.txt"
  log "   $(wc -l < "$SNAP/01_command_names.txt") commands"
  [ -s "$SNAP/01_command_names.txt" ] || die "command inventory is empty — 'gmx help commands' output format may have changed; inspect $SNAP/01_commands.txt"

  log "02: help dumps for all commands"
  local tool
  while read -r tool; do
    gmx "$tool" -h > "$SNAP/02_help/$tool.txt" 2>&1 </dev/null
  done < "$SNAP/01_command_names.txt"
  log "   $(ls "$SNAP/02_help" | wc -l) help files"

  log "03: force field / water listing (top level + .ff subdirs)"
  {
    echo "# top level"
    ctr ls /usr/local/gromacs/share/gromacs/top/
    echo "# .ff subdirectories (water models / ions live here)"
    ctr sh -c \
      'for d in /usr/local/gromacs/share/gromacs/top/*.ff; do [ -d "$d" ] || continue; echo "## $(basename "$d")"; ls "$d"; done'
  } > "$SNAP/03_ff_listing.txt" 2>&1

  log "04: GMX_* environment variables"
  ctr sh -c \
    'strings /usr/local/gromacs/lib/libgromacs.so | grep -o "GMX_[A-Z0-9_]*" | sort -u' \
    > "$SNAP/04_envvars.txt" 2>&1

  log "05: install tree (maxdepth 3)"
  ctr find /usr/local/gromacs -maxdepth 3 | sort \
    > "$SNAP/05_install_tree.txt" 2>&1

  log "build snapshot complete: $SNAP"
}

# --- claim extraction (from the LIVE KB) + MDP probes --------------------------
run_claims() {
  [ -d "$KB_DIR" ] || die "KB dir not found: $KB_DIR"
  mkdir -p "$SNAP" "$CLAIMS" "$BLOCKS" "$MATRIX"
  cp "$ASSETS/tmin.gro" "$ASSETS/tmin.top" "$ASSETS/probe.gro" "$ASSETS/probe.top" "$SESSION_HOST/"

  local kb_files
  # issues_kb.md is excluded: it is the historical findings log (its fenced
  # blocks are evidence of PAST issues, not current claims).
  kb_files=$(find "$KB_DIR" -name '*.md' -type f ! -name 'issues_kb.md' | sort)
  log "extracting mechanical claims from live KB ($(echo "$kb_files" | wc -l) files)"

  # --- MDP option claims: fenced 'option = value' lines + inline spans --------
  {
    awk '
      /^ {0,3}```/ { fence = !fence; next }
      fence && /^[[:space:]]*[a-z][a-z0-9-]*[[:space:]]*=/ {
        line = $0
        sub(/^[[:space:]]+/, "", line)
        eq = index(line, "=")
        opt = substr(line, 1, eq - 1); gsub(/[[:space:]]+$/, "", opt)
        val = substr(line, eq + 1);    gsub(/^[[:space:]]+/, "", val); gsub(/[[:space:]]+$/, "", val)
        printf "%s:%d: %s = %s\n", FILENAME, FNR, opt, val
      }
    ' $kb_files
    # inline code spans in prose: `option = value`
    awk '
      {
        rest = $0
        while (match(rest, /`[a-z][a-z0-9-]*[[:space:]]*=[^`]+`/)) {
          span = substr(rest, RSTART + 1, RLENGTH - 2)
          rest = substr(rest, RSTART + RLENGTH)
          eq = index(span, "=")
          opt = substr(span, 1, eq - 1); gsub(/[[:space:]]+$/, "", opt)
          val = substr(span, eq + 1);    gsub(/^[[:space:]]+/, "", val); gsub(/[[:space:]]+$/, "", val)
          printf "%s:%d: %s = %s\n", FILENAME, FNR, opt, val
        }
      }
    ' $kb_files
  } | sort -u > "$CLAIMS/mdp_options_raw.txt"

  # Stripped (matrix input), deduped, multi-value.
  awk '{ sub(/^[^:]+:[0-9]+: /, ""); print }' "$CLAIMS/mdp_options_raw.txt" \
    > "$CLAIMS/mdp_options_stripped.txt"
  awk '{ eq = index($0, "="); opt = substr($0, 1, eq - 1); gsub(/[[:space:]]+$/, "", opt)
         if (!(opt in seen)) { seen[opt] = 1; print } }' \
    "$CLAIMS/mdp_options_stripped.txt" > "$CLAIMS/mdp_options_unique.txt"
  awk '{ eq = index($0, "="); opt = substr($0, 1, eq - 1); gsub(/[[:space:]]+$/, "", opt)
         val = substr($0, eq + 1); gsub(/^[[:space:]]+/, "", val)
         key = opt SUBSEP val
         if (!(key in seenval)) { seenval[key] = 1; n[opt]++; vals[opt] = vals[opt] " " val } }
       END { for (o in n) if (n[o] > 1) print o ":" vals[o] }' \
    "$CLAIMS/mdp_options_stripped.txt" | sort > "$CLAIMS/mdp_multi_value.txt"

  # --- per-block MDP probes (each KB fenced MDP block probed as-is) -----------
  # clean stale probes from a same-day re-run
  rm -f "$BLOCKS"/block_*.mdp "$BLOCKS"/block_*.log "$BLOCKS"/block_*.tpr
  : > "$CLAIMS/blocks_manifest.txt"
  awk -v MANIFEST="$CLAIMS/blocks_manifest.txt" -v OUTDIR="$BLOCKS" '
    function rel(p) { sub(/.*\/knowledge\//, "", p); return p }
    /^ {0,3}```/ {
      if (fence) {
        fence = 0
        if (n > 0) {
          printf "block_%03d.mdp  %s:%d-%d\n", count, rel(FILENAME), start, FNR - 1 >> MANIFEST
          close(BUF)
        }
        n = 0
      } else fence = 1
      next
    }
    fence {
      line = $0
      if (line ~ /^[[:space:]]*[a-z][a-z0-9-]*[[:space:]]*=/) {
        if (n == 0) {
          count++
          start = FNR
          BUF = OUTDIR "/block_" sprintf("%03d", count) ".mdp"
          printf "; KB block %s:%d (generated by probe_suite.sh)\n", rel(FILENAME), start > BUF
        }
        n++
        print line > BUF
      } else if (line ~ /^[[:space:]]*;/ && n > 0) {
        print line > BUF
      }
    }
    END {
      if (fence && n > 0) {
        printf "block_%03d.mdp  %s:%d-%d\n", count, rel(FILENAME), start, FNR >> MANIFEST
        close(BUF)
      }
    }
  ' $kb_files

  # --- CLI claims: fenced 'gmx ...' lines + inline `gmx ...` spans ------------
  awk '
    function emit(cmd,   n, tok, i, flags) {
      sub(/^[[:space:]]+/, "", cmd)
      sub(/^.*exec[[:space:]]+[^[:space:]]+[[:space:]]+/, "", cmd)
      sub(/#.*/, "", cmd)
      sub(/\\.*$/, "", cmd)
      n = split(cmd, tok, /[[:space:]]+/)
      if (n < 2) return
      flags = ""
      for (i = 3; i <= n; i++) if (tok[i] ~ /^-/) flags = flags " " tok[i]
      sub(/^ /, "", flags)
      printf "%s:%d: gmx %s %s\n", FILENAME, FNR, tok[2], flags
    }
    /^ {0,3}```/ { fence = !fence }
    {
      rest = $0
      while (match(rest, /`gmx [^`]+`/)) {
        emit(substr(rest, RSTART + 1, RLENGTH - 2))
        rest = substr(rest, RSTART + RLENGTH)
      }
      if (fence && $0 ~ /^[[:space:]]*gmx[[:space:]]/) emit($0)
    }
  ' $kb_files | sort -u > "$CLAIMS/cli_commands.txt"
   awk '{print $3}' "$CLAIMS/cli_commands.txt" | sort -u > "$CLAIMS/cli_tools.txt"

  # --- topology directive claims: fenced '[ dir ]' lines + inline spans --------
  # Context inference: 'mt' while a '[ moleculetype ]' header is open in the
  # same fence (cleared by '[ system ]'); 'top' otherwise; 'any' for inline
  # spans (name claims without positional context).
  awk '
    function rel(p) { sub(/.*\/knowledge\//, "", p); return p }
    /^ {0,3}```/ { fence = !fence; mtopen = 0; next }
    fence && $0 ~ /^[[:space:]]*\[ ?[a-z0-9_]+ *\]/ {
      d = $0
      sub(/^[[:space:]]*\[ ?/, "", d); sub(/[[:space:]]*\].*$/, "", d)
      printf "%s:%d: %s ctx=%s\n", rel(FILENAME), FNR, d, (mtopen ? "mt" : "top")
      if (d == "moleculetype") mtopen = 1
      if (d == "system") mtopen = 0
    }
    {
      rest = $0
      while (match(rest, /`\[ ?[a-z0-9_]+ *\]`/)) {
        span = substr(rest, RSTART + 1, RLENGTH - 2)
        d = span; sub(/^\[ ?/, "", d); sub(/[[:space:]]*\].*$/, "", d)
        printf "%s:%d: %s ctx=any\n", rel(FILENAME), FNR, d
        rest = substr(rest, RSTART + RLENGTH)
      }
    }
  ' $kb_files | sort -u > "$CLAIMS/directives_raw.txt"
  awk '{ print $2 }' "$CLAIMS/directives_raw.txt" | sort -u > "$CLAIMS/directives_unique.txt"

  # --- directive probes: name (stage A) + usability (stage B) ------------------
  # Stage A (assets/dir_probe_a.tpl): the directive at LINE 1. An unknown name
  # there always yields 'Invalid directive <name>' (verified 2026.3); a known
  # name yields any other signal — never that message. Stage B
  # (assets/dir_probe_b.tpl): canonical position (after the moleculetype, before
  # [ system ]); known names only — exit 0 = usable there, 'Invalid order for
  # directive <name>' = not usable there. TRAP: grompp 2026.3 SILENTLY ignores
  # an unknown directive at the end of a moleculetype (exit 0), so stage B is
  # never used for name verdicts (assets/README.md).
  mkdir -p "$SESSION_HOST/directives"
  cp "$ASSETS/base.mdp" "$SESSION_HOST/"
  local d refs
  : > "$SNAP/06_directive_verdicts.txt"
  {
    echo "# directive probe verdicts (generated by probe_suite.sh)"
    echo "# A=known|unknown (name check, directive at line 1); B=ok|order|other|skipped"
    echo "# (usability at the canonical position; known names only; 'other' ="
    echo "# unexpected signal — read directives/<name>_b.log)."
  } >> "$SNAP/06_directive_verdicts.txt"

  # controls (self-healing: a parser-behavior change dies the suite, not a
  # silent pass)
  local ctl
  sed 's/%DIR%/[ bondtyps ]/' "$ASSETS/dir_probe_a.tpl" > "$SESSION_HOST/directives/ctl_bad.top"
  ctr gmx grompp -f base.mdp -c tmin.gro \
    -p directives/ctl_bad.top -o directives/ctl_bad.tpr \
    > "$SESSION_HOST/directives/ctl_bad.log" 2>&1 </dev/null
  grep -q "Invalid directive bondtyps" "$SESSION_HOST/directives/ctl_bad.log" \
    || die "ctl_bad: expected 'Invalid directive bondtyps' — parser behavior changed? inspect directives/ctl_bad.log"
  sed 's/%DIR%/[ bonds ]/' "$ASSETS/dir_probe_b.tpl" > "$SESSION_HOST/directives/ctl_good.top"
  ctr gmx grompp -f base.mdp -c tmin.gro \
    -p directives/ctl_good.top -o directives/ctl_good.tpr \
    > "$SESSION_HOST/directives/ctl_good.log" 2>&1 </dev/null
  [ $? -eq 0 ] || die "ctl_good: '[ bonds ]' at the canonical position must parse — inspect directives/ctl_good.log"

  while read -r d; do
    [ -n "$d" ] || continue
    refs=$(grep -E "^[^:]+:[0-9]+: $d ctx=" "$CLAIMS/directives_raw.txt" \
      | awk -F': ' '{print $1}' | head -5 | tr '\n' ',' | sed 's/,$//')
    sed "s/%DIR%/[ $d ]/" "$ASSETS/dir_probe_a.tpl" > "$SESSION_HOST/directives/${d}_a.top"
    ctr gmx grompp -f base.mdp -c tmin.gro \
      -p "directives/${d}_a.top" -o "directives/${d}_a.tpr" \
      > "$SESSION_HOST/directives/${d}_a.log" 2>&1 </dev/null
    if grep -q "Invalid directive $d" "$SESSION_HOST/directives/${d}_a.log"; then
      a="unknown"
    else
      a="known"
    fi
    if [ "$a" = "known" ]; then
      sed "s/%DIR%/[ $d ]/" "$ASSETS/dir_probe_b.tpl" > "$SESSION_HOST/directives/${d}_b.top"
      ctr gmx grompp -f base.mdp -c tmin.gro \
        -p "directives/${d}_b.top" -o "directives/${d}_b.tpr" \
        > "$SESSION_HOST/directives/${d}_b.log" 2>&1 </dev/null
      if [ $? -eq 0 ]; then
        b="ok"
      elif grep -q "Invalid order for directive $d" "$SESSION_HOST/directives/${d}_b.log"; then
        b="order"
      else
        b="other"
      fi
    else
      b="skipped"
    fi
    echo "$d  A=$a  B=$b  refs=$refs" >> "$SNAP/06_directive_verdicts.txt"
  done < "$CLAIMS/directives_unique.txt"
  log "   $(wc -l < "$CLAIMS/directives_unique.txt") directives probed"

  # --- context header: let fragment blocks pass grompp's system checks --------
  # GROMACS hard-errors on doubly-defined parameters, so only add options the
  # block does not define itself. Without a finite ensemble temperature the
  # Verlet buffer is computed at -nan K and grompp aborts (system noise, not an
  # option-parsing problem).
  # Context parents: child options (pull-coordN-*, awh1-*, sc-*, ...) are
  # rejected as unknown unless their parent is in the same MDP. Delta blocks
  # that omit the parent get it injected here so the block verdict stays a
  # parse signal, not a context artifact. (nnpot-*/qmmm-cp2k-* are excluded:
  # the build aborts without LibTorch/CP2K — probe names only.)
  local f o v hdr
  for f in "$BLOCKS"/block_*.mdp; do
    [ -f "$f" ] || continue
    hdr=""
    # gen-vel/continuation default to NO (fresh, non-continuing run): injecting
    # gen-vel=yes + continuation=yes is a hard grompp error that would mask the
    # block's real verdict. A block defining BOTH stays broken (genuine KB bug,
    # correctly flagged); a block defining only one gets the other as no.
    # NOTE: do NOT inject ref-t — it is only valid under group T-coupling
    # (tcoupl=yes + tc-grps). Injecting it into a block without T-coupling
    # creates a spurious "0 groups, 1 ref-t values" mismatch. C-rescale blocks
    # that lack an ensemble temperature are a documented probe limitation.
    for pair in "nsteps 100" "dt 0.002" "gen-vel no" "continuation no"; do
      o="${pair%% *}"; v="${pair##* }"
      if ! grep -qE "^[[:space:]]*${o}[[:space:]]*=" "$f"; then
        hdr="${hdr}${o} = ${v}\n"
      fi
    done
    add_parent() { # $1=child-pattern $2..=parent pairs
      local pat="$1"; shift
      if grep -qE "$pat" "$f"; then
        for pair in "$@"; do
          o="${pair%% *}"; v="${pair##* }"
          if ! grep -qE "^[[:space:]]*${o}[[:space:]]*=" "$f"; then
            hdr="${hdr}${o} = ${v}\n"
          fi
        done
      fi
    }
    add_parent '^[[:space:]]*pull-(coord[0-9]+|group[0-9]+)-' \
      "pull yes" "pull-ncoords 1" "pull-ngroups 2"
    add_parent '^[[:space:]]*awh[0-9]+-' "awh yes"
    add_parent '^[[:space:]]*(sc-|couple-|dhdl-|init-lambda|coul-lambdas|vdw-lambdas)' "free-energy yes"
    add_parent '^[[:space:]]*colvars-' "colvars-active yes"
    add_parent '^[[:space:]]*fmm-' "coulombtype FMM"
    if [ -n "$hdr" ]; then
      {
        printf '; context header added by probe_suite.sh (options the KB block does not define)\n'
        printf '%b' "$hdr"
        printf '; --- KB block below ---\n'
        cat "$f"
      } > "$f.tmp" && mv "$f.tmp" "$f"
    fi
  done

  # --- run block probes --------------------------------------------------------
  log "running per-block MDP probes against the build"
  local blockid ref rc unknown invalid obsolete fatal errors notes
  : > "$SNAP/03_block_verdicts.txt"
  while read -r blockid ref; do
    [ -f "$BLOCKS/$blockid" ] || continue
    # Probe against the protein+water asset (probe.gro/probe.top), NOT the
    # 1-atom DUM: a real Protein + Non-Protein system is required for the
    # T-coupling count check to fire (issues_agent_run.md A4). -maxwarn 5 lets
    # benign minimal-system warnings through while hard fatals (T-coupling,
    # atom mismatch, unknown option) still fatal.
    ctr gmx grompp -f "blocks/$blockid" -c probe.gro -p probe.top \
      -o "blocks/$blockid.tpr" -maxwarn 5 > "$BLOCKS/$blockid.log" 2>&1 </dev/null
    rc=$?
    logf="$BLOCKS/$blockid.log"
    unknown=$(grep -c "Unknown left-hand" "$logf" 2>/dev/null || true)
    invalid=$(grep -c "Invalid enum" "$logf" 2>/dev/null || true)
    obsolete=$(grep -c "Ignoring obsolete" "$logf" 2>/dev/null || true)
    fatal=$(grep -c "Fatal error" "$logf" 2>/dev/null || true)
    errors=$(grep -cE "^ERROR [0-9]" "$logf" 2>/dev/null || true)
    notes=$(grep -cE "^NOTE [0-9]" "$logf" 2>/dev/null || true)
    echo "$blockid ($ref) exit=$rc unknown=$unknown invalid=$invalid obsolete=$obsolete fatal=$fatal errors=$errors notes=$notes" \
      >> "$SNAP/03_block_verdicts.txt"
    # Needs-attention trigger: ANY of a non-zero exit, a Fatal error, or a
    # parse signal (unknown/invalid/obsolete). A semantic grompp fatal (e.g.
    # T-coupling count mismatch) exits non-zero WITHOUT a parse signal, so
    # rc/fatal must be part of the trigger (issues_agent_run.md A4).
    if [ "${rc:-0}" -ne 0 ] || [ "${fatal:-0}" -gt 0 ] || [ "${unknown:-0}" -gt 0 ] || [ "${invalid:-0}" -gt 0 ] || [ "${obsolete:-0}" -gt 0 ]; then
      {
        echo "--- $blockid details:"
        grep -nE "Unknown left-hand|Invalid enum|Ignoring obsolete|Fatal error|Invalid T coupling|does not match" "$logf" | head -40
      } >> "$SNAP/03_block_verdicts.txt"
    fi
  done < "$CLAIMS/blocks_manifest.txt"
  log "   $(wc -l < "$CLAIMS/blocks_manifest.txt") blocks probed"

  # --- merged top-level existence matrix ---------------------------------------
  # Context-dependent options (need a parent in the same MDP) are excluded:
  # they are covered by the per-block probes, which carry the KB's own parents.
  #
  # BUILD-PINNED CONVENTION (hardcoded, NOT derived from the build): the prefix
  # list below is a manual enumeration of context-dependent option families. It
  # is a superset heuristic — a missed prefix just leaves an option in the
  # matrix (harmless: it fails there and is still covered by its per-block
  # probe); a stale prefix only over-excludes (also harmless, per-block covers
  # it). Review this list when the build changes and new context-dependent
  # families appear.
  {
    echo "; merged top-level existence matrix (generated by probe_suite.sh)"
    grep -vE '^(pull-|awh-|sc-|dhdl-|couple-|init-lambda|lmc-|nnpot-|colvars-|fmm-|qmmm-cp2k-|rot-)' \
      "$CLAIMS/mdp_options_unique.txt"
  } > "$MATRIX/base.mdp"
  for f in "$MATRIX/base.mdp"; do
    hdr=""
    # gen-vel/continuation default to NO (see block-probe header above).
    for pair in "nsteps 100" "dt 0.002" "gen-vel no" "continuation no"; do
      o="${pair%% *}"; v="${pair##* }"
      if ! grep -qE "^[[:space:]]*${o}[[:space:]]*=" "$f"; then
        hdr="${hdr}${o} = ${v}\n"
      fi
    done
    if [ -n "$hdr" ]; then
      { printf '; context header added by probe_suite.sh\n'; printf '%b' "$hdr"; cat "$f"; } > "$f.tmp" && mv "$f.tmp" "$f"
    fi
  done
  ctr gmx grompp -f matrix/base.mdp -c tmin.gro -p tmin.top \
    -o matrix/base.tpr > "$MATRIX/base.log" 2>&1
  {
    echo "=== merged top-level matrix (grompp exit=$?, option lines: $(grep -c '=' "$MATRIX/base.mdp" || true), log: matrix/base.log)"
    grep -nE "Unknown left-hand|Invalid enum|Ignoring obsolete|Fatal error|Invalid T coupling|does not match" "$MATRIX/base.log" | head -80
  } > "$SNAP/03_matrix_verdicts.txt"

  {
    echo "generated: $(date -Is)"
    echo "kb_dir: $KB_DIR"
    echo "files scanned: $(echo "$kb_files" | wc -l)"
    echo "mdp option claims (raw, unique lines): $(wc -l < "$CLAIMS/mdp_options_raw.txt")"
    echo "unique mdp options: $(wc -l < "$CLAIMS/mdp_options_unique.txt")"
    echo "multi-value options (need targeted value probes): $(wc -l < "$CLAIMS/mdp_multi_value.txt")"
    echo "mdp blocks probed: $(wc -l < "$CLAIMS/blocks_manifest.txt")"
    echo "cli command claims (unique): $(wc -l < "$CLAIMS/cli_commands.txt")"
    echo "cli tools referenced: $(wc -l < "$CLAIMS/cli_tools.txt")"
    echo "topology directive claims (raw, unique lines): $(wc -l < "$CLAIMS/directives_raw.txt")"
    echo "unique directives probed: $(wc -l < "$CLAIMS/directives_unique.txt")"
    echo ""
    echo "SCOPE: claims/ is the mechanical floor (fenced blocks + inline code"
    echo "spans). Table cells and plain-prose claims are NOT extracted; the"
    echo "auditor reads the KB for those (SKILL.md step 2). issues_kb.md is"
    echo "excluded (historical log, not current claims)."
    echo "Known false-positive classes — judge by the file:line reference"
    echo "before filing: (a) inline 'x = y' prose that is not MDP (CLI flag"
    echo "discussions; topology/pull directives like 'nrexcl', 'fc', pull"
    echo "section 'type' — those need topology-level probes, not MDP ones);"
    echo "(b) README changelog spans documenting REMOVED options;"
    echo "(c) single-line summary 'blocks' in playbooks (not real MDP);"
    echo "(d) topology PARAMETERS written as inline 'a = value' spans (e.g. the"
    echo "virtual-site fraction 'a' in a [ virtual_sites2 ] line) — the inline"
    echo "extractor reads them as MDP options; they are not MDP."
  } > "$CLAIMS/notes.txt"

  log "claims + probes complete: $CLAIMS"
}

MODE="${1:-full}"
case "$MODE" in
  build)  run_build ;;
  claims) run_claims ;;
  full)   run_build; run_claims ;;
  *)      die "unknown mode: $MODE (use: full | build | claims)" ;;
esac

log "done. Next: read $SNAP/03_block_verdicts.txt, $SNAP/03_matrix_verdicts.txt, $SNAP/06_directive_verdicts.txt and $CLAIMS/notes.txt, then map KB claims to the snapshot (SKILL.md step 3)."
