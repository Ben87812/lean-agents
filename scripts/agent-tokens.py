"""Measure the token use of Claude Code sessions from their saved transcripts.

Reads ~/.claude/projects/<project>/: each session's main thread plus every
subagent and workflow agent under it. Each model call is counted once (a
streamed reply is saved as several lines). Prints numbers only, never
transcript text beyond a short session label.

    python agent-tokens.py                    # one line per session, this project
    python agent-tokens.py 3f2a9c1e [...]     # detail for these sessions (id prefixes)
    python agent-tokens.py --project-dir PATH # another project's transcript folder
    python agent-tokens.py --share BEFORE AFTER  # numbers-only Markdown table to post
    python agent-tokens.py --diagnose 3f2a9c1e   # where the tokens went, with fixes, and agent health
    python agent-tokens.py --json 3f2a9c1e       # the same figures as JSON, for the benchmark

A session can also be given as the path to its .jsonl transcript, so the
before and after runs may come from different projects.

"Tokens" is the context sent per model call plus the output, summed over calls:
the figure usage limits track. "Cost" weighs it the way the API bills it,
relative to fresh input: cache reads 0.1, cache writes 1.25, output 5.
"""

import argparse
import glob
import json
import os

from diagnose import CHARS_PER_TOKEN, report
from transcripts import BIG_CONTEXT, CACHE_GAP_S, cost, load_session, project_dir, project_root, stats, tokens


def summary(pdir):
    rows = []
    for main in glob.glob(os.path.join(pdir, "*.jsonl")):
        sid, label, agents = load_session(pdir, main)
        allc = [c for a in agents for c in a["calls"]]
        if not allc:
            continue
        stamps = [c["ts"] for c in allc if c["ts"]]
        start = min(stamps) if stamps else "-"
        rows.append((start, sid, len(agents) - 1, tokens(allc), cost(allc), label))
    print(f"{'start':16} {'session':8} {'agents':>6} {'tokens':>8} {'cost-wt':>8}  first prompt")
    for start, sid, n, t, c, label in sorted(rows):
        print(f"{start[:16]} {sid[:8]} {n:6d} {t / 1e6:7.1f}M {c / 1e6:7.1f}M  {label}")


def detail(pdir, ref):
    s = stats(pdir, ref)
    print(f"session {s['sid']}  ({s['label']})")
    print(f"  elapsed {s['hours']:.1f} h (first to last message, idle time included); agents {s['agents']}")
    print(f"  tokens {s['tokens'] / 1e6:.1f}M; cost-weighted {s['cost'] / 1e6:.1f}M (reads {s['reads']:.0%}, "
          f"writes {s['writes']:.0%}, output {s['output']:.0%})")
    if s["agents"]:
        print(f"  agent start-up context: median {s['startup'] / 1e3:.1f}k")
        print(f"  five largest agents: {s['top5']:.0%} of tokens; largest peak context {s['peak'] / 1e3:.0f}k")
    print(f"  lead peak context: {s['lead_peak'] / 1e3:.0f}k")
    print(f"  tokens on calls above {BIG_CONTEXT // 1000}k context: {s['above']:.0%}")
    print(f"  cache rewritten after gaps over {CACHE_GAP_S // 60} min: {s['rewrites'] / 1e6:.1f}M tokens")
    print(f"  tool calls per model call: {s['per_call']:.2f}")
    print("  by role:  " + ", ".join(f"{k} {v:.0%} ({n})" for k, v, n in s["by_role"]))
    print("  by model: " + ", ".join(f"{k} {v:.0%}" for k, v in s["by_model"]))


SHARE_ROWS = [
    ("Tokens", lambda s: f"{s['tokens'] / 1e6:.1f}M", "tokens"),
    ("Cost-weighted tokens", lambda s: f"{s['cost'] / 1e6:.1f}M", "cost"),
    ("Elapsed hours (idle included)", lambda s: f"{s['hours']:.1f}", "hours"),
    ("Agents", lambda s: str(s["agents"]), None),
    ("Agent start-up (median)", lambda s: f"{s['startup'] / 1e3:.1f}k" if s["startup"] else "-", "startup"),
    ("Largest agent context", lambda s: f"{s['peak'] / 1e3:.0f}k" if s["peak"] else "-", "peak"),
    ("Lead peak context", lambda s: f"{s['lead_peak'] / 1e3:.0f}k", "lead_peak"),
    ("Tokens on calls above 100k context", lambda s: f"{s['above']:.0%}", None),
    ("Tool calls per model call", lambda s: f"{s['per_call']:.2f}", None),
    ("By role", lambda s: ", ".join(f"{k} {v:.0%}" for k, v, _ in s["by_role"]), None),
    ("By model", lambda s: ", ".join(f"{k} {v:.0%}" for k, v in s["by_model"]), None),
]


def share(pdir, refs):
    """Print numbers only, as a Markdown table: no session ids, prompts, paths or dates."""
    runs = [stats(pdir, r) for r in refs]
    if len(runs) == 2:
        print("| | Before | After | Change |\n|---|---|---|---|")
        for name, fmt, key in SHARE_ROWS:
            b, a = runs
            change = f"{(a[key] - b[key]) / b[key]:+.0%}" if key and b[key] else ""
            print(f"| {name} | {fmt(b)} | {fmt(a)} | {change} |")
    else:
        heads = [f"Run {i + 1}" for i in range(len(runs))]
        print("| | " + " | ".join(heads) + " |\n|---|" + "---|" * len(runs))
        for name, fmt, _ in SHARE_ROWS:
            print(f"| {name} | " + " | ".join(fmt(s) for s in runs) + " |")
    print("\nMeasured with lean-agents scripts/agent-tokens.py --share")


def print_diagnosis(pdir, ref, hung_min):
    r = report(pdir, ref, hung_min)
    d = r["diagnosis"]
    print(f"session {r['sid']}  ({r['label']})")
    print(f"  where the tokens went, of {d['total'] / 1e6:.2f}M "
          f"(measured context growth, split by what arrived between calls):")
    for c in d["causes"]:
        print(f"    {c['cause']:18} {c['tokens'] / 1e6:7.2f}M {c['share']:4.0%}  {c['fix']}")
        for culprit, t in c["culprits"]:
            print(f"        {t / 1e6:7.2f}M  {culprit}")
    if d["patterns"]:
        print("  patterns (these overlap the causes above):")
        for p in d["patterns"]:
            value = f"{p['value']}" if p["unit"] == "reviewers" else f"{p['value'] / 1e6:.2f}M"
            print(f"    {p['pattern']:18} {value:>8}  {p['fix']}")
            for culprit, v in p["culprits"]:
                print(f"        {v if p['unit'] == 'reviewers' else f'{v / 1e6:.2f}M':>8}  {culprit}")
    if d["coverage"] is not None:
        print(f"  sources found for {d['coverage']:.0%} of the context growth")
    print("  health: " + ("no problems found" if not r["health"] else f"{len(r['health'])} found"))
    for h in r["health"]:
        print(f"    {h['kind']}: {h['agent']}: {h['detail']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sessions", nargs="*", help="session id prefixes to report in detail")
    ap.add_argument("--share", action="store_true",
                    help="print the sessions as a Markdown table with numbers only (two sessions: before and after)")
    ap.add_argument("--diagnose", action="store_true",
                    help="for each session: where the tokens went, with a fix per cause, and agent health")
    ap.add_argument("--json", action="store_true", help="for each session: stats, diagnosis and health as JSON")
    ap.add_argument("--hung-min", type=float, default=10,
                    help="minutes a tool call may wait before it counts as hung (default 10)")
    ap.add_argument("--project-dir", help="Claude Code transcript folder (default: the one for this git repo or folder)")
    args = ap.parse_args()
    for flag in ("diagnose", "json"):
        if getattr(args, flag) and not args.sessions:
            raise SystemExit(f"--{flag} needs one or more sessions")
    if args.share and not args.sessions:
        raise SystemExit("--share needs one or more sessions (before and after for a comparison)")
    pdir = args.project_dir or project_dir(project_root())
    if not os.path.isdir(pdir) and not all(r.endswith(".jsonl") for r in args.sessions or [""]):
        raise SystemExit(f"no transcripts at {pdir}\nlist ~/.claude/projects/ and pass --project-dir")
    if args.share:
        if not args.sessions:
            raise SystemExit("--share needs one or more sessions (before and after for a comparison)")
        share(pdir, args.sessions)
    elif args.json:
        print(json.dumps([report(pdir, s, args.hung_min) for s in args.sessions], indent=1))
    elif args.diagnose:
        for s in args.sessions:
            print_diagnosis(pdir, s, args.hung_min)
    elif args.sessions:
        for s in args.sessions:
            detail(pdir, s)
    else:
        summary(pdir)


if __name__ == "__main__":
    main()
