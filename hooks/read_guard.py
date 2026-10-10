"""PreToolUse hook for Read: block whole-file reads of large text files.

Whatever an agent reads stays in its context and is re-sent on every later
turn, so a whole 3,000-line file costs far more than the 80 lines around a
search hit. A Read of a text file over MAX_LINES lines must name a range
(offset or limit). Images, PDFs and notebooks pass through untouched.

Settings (environment variables, all optional):
  LEAN_MAX_LINES       line limit for a whole-file read (default 400)
  LEAN_ALWAYS_RANGED   comma-separated path endings that must always be read
                       by range, whatever their size (generated files, a big
                       shared plan or decision log), e.g. "src/gen/api.ts,docs/plan.md"

Any error lets the read through: the guard must never stop work by failing itself.
"""

import json
import os
import sys

PASS_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".pdf", ".ipynb", ".svg")


def settings():
    max_lines = int(os.environ.get("LEAN_MAX_LINES") or 400)
    always = tuple(
        p.strip().replace("\\", "/").lower()
        for p in (os.environ.get("LEAN_ALWAYS_RANGED") or "").split(",")
        if p.strip()
    )
    return max_lines, always


def main() -> int:
    try:
        max_lines, always = settings()
        event = json.load(sys.stdin)
        args = event.get("tool_input") or {}
        path = args.get("file_path") or ""
        if args.get("offset") or args.get("limit"):
            return 0
        norm = path.replace("\\", "/").lower()
        if norm.endswith(PASS_SUFFIXES) or not os.path.isfile(path):
            return 0
        if always and norm.endswith(always):
            size = "is on the always-read-by-range list"
        else:
            with open(path, "rb") as f:
                lines = sum(1 for _ in f)
            if lines <= max_lines:
                return 0
            size = f"has {lines} lines"
    except Exception:
        return 0
    print(
        f"Blocked: {os.path.basename(path)} {size}. Reading it whole would stay in your "
        f"context and be re-sent on every later turn. Find what you need with Grep (-n), then "
        f"Read with offset and limit around the match (about 40 to 150 lines). If your task "
        f"brief covers this document, read the brief instead. If you must change most of the "
        f"file, read it in ranges of up to {max_lines} lines.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
