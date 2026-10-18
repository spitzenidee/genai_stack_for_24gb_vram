#!/usr/bin/env python3
"""tmd — tasks.md board CLI (python3 stdlib only, no dependencies).

Board API: $TASKS_MD_URL/_api  (default http://localhost:8090)
Paths are board-relative:  Lane/card.md   (or proj/Lane/card.md for sub-projects)

Commands:
  list [project]                 one line per lane, cards in stored order
  get <Lane/card.md>             print card markdown
  new-lane <Lane>                create lane
  new-card <Lane/card.md>        create card, content from stdin
  edit <Lane/card.md>            replace content, from stdin (validates the
                                 result: structure + newly-written Log entries;
                                 --force overrides for repair)
  insert <Lane/card.md>          insert a content section (stdin) before the
                                 last exact '## Log' line (appends at end if
                                 the card has no Log header); validates the
                                 result; --force overrides for repair
  check <Lane/card.md>           validate card structure (tag line, H1, at
                                 most one standalone '## Log' heading, Log
                                 last) + Log format (canonical entry regex,
                                 non-decreasing timestamps, no consecutive
                                 duplicates); exit 1 + offending lines;
                                 non-matching entries labeled '[old-format]'
                                 (grandfathered legacy entries — stateless
                                 whole-Log check)
  append <Lane/card.md>          append stdin to content (validates the
                                 appended Log entries; --force overrides)
  move <src> <dst>               move card (dst may be "Lane/" to keep name);
                                 auto-updates sort order on both lanes
  claim <Lane/card.md>           claim a card for work: verify Active is EMPTY
                                 (single-Active guardrail), move it into Active,
                                 print its content — one call (the worker's
                                 list+get+move collapsed into one)
  to-top <Lane/card.md>          move card to the top of its lane (highest priority)
  reorder <Lane> <a,b,c,...>     set a lane's card order (top->bottom); unlisted
                                 cards keep their current order after the listed ones
  rm <Lane/card.md | Lane>       delete card or lane
  img <name>                     upload image from stdin, prints _api/image/<name>
                                 (usage: tmd img plot.png < /path/to/plot.png)

Card paths may omit the ".md" suffix: move/new-card/edit/insert/append/claim
add it for you. rm keeps the ".md" to tell a card from a lane. to-top/reorder set
per-lane order (the _api/sort map, whole-map last-write-wins) — use them, don't
hand-edit the sort.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime

BASE = os.environ.get("TASKS_MD_URL", "http://localhost:8090").rstrip("/")
API = BASE + "/_api"


def die(msg, code=1):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def req(method, path, body=None, raw_body=None, content_type=None):
    """HTTP request to the board API. Returns (status, body-text). Dies on error."""
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    elif raw_body is not None:
        data = raw_body
        if content_type:
            headers["Content-Type"] = content_type
    r = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        die(f"HTTP {e.code} {method} {path}: {e.read().decode()[:200]}")
    except urllib.error.URLError as e:
        die(f"cannot reach {API}{path}: {e.reason}")


def q(path):
    """URL-encode a board path (spaces, '#' etc.; slashes stay)."""
    return urllib.parse.quote(path, safe="/")


def proj_suffix(project):
    return f"/{q(project)}" if project else ""


def sort_path(project):
    # Root project: NO trailing slash (API key ""). A trailing slash would
    # address a different project key "/" — quirk encapsulated here.
    return "/sort" + proj_suffix(project)


def get_sort(project=""):
    _, body = req("GET", sort_path(project))
    try:
        return json.loads(body) or {}
    except json.JSONDecodeError:
        return {}


def put_sort(project, lanes):
    req("PUT", sort_path(project), body=lanes)


def ensure_md(path):
    """Card files are stored with a .md suffix; accept it omitted and normalize."""
    return path if path.endswith(".md") else path + ".md"


def split_lane(lane_arg):
    """'Lane' -> ('', 'Lane');  'proj/Lane' -> ('proj', 'Lane')."""
    parts = lane_arg.split("/")
    if len(parts) == 1:
        return "", parts[0]
    return "/".join(parts[:-1]), parts[-1]


def resource_lanes(project=""):
    _, body = req("GET", "/resource" + proj_suffix(project))
    return json.loads(body)


def effective_order(project, lane):
    """Current top->bottom card order for a lane (sort map + unsorted on-disk cards)."""
    lanes = resource_lanes(project)
    lane_obj = next((l for l in lanes if l["name"] == lane), None)
    cards = [f["name"] for f in (lane_obj["files"] if lane_obj else [])]
    sort = get_sort(project)
    ordered = [c for c in sort.get(lane, []) if c in cards]
    ordered += [c for c in cards if c not in ordered]
    return ordered


def split_path(path):
    """'proj/Lane/card.md' -> (project, lane, card); root project -> ('', lane, card)."""
    parts = path.split("/")
    if len(parts) < 2:
        die(f"expected <Lane/card.md> (or <proj/Lane/card.md>), got: {path}")
    if len(parts) == 2:
        return "", parts[0], parts[1]
    return "/".join(parts[:-2]), parts[-2], parts[-1]


def get_content(path):
    project, lane, card = split_path(path)
    _, body = req("GET", "/resource" + proj_suffix(project))
    want = card.removesuffix(".md")
    for l in json.loads(body):
        if l["name"] == lane:
            for f in l["files"]:
                if f["name"] == want:
                    return f["content"]
    die(f"card not found: {path}")


def cmd_list(project=""):
    _, body = req("GET", "/resource" + proj_suffix(project))
    lanes = json.loads(body)
    sort = get_sort(project)
    on_disk = {l["name"] for l in lanes}
    order = [l for l in sort.keys() if l in on_disk]
    for l in lanes:
        if l["name"] not in order:
            order.append(l["name"])
    for lane in order:
        lane_obj = next((l for l in lanes if l["name"] == lane), None)
        cards = [f["name"] for f in (lane_obj["files"] if lane_obj else [])]
        ordered = [c for c in sort.get(lane, []) if c in cards]
        ordered += [c for c in cards if c not in ordered]
        print(f"{lane}: {', '.join(ordered) if ordered else '-'}")


def cmd_get(path):
    content = get_content(path)
    sys.stdout.write(content)
    if content and not content.endswith("\n"):
        print()


def cmd_new_lane(name):
    req("POST", "/resource/" + q(name), body={"isFile": False})
    print(f"created lane: {name}")


def cmd_new_card(path):
    path = ensure_md(path)
    req("POST", "/resource/" + q(path),
        body={"isFile": True, "content": sys.stdin.read()})
    # Register in the sort map — /_api/sort (and the orchestrator) only see
    # cards listed there; a file-only card is a ghost (tmd list merges
    # unsorted on-disk cards, which masks the gap).
    project, lane, card = split_path(path)
    name = card.removesuffix(".md")
    sort = get_sort(project)
    if name not in sort.get(lane, []):
        sort.setdefault(lane, [])
        sort[lane].append(name)
        put_sort(project, sort)
    print(f"created: {path}")


def _outside_fences(lines):
    """1-based line indices that are OUTSIDE fenced code blocks.

    Simplified CommonMark: a fence opens with a line starting (after up to
    3 spaces) with ``` or ~~~ (3+ of the character); it closes at the next
    line consisting of the same character repeated at least as often.
    """
    outside = []
    in_fence = False
    fence_char = ""
    fence_len = 0
    for i, line in enumerate(lines, 1):
        s = line.strip()
        if in_fence:
            if s and set(s) == {fence_char} and len(s) >= fence_len:
                in_fence = False
            continue
        m = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if m:
            in_fence = True
            fence_char = m.group(1)[0]
            fence_len = len(m.group(1))
            continue
        outside.append(i)
    return outside


def validate_card(content):
    """Structural validation (P2). Returns a list of violation strings
    (empty list = OK). Rules:
      1. line 1 is a tag line (starts with '[tag:')
      2. an H1 heading exists (a line starting with '# ')
      3. at most one standalone '## Log' heading (a line whose stripped text
         is exactly '## Log'); in-body quotes (backticks, table cells, code
         fences) do not count
      4. if a '## Log' heading is present, it is the last heading in the card
         (no heading line after it)
    Lines inside fenced code blocks are not headings (rules 2–4).
    """
    violations = []
    lines = content.splitlines()
    if not lines or not lines[0].startswith("[tag:"):
        violations.append("line 1: must be a tag line (starts with '[tag:')")
    outside = _outside_fences(lines)
    if not any(lines[i - 1].startswith("# ") for i in outside):
        violations.append("card: no H1 heading found (a line starting with '# ')")
    log_lines = [i for i in outside if lines[i - 1].strip() == "## Log"]
    if len(log_lines) > 1:
        for ln in log_lines[1:]:
            violations.append(
                f"line {ln}: second standalone '## Log' heading "
                f"(first at line {log_lines[0]})")
    if log_lines:
        outside_set = set(outside)
        for i in range(log_lines[0] + 1, len(lines) + 1):
            if i in outside_set and re.match(r"^#{1,6}(?:\s|$)", lines[i - 1].strip()):
                violations.append(
                    f"line {i}: heading after '## Log' "
                    f"(line {log_lines[0]}) — the Log section must be last")
                break
    return violations


def refuse_violations(context, path, violations):
    """Print a loud validation failure and exit non-zero."""
    print(f"error: {context} refused — {path} would violate card structure / "
          f"log format:",
          file=sys.stderr)
    for v in violations:
        print(f"  {v}", file=sys.stderr)
    print("use --force to override (deliberate repair of a malformed card)",
          file=sys.stderr)
    sys.exit(1)


# --- Log-format validation (P3) -------------------------------------------
# Canonical log entry: exactly ONE bullet line, in one of two forms.
#   general: - DD.MM.YYYY HH:MM **Action** — one-line summary
#   moved:   - DD.MM.YYYY HH:MM **Moved** <src> → <dst>: reason
# Validation is scoped to the newly written delta (append/insert/edit), not
# the whole pre-existing Log: pre-existing old-format entries are grandfathered.
LOG_ENTRY_RE = re.compile(
    r"^- \d{2}\.\d{2}\.\d{4} \d{2}:\d{2} \*\*"
    r"(Moved\*\* [^ ]+ → [^ ]+: .+|[^*]+\*\* — .+)$"
)
_TS_FMT = "%d.%m.%Y %H:%M"


def _parse_ts(ts_str):
    """Parse 'DD.MM.YYYY HH:MM' into a datetime (for chronological checks)."""
    return datetime.strptime(ts_str, _TS_FMT)


def extract_log_lines(content):
    """Extract Log entries from card content.

    Returns (lines, line_numbers): the non-blank lines after the LAST exact
    '## Log' header, and their 1-based line numbers. Empty if no Log header.
    """
    lines = content.splitlines()
    log_start = None
    for i, line in enumerate(lines):
        if line.strip() == "## Log":
            log_start = i + 1  # 0-based index of first line after the header
    if log_start is None:
        return [], []
    out_lines, out_nums = [], []
    for i in range(log_start, len(lines)):
        if lines[i].strip():
            out_lines.append(lines[i])
            out_nums.append(i + 1)  # 1-based
    return out_lines, out_nums


def validate_log_lines(lines, line_numbers, prev_ts=None,
                       prev_line=None, prev_line_num=None, whole_log=False):
    """Validate Log entries against the canonical format.

    Per entry: matches LOG_ENTRY_RE (general em-dash form or Moved form);
    timestamp non-decreasing (vs. the running previous timestamp, optionally
    seeded with prev_ts from a pre-existing entry); not a consecutive
    duplicate of the previous entry (optionally seeded with prev_line, so a
    new entry duplicating the last pre-existing entry is caught).
    Returns violation strings (empty = OK).

    whole_log: when True (standalone `tmd check` over the whole Log section),
    non-matching entries are labeled '[old-format]' — grandfathered legacy
    entries (a stateless check has no notion of "newly written", so a new
    malformed entry is labeled the same way; the reader distinguishes by
    position/timestamp). When False (the write path, delta-scoped),
    non-matching entries are regular violations.
    """
    violations = []
    cur_ts = prev_ts
    last_line = prev_line
    last_num = prev_line_num
    for line, ln in zip(lines, line_numbers):
        if not LOG_ENTRY_RE.match(line):
            prefix = "[old-format] " if whole_log else ""
            violations.append(
                f"line {ln}: {prefix}log entry does not match the canonical "
                f"format ('- DD.MM.YYYY HH:MM **Action** — summary' or "
                f"'- DD.MM.YYYY HH:MM **Moved** <src> → <dst>: reason')")
        else:
            ts_str = line[2:18]
            try:
                ts = _parse_ts(ts_str)
            except ValueError:
                violations.append(f"line {ln}: unparseable timestamp '{ts_str}'")
                ts = None
            if ts is not None:
                if cur_ts is not None and ts < cur_ts:
                    ref = (f" (line {last_num})" if last_num is not None
                           else " (a pre-existing entry)")
                    violations.append(
                        f"line {ln}: timestamp {ts_str} is earlier than the "
                        f"previous entry{ref}")
                cur_ts = ts
        if last_line is not None and line == last_line:
            ref = (f" (line {last_num})" if last_num is not None
                   else " (a pre-existing entry)")
            violations.append(
                f"line {ln}: duplicate of the previous entry{ref}")
        last_line = line
        last_num = ln
    return violations


def _last_log_ts(content):
    """Timestamp (datetime) of the last parseable Log entry, or None."""
    lines, _ = extract_log_lines(content)
    for line in reversed(lines):
        if LOG_ENTRY_RE.match(line):
            try:
                return _parse_ts(line[2:18])
            except ValueError:
                continue
    return None


def diff_log_lines(old_content, new_content):
    """Log entries present in new_content but not in old_content (multiset).

    Returns (lines, line_numbers) for the NEW entries only, with their 1-based
    line numbers in new_content. Scopes edit/insert validation to the newly
    written delta (pre-existing entries are grandfathered).
    """
    old_lines, _ = extract_log_lines(old_content)
    old_remaining = list(old_lines)
    new_lines, new_nums = extract_log_lines(new_content)
    out_lines, out_nums = [], []
    for line, ln in zip(new_lines, new_nums):
        if line in old_remaining:
            old_remaining.remove(line)
        else:
            out_lines.append(line)
            out_nums.append(ln)
    return out_lines, out_nums


def cmd_insert(path, force=False):
    """Insert a content section (stdin) before the last exact '## Log' line.

    The real Log header is always the LAST exact match, so the anchor is
    unambiguous even with in-body quotes (backticks, table cells, code
    fences). No '## Log' line in the card -> append the section at the end
    (no header created) and print a note. The resulting content is validated
    before the PATCH; on violation the write is refused (--force overrides).
    """
    path = ensure_md(path)
    section = sys.stdin.read().strip("\n")
    if not section.strip():
        die("insert: empty section on stdin")
    current = get_content(path)
    lines = current.splitlines()
    log_idx = None
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip() == "## Log":
            log_idx = i
            break
    section_lines = section.splitlines()
    before = lines[:log_idx] if log_idx is not None else lines[:]
    while before and not before[-1].strip():
        before.pop()
    if log_idx is not None:
        after = lines[log_idx:]
        result_lines = before + [""] + section_lines + [""] + after
        note = ""
    else:
        result_lines = before + [""] + section_lines
        note = " (no '## Log' header in card — appended at end, no header created)"
    result = "\n".join(result_lines) + "\n"
    if not force:
        violations = validate_card(result)
        # Log-format validation on the inserted delta (the section). The
        # section is a content section (placed before '## Log'), so it has no
        # Log entries in practice; this is a no-op backstop.
        sec_lines, sec_nums = extract_log_lines(section)
        if sec_lines:
            violations.extend(validate_log_lines(sec_lines, sec_nums))
        if violations:
            refuse_violations("insert", path, violations)
    req("PATCH", "/resource/" + q(path), body={"content": result})
    insert_at = len(before) + 2  # 1-based line number of the section's first line
    msg = f"inserted section at line {insert_at}: {path}{note}"
    if force:
        msg += " [--force: structure + log-format validation overridden]"
    print(msg)


def cmd_check(path):
    """Validate a card's structure + Log format; exit non-zero + offending lines.

    Structure: tag line, H1, single '## Log' heading, Log last.
    Log format (strict, whole Log section): canonical entry regex,
    non-decreasing timestamps, no consecutive duplicates. Non-matching
    entries are labeled '[old-format]' (grandfathered legacy entries — a
    stateless check has no notion of "newly written" — or new malformed
    entries; the reader distinguishes by position/timestamp). The card still
    FAILs on them (the backstop stays strong); the label makes the output
    interpretable. The write path (append/insert/edit) is the primary gate
    and is delta-scoped (legacy lines never fail there).
    """
    path = ensure_md(path)
    content = get_content(path)
    violations = validate_card(content)
    log_lines, log_nums = extract_log_lines(content)
    violations.extend(validate_log_lines(log_lines, log_nums, whole_log=True))
    if violations:
        print(f"FAIL: {path}", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        sys.exit(1)
    print(f"OK: {path}")


def cmd_edit(path, force=False):
    path = ensure_md(path)
    content = sys.stdin.read()
    if not force:
        violations = validate_card(content)
        # Log-format validation on the newly written delta (entries present in
        # the new content but not the old). Pre-existing entries are
        # grandfathered, so editing a legacy card never fails on old lines.
        old_content = get_content(path)
        delta_lines, delta_nums = diff_log_lines(old_content, content)
        if delta_lines:
            # Seed the chronological + duplicate checks with the last
            # pre-existing Log entry, so a delta entry that is out-of-order
            # or duplicates the last existing entry is caught (the delta
            # alone can't see it — same seeding as cmd_append).
            prev_ts = _last_log_ts(old_content)
            old_log_lines, old_log_nums = extract_log_lines(old_content)
            prev_line = old_log_lines[-1] if old_log_lines else None
            prev_line_num = old_log_nums[-1] if old_log_nums else None
            violations.extend(
                validate_log_lines(delta_lines, delta_nums, prev_ts,
                                   prev_line, prev_line_num))
        if violations:
            refuse_violations("edit", path, violations)
    req("PATCH", "/resource/" + q(path), body={"content": content})
    msg = f"updated: {path}"
    if force:
        msg += " [--force: structure + log-format validation overridden]"
    print(msg)


def cmd_append(path, force=False):
    path = ensure_md(path)
    current = get_content(path)
    extra = sys.stdin.read()
    if current and not current.endswith("\n"):
        current += "\n"
    result = current + extra
    if not force:
        # Validate the appended delta (the newly written lines). Appended lines
        # land after the '## Log' header, so they are Log entries; seed the
        # chronological check with the last pre-existing entry's timestamp.
        base = len(current.splitlines())
        delta_lines, delta_nums = [], []
        for i, line in enumerate(extra.splitlines()):
            if line.strip():
                delta_lines.append(line)
                delta_nums.append(base + i + 1)
        # Seed the chronological + duplicate checks with the last pre-existing
        # Log entry, so a new entry that is out-of-order or duplicates the
        # last existing entry is caught (the delta alone can't see it).
        prev_ts = _last_log_ts(current)
        cur_log_lines, cur_log_nums = extract_log_lines(current)
        prev_line = cur_log_lines[-1] if cur_log_lines else None
        prev_line_num = cur_log_nums[-1] if cur_log_nums else None
        violations = validate_log_lines(
            delta_lines, delta_nums, prev_ts, prev_line, prev_line_num)
        if violations:
            refuse_violations("append", path, violations)
    req("PATCH", "/resource/" + q(path), body={"content": result})
    msg = f"appended: {path}"
    if force:
        msg += " [--force: log-format validation overridden]"
    print(msg)


def cmd_move(src, dst):
    src = ensure_md(src)
    sp, slane, scard = split_path(src)
    if dst.endswith("/"):
        dst = dst + scard
    else:
        dst = ensure_md(dst)
    dp, dlane, _ = split_path(dst)
    if sp != dp:
        die("move within one project only (v1)")
    req("PATCH", "/resource/" + q(src), body={"newPath": dst})
    # The move endpoint does NOT update sort state — do it here (as the UI does).
    name = scard.removesuffix(".md")
    sort = get_sort(sp)
    if slane in sort:
        sort[slane] = [c for c in sort[slane] if c != name]
    sort.setdefault(dlane, [])
    if name not in sort[dlane]:
        sort[dlane].append(name)
    put_sort(sp, sort)
    print(f"moved: {src} -> {dst}")


def cmd_claim(path):
    """Claim a card: Active must be empty, then move it in + print its content.

    The worker's critical path in one invocation: replaces list + get + move
    (3 docker runs, 6 HTTP) with 1 run / 4 HTTP. The content is taken from
    the initial resource fetch (no extra round-trip after the move).
    """
    path = ensure_md(path)
    project, lane, card = split_path(path)
    if lane == "Active":
        die(f"claim: card is already in Active: {path}")
    name = card.removesuffix(".md")
    # 1. File truth: the Active lane must be empty (single-Active guardrail).
    lanes = resource_lanes(project)
    active_obj = next((l for l in lanes if l["name"] == "Active"), None)
    active_cards = [f["name"] for f in (active_obj["files"] if active_obj else [])]
    if active_cards:
        die(f"claim: Active lane not empty ({', '.join(active_cards)}) — "
            f"single-Active guardrail; refusing to claim {path}")
    # 2. Locate the card (and its content) in the source lane.
    src_obj = next((l for l in lanes if l["name"] == lane), None)
    content = None
    for f in (src_obj["files"] if src_obj else []):
        if f["name"] == name:
            content = f["content"]
            break
    if content is None:
        die(f"claim: card not found: {path}")
    # 3. Move it into Active (file move + sort sync, as cmd_move does).
    req("PATCH", "/resource/" + q(f"{lane}/{card}"),
        body={"newPath": f"Active/{card}"})
    sort = get_sort(project)
    if lane in sort:
        sort[lane] = [c for c in sort[lane] if c != name]
    sort.setdefault("Active", [])
    if name not in sort["Active"]:
        sort["Active"].append(name)
    put_sort(project, sort)
    print(f"claimed: {lane}/{name} -> Active/{name}")
    # 4. Print the card content (from the pre-move fetch).
    sys.stdout.write(content)
    if not content.endswith("\n"):
        print()


def cmd_to_top(path):
    project, lane, card = split_path(ensure_md(path))
    name = card.removesuffix(".md")
    order = effective_order(project, lane)
    if name not in order:
        die(f"card not found in lane: {lane}/{name}")
    order.remove(name)
    order.insert(0, name)
    sort = get_sort(project)
    sort[lane] = order
    put_sort(project, sort)
    print(f"moved to top: {lane}/{name}")


def cmd_reorder(lane_arg, csv):
    project, lane = split_lane(lane_arg)
    names = [c.strip() for c in csv.split(",") if c.strip()]
    if not names:
        die("reorder: no cards given (usage: tmd reorder <Lane> <a,b,c,...>)")
    order = effective_order(project, lane)
    missing = [n for n in names if n not in order]
    if missing:
        die(f"cards not in lane {lane}: {', '.join(missing)}")
    new_order = names + [c for c in order if c not in names]
    sort = get_sort(project)
    sort[lane] = new_order
    put_sort(project, sort)
    print(f"reordered {lane}: {', '.join(new_order)}")


def cmd_rm(path):
    req("DELETE", "/resource/" + q(path))
    # Keep the sort map in sync: a deleted card/lane must not linger in it
    # (stale entries are ghosts for /_api/sort consumers like the orchestrator).
    if path.endswith(".md"):  # card: drop it from its lane's sort list
        project, lane, card = split_path(path)
        name = card.removesuffix(".md")
        sort = get_sort(project)
        if name in sort.get(lane, []):
            sort[lane] = [c for c in sort[lane] if c != name]
            put_sort(project, sort)
    else:  # lane: drop its whole sort entry
        parts = path.split("/")
        sort = get_sort("/".join(parts[:-1]))
        if parts[-1] in sort:
            del sort[parts[-1]]
            put_sort("/".join(parts[:-1]), sort)
    print(f"deleted: {path}")


def cmd_img(name):
    data = sys.stdin.buffer.read()
    if not data:
        die("no image data on stdin (usage: tmd img <name> < file)")
    boundary = uuid.uuid4().hex
    head = (f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{name}"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n").encode()
    body = head + data + f"\r\n--{boundary}--\r\n".encode()
    _, out = req("POST", "/image", raw_body=body,
                 content_type=f"multipart/form-data; boundary={boundary}")
    print(f"_api/image/{out.strip()}")


def main():
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
        return
    cmd, args = a[0], a[1:]
    if cmd == "list" and len(args) <= 1:
        cmd_list(args[0] if args else "")
    elif cmd == "get" and len(args) == 1:
        cmd_get(args[0])
    elif cmd == "new-lane" and len(args) == 1:
        cmd_new_lane(args[0])
    elif cmd == "new-card" and len(args) == 1:
        cmd_new_card(args[0])
    elif cmd == "edit" and 1 <= len(args) <= 2:
        force = "--force" in args
        paths = [a for a in args if a != "--force"]
        if len(paths) != 1:
            die(f"usage error: tmd {cmd} <Lane/card.md> [--force]")
        cmd_edit(paths[0], force=force)
    elif cmd == "insert" and 1 <= len(args) <= 2:
        force = "--force" in args
        paths = [a for a in args if a != "--force"]
        if len(paths) != 1:
            die(f"usage error: tmd {cmd} <Lane/card.md> [--force]")
        cmd_insert(paths[0], force=force)
    elif cmd == "check" and len(args) == 1:
        cmd_check(args[0])
    elif cmd == "append" and 1 <= len(args) <= 2:
        force = "--force" in args
        paths = [a for a in args if a != "--force"]
        if len(paths) != 1:
            die(f"usage error: tmd {cmd} <Lane/card.md> [--force]")
        cmd_append(paths[0], force=force)
    elif cmd == "move" and len(args) == 2:
        cmd_move(args[0], args[1])
    elif cmd == "claim" and len(args) == 1:
        cmd_claim(args[0])
    elif cmd == "to-top" and len(args) == 1:
        cmd_to_top(args[0])
    elif cmd == "reorder" and len(args) == 2:
        cmd_reorder(args[0], args[1])
    elif cmd == "rm" and len(args) == 1:
        cmd_rm(args[0])
    elif cmd == "img" and len(args) == 1:
        cmd_img(args[0])
    else:
        die(f"usage error: tmd {cmd} ...")


if __name__ == "__main__":
    main()
