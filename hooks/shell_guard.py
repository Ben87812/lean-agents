"""PreToolUse hook for Bash and PowerShell: the Read guard's rule for shell reads.

Files printed through the shell (cat, sed -n, Get-Content, type) never pass the
Read guard, and in measured multi-agent runs they cost more tokens than the Read
tool did. Whatever a command prints stays in the agent's context for every later
turn. This blocks, and explains how to do it cheaply:

- printing a whole text file over LEAN_MAX_LINES lines (cat, type, Get-Content
  without -TotalCount/-Head/-Tail/-First/-Last, and with no pipe that cuts it),
- a sed -n or Select-Object -Skip/-First range wider than LEAN_MAX_RANGE lines,
- printing any LEAN_ALWAYS_RANGED file whole, at any size,
- a git diff of a branch or commit range with no pathspec and no --stat,
  --name-only, --shortstat or --numstat (diff one file at a time after --stat).

Settings (environment variables, all optional): LEAN_MAX_LINES (default 400),
LEAN_MAX_RANGE (default 250), LEAN_ALWAYS_RANGED (comma-separated path endings).

Any error lets the command through: the guard must never stop work by failing itself.
"""

import json
import os
import re
import sys

CUTS = re.compile(r"\|\s*(head|tail|grep|rg|select-string|select-object|sed|awk|wc|findstr|measure-object|out-null)\b", re.I)
WHOLE = re.compile(r"(?:^|[;&|(]\s*|\s)(cat|type|gc|get-content)\s+((?:-\w+\s+)*)([^\s|;&>]+)", re.I)
SED = re.compile(r"\bsed\s+-n\s+['\"]?(\d+),(\d+)p['\"]?\s+([^\s|;&>]+)")
SKIP = re.compile(r"select-object\s+.*-skip\s+(\d+)\s+.*-first\s+(\d+)", re.I)
GIT_DIFF = re.compile(r"\bgit\s+(?:-C\s+\S+\s+)?(diff|show)\b([^|;&]*)")


def settings():
    max_lines = int(os.environ.get("LEAN_MAX_LINES") or 400)
    max_range = int(os.environ.get("LEAN_MAX_RANGE") or 250)
    always = tuple(
        p.strip().replace("\\", "/").lower()
        for p in (os.environ.get("LEAN_ALWAYS_RANGED") or "").split(",")
        if p.strip()
    )
    return max_lines, max_range, always


def lines_in(path, cwd):
    p = path.strip("'\"")
    if not os.path.isabs(p):
        p = os.path.join(cwd, p)
    if not os.path.isfile(p):
        return None
    with open(p, "rb") as f:
        return sum(1 for _ in f)


def why(cmd, cwd):
    max_lines, max_range, always = settings()
    for seg in re.split(r"&&|;|\n", cmd):
        if CUTS.search(seg):
            continue
        m = WHOLE.search(seg)
        if m and not re.search(r"-(totalcount|head|tail|first|last)\b", m.group(2) + seg, re.I):
            path = m.group(3)
            norm = path.strip("'\"").replace("\\", "/").lower()
            if always and norm.endswith(always):
                return f"{os.path.basename(path)} is on the always-read-by-range list"
            n = lines_in(path, cwd)
            if n and n > max_lines:
                return f"{os.path.basename(path)} has {n} lines"
    for a, b, path in SED.findall(cmd):
        if int(b) - int(a) > max_range:
            return f"the range {a},{b} of {os.path.basename(path)} is {int(b) - int(a)} lines"
    m = SKIP.search(cmd)
    if m and int(m.group(2)) > max_range:
        return f"-First {m.group(2)} is over {max_range} lines"
    for verb, rest in GIT_DIFF.findall(cmd):
        if re.search(r"--(stat|name-only|name-status|shortstat|numstat|quiet|exit-code)\b|\s--\s|\s--$", rest):
            continue
        if verb == "diff" and ("..." in rest or ".." in rest or re.search(r"\borigin/|\bmain\b|\bmaster\b|HEAD~", rest)):
            return "a whole-branch git diff prints every file at once"
    return None


def main() -> int:
    try:
        event = json.load(sys.stdin)
        cmd = (event.get("tool_input") or {}).get("command") or ""
        cwd = event.get("cwd") or os.getcwd()
        reason = why(cmd, cwd)
        _, max_range, _ = settings()
    except Exception:
        return 0
    if not reason:
        return 0
    print(
        f"Blocked: {reason}. Whatever a command prints stays in your context for every later turn. "
        f"Search first (Grep, or grep -n / Select-String), then print about 40 to 150 lines around the match "
        f"(Read with offset and limit, or sed -n 'A,Bp' up to {max_range} lines). For a branch diff, run "
        f"git diff --stat first, then git diff <range> -- <file> one file at a time. If your task brief "
        f"covers this document, read the brief instead.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
