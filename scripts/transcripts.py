"""Find and parse Claude Code session transcripts.

Reads ~/.claude/projects/<project>/: each session's main thread plus every
subagent and workflow agent under it. Each model call is counted once (a
streamed reply is saved as several lines). Shared by agent-tokens.py,
diagnose.py and the benchmark harness.
"""

import datetime as dt
import glob
import json
import os
import re
import statistics
import subprocess
from collections import Counter, defaultdict

BIG_CONTEXT = 100_000
CACHE_GAP_S = 300
NOT_SENT = ("prompt_snapshot",)  # attachment types kept for the app, not sent to the model
ROLES = ("builder", "fixer", "reviewer", "runner", "shipper")


def project_root():
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=10)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return os.getcwd()


def project_dir(root):
    # Claude Code names a project's folder after its path, with every
    # character that is not a letter or digit replaced by "-".
    path = os.path.abspath(root).replace("\\", "/")
    home = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    return os.path.join(home, "projects", re.sub(r"[^A-Za-z0-9]", "-", path))


def when(ts):
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _text(content):
    """The text of a message or tool-result content: a string, or a list of blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def read_agent(path, seen):
    """Return dict(calls, label, tools, events) for one transcript."""
    calls, label, tools, events, index = [], None, 0, [], {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if not isinstance(d, dict):
                continue
            if d.get("type") == "attachment":
                # Hook output, reminders and listing updates reach the model between calls.
                a = d.get("attachment")
                if isinstance(a, dict) and calls and a.get("type") not in NOT_SENT:
                    c = a.get("content")
                    size = len(c) if isinstance(c, str) else len(json.dumps(a))
                    events.append(dict(kind="message", source=a.get("type") or "attachment", size=size,
                                       ts=d.get("timestamp"), after=len(calls)))
                continue
            m = d.get("message") or {}
            content = m.get("content")
            if d.get("type") == "user":
                if label is None and not d.get("isMeta"):
                    c = content
                    if isinstance(c, list):
                        c = " ".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
                    if isinstance(c, str) and c.strip() and not c.lstrip().startswith("<"):
                        label = re.sub(r"\s+", " ", c.strip())[:60]
                blocks = content if isinstance(content, list) else []
                for b in blocks:
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        text, inner = _text(b.get("content")), b.get("content")
                        images = sum(1 for x in inner if isinstance(x, dict) and x.get("type") == "image")                             if isinstance(inner, list) else 0
                        events.append(dict(kind="result", id=b.get("tool_use_id"), size=len(text), head=text[:500],
                                           images=images, is_error=bool(b.get("is_error")), ts=d.get("timestamp"),
                                           after=len(calls)))
                if not any(isinstance(b, dict) and b.get("type") == "tool_result" for b in blocks):
                    text = _text(content)
                    if text and calls:  # the opening prompt is start-up, not a message
                        events.append(dict(kind="message", source="user", size=len(text), ts=d.get("timestamp"),
                                           after=len(calls)))
                continue
            if d.get("type") != "assistant":
                continue
            key = (m.get("id"), d.get("requestId"))
            u = m.get("usage")
            if u and key not in seen:
                seen.add(key)
                index[key] = len(calls)
                read = u.get("cache_read_input_tokens") or 0
                write = u.get("cache_creation_input_tokens") or 0
                fresh = u.get("input_tokens") or 0
                calls.append(dict(ts=d.get("timestamp"), ctx=fresh + read + write, read=read, write=write,
                                  fresh=fresh, out=u.get("output_tokens") or 0, model=m.get("model", "?")))
            for b in content or []:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    tools += 1
                    events.append(dict(kind="use", id=b.get("id"), name=b.get("name", ""), input=b.get("input") or {},
                                       ts=d.get("timestamp"), call=index.get(key)))
    return dict(calls=calls, label=label, tools=tools, events=events)


def load_session(pdir, main):
    seen = set()
    sid = os.path.basename(main)[:-6]
    a = read_agent(main, seen)
    agents = [dict(desc="(main thread)", calls=a["calls"], tools=a["tools"], events=a["events"])]
    for p in sorted(glob.glob(os.path.join(pdir, sid, "**", "agent-*.jsonl"), recursive=True)):
        meta = {}
        mp = p[:-6] + ".meta.json"
        if os.path.exists(mp):
            with open(mp, encoding="utf-8") as f:
                meta = json.load(f)
        s = read_agent(p, seen)
        if s["calls"]:
            agents.append(dict(desc=meta.get("description", ""), atype=meta.get("agentType", ""),
                               calls=s["calls"], tools=s["tools"], events=s["events"]))
    return sid, a["label"] or "", agents


def tokens(calls):
    return sum(c["ctx"] + c["out"] for c in calls)


def cost(calls):
    return sum(c["read"] * 0.1 + c["write"] * 1.25 + c["fresh"] + c["out"] * 5 for c in calls)


def rebuys(calls):
    """Cache-write tokens bought again after a gap long enough for the cache to expire."""
    total = 0
    for prev, c in zip(calls, calls[1:]):
        if not (prev["ts"] and c["ts"]):
            continue
        if c["write"] > 0.5 * c["ctx"] > 10_000 and (when(c["ts"]) - when(prev["ts"])).total_seconds() > CACHE_GAP_S:
            total += c["write"]
    return total


def role(a):
    if a["desc"] == "(main thread)":
        return "lead"
    atype = a.get("atype", "").split(":")[-1].lower()
    for r in ROLES:
        if r in atype:
            return r
    d = a["desc"].lower()
    for name, pat in [("reviewer", r"review|audit|skeptic|verify"), ("fixer", r"fix|address|repair|resolve"),
                      ("builder", r"build|implement|write|tdd"), ("runner", r"check|run |test|measure"),
                      ("shipper", r"merge|ship|pr |push")]:
        if re.search(pat, d):
            return name
    return atype or "other"


def find_session(pdir, ref):
    """A session is an id prefix in pdir, or a path to its .jsonl transcript."""
    if ref.endswith(".jsonl") and os.path.isfile(ref):
        return os.path.dirname(os.path.abspath(ref)), ref
    mains = [m for m in glob.glob(os.path.join(pdir, "*.jsonl")) if os.path.basename(m).startswith(ref)]
    if len(mains) != 1:
        raise SystemExit(f"{ref}: {len(mains)} sessions match; give a longer prefix or a transcript path")
    return pdir, mains[0]


def stats(pdir, ref):
    pdir, main = find_session(pdir, ref)
    sid, label, agents = load_session(pdir, main)
    allc = [c for a in agents for c in a["calls"]]
    if not allc:
        raise SystemExit(f"session {sid}: no model calls")
    T, C = tokens(allc), cost(allc)
    ts = [c["ts"] for c in allc if c["ts"]]
    subs = [a for a in agents if a["desc"] != "(main thread)"]
    rewrites = sum(rebuys(a["calls"]) for a in agents)
    by_role, by_model = defaultdict(lambda: [0, 0]), Counter()
    for a in agents:
        r = by_role[role(a)]
        r[0] += tokens(a["calls"])
        r[1] += 1
        for c in a["calls"]:
            by_model[c["model"]] += c["ctx"] + c["out"]
    big = sorted(subs, key=lambda a: -tokens(a["calls"]))
    return dict(
        sid=sid, label=label, hours=(when(max(ts)) - when(min(ts))).total_seconds() / 3600 if ts else 0, agents=len(subs),
        tokens=T, cost=C,
        reads=sum(c["read"] for c in allc) * .1 / C, writes=sum(c["write"] for c in allc) * 1.25 / C,
        output=sum(c["out"] for c in allc) * 5 / C,
        startup=statistics.median(a["calls"][0]["ctx"] for a in subs) if subs else None,
        top5=sum(tokens(a["calls"]) for a in big[:5]) / T if subs else None,
        peak=max(max(c["ctx"] for c in a["calls"]) for a in subs) if subs else None,
        lead_peak=max(c["ctx"] for c in agents[0]["calls"]) if agents[0]["calls"] else 0,
        above=sum(c["ctx"] for c in allc if c["ctx"] > BIG_CONTEXT) / T, rewrites=rewrites,
        per_call=sum(a["tools"] for a in agents) / max(1, len(allc)),
        by_role=sorted(((k, v[0] / T, v[1]) for k, v in by_role.items()), key=lambda x: -x[1]),
        by_model=[(k, v / T) for k, v in by_model.most_common()],
    )
