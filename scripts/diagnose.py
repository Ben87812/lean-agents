"""Charge every token to what brought it into context, and check the agents' health.

Anything that enters an agent's context is re-sent on every later call, so
content that arrives after call k of an agent's N calls is charged its size
x (N - k). Sizes come from the API: the growth in context from one call to the
next is split between what arrived in between (the previous call's output,
tool results, messages), weighted by estimates (CHARS_PER_TOKEN characters a
token, IMAGE_TOKENS an image). Growth beyond the estimates goes to images if
any arrived, otherwise to "other context"; coverage() is the share of growth
with a known source.
"""

import json
import re
from collections import Counter, defaultdict

from transcripts import BIG_CONTEXT, find_session, load_session, rebuys, role, stats, tokens, when

CHARS_PER_TOKEN = 4
IMAGE_TOKENS = 1_600
MESSAGES = "(user and system messages)"
SHELL = ("Bash", "PowerShell")
SEARCH = ("Grep", "Glob")
SPAWN = ("Agent", "Task")
DIED_RE = re.compile(r"maxTurns|max turns|without StructuredOutput", re.I)
FIXES = {
    "start-up": "Use role agents, disable plugins the repository never uses, switch claude.ai connectors off",
    "file reads": "Lower LEAN_MAX_LINES or add these paths to LEAN_ALWAYS_RANGED, so they are read by range",
    "re-reads": "Write module notes and put what agents need in the brief",
    "shell output": "Lower bashOutputMaxChars and put quiet test flags in the brief",
    "search output": "Search narrower: give a path or glob, and limit the matches",
    "subagent reports": "Ask the role agents for shorter reports",
    "other tool output": "Check which tool this is and whether its output can be cut",
    "own output": "Ask for shorter replies and plans; large Write and Edit contents count here",
    "messages": "Cut hook output and long pasted text; system reminders count here",
    "other context": "Context that grew with no recorded source: compaction summaries, attachments",
    "long agents": "Hand over earlier: lower maxTurns or the hand-over round in the agent prompt",
    "cache rebuys": "Give long commands to a runner instead of waiting with a big context",
    "model mix": "Set the model per role: the smallest for runners, mid-tier for reviewers and shippers",
    "review rounds": "Cap reviews at 2 rounds; minor findings are notes",
}


def norm_path(p):
    """One spelling per file: forward slashes, lower case (Windows paths ignore case)."""
    return p.replace("\\", "/").lower()


def _first_reads(agents):
    """The first Read of each path in the session, as (timestamp, tool id)."""
    first = {}
    for a in agents:
        for e in a["events"]:
            if e["kind"] == "use" and e["name"] == "Read":
                p = norm_path(str(e["input"].get("file_path", "")))
                key = (e["ts"] or "", e["id"] or "")
                if p not in first or key < first[p]:
                    first[p] = key
    return first


def classify(use, first):
    """Return (cause, culprit) for the tool call that produced a result."""
    if use is None:
        return "other tool output", "(unknown tool)"
    name, inp = use["name"], use["input"]
    if name == "Read":
        p = str(inp.get("file_path", ""))
        if first.get(norm_path(p)) != (use["ts"] or "", use["id"] or ""):
            return "re-reads", p
        return "file reads", p + ("" if "offset" in inp or "limit" in inp else " (whole)")
    if name in SHELL:
        return "shell output", str(inp.get("command", ""))[:80]
    if name in SEARCH:
        return "search output", f"{name} {inp.get('pattern', '')}"[:80]
    if name in SPAWN:
        return "subagent reports", str(inp.get("description", ""))[:80]
    return "other tool output", name


def _parts(a, k, uses, first, arrived):
    """(cause, culprit, estimated tokens, images) for what entered context between calls k-1 and k."""
    parts = [("own output", a["desc"] or a.get("atype", ""), a["calls"][k - 1]["out"], 0)]
    for e in arrived:
        est = e["size"] / CHARS_PER_TOKEN + e.get("images", 0) * IMAGE_TOKENS
        if e["kind"] == "message":
            parts.append(("messages", MESSAGES if e.get("source", "user") == "user" else e["source"], est, 0))
        else:
            cause, culprit = classify(uses.get(e["id"]), first)
            parts.append((cause, culprit, est, e.get("images", 0)))
    return parts


def charges(agents):
    """Tokens charged per cause, with culprits: {cause: [tokens, Counter(culprit -> tokens)]}."""
    first = _first_reads(agents)
    out = defaultdict(lambda: [0.0, Counter()])

    def add(cause, culprit, t):
        out[cause][0] += t
        out[cause][1][culprit] += t

    for a in agents:
        calls, n = a["calls"], len(a["calls"])
        if not n:
            continue
        add("start-up", a["desc"] or a.get("atype", ""), calls[0]["ctx"] * n)
        uses = {e["id"]: e for e in a["events"] if e["kind"] == "use"}
        arrived = defaultdict(list)
        for e in a["events"]:
            if e["kind"] in ("result", "message") and 0 < e["after"] < n:
                arrived[e["after"]].append(e)
        for k in range(1, n):
            growth = calls[k]["ctx"] - calls[k - 1]["ctx"]
            if growth <= 0:
                continue
            times = n - k
            parts = _parts(a, k, uses, first, arrived[k])
            est = sum(p[2] for p in parts)
            scale = min(1.0, growth / est) if est else 0.0
            for cause, culprit, t, _ in parts:
                add(cause, culprit, t * scale * times)
            rest = growth - est * scale
            if rest <= 0:
                continue
            images = sum(p[3] for p in parts)
            if images:
                for cause, culprit, _, im in parts:
                    if im:
                        add(cause, culprit, rest * im / images * times)
            else:
                add("other context", a["desc"] or a.get("atype", ""), rest * times)
    return out


def _review_key(desc):
    d = re.sub(r"\d+|\bround\b|\bagain\b|\bre-", " ", desc.lower())
    return re.sub(r"\s+", " ", d).strip()


def patterns(agents):
    """Costly patterns that overlap the causes: {name: Counter(culprit -> value)}."""
    long, rebuy, mix = Counter(), Counter(), Counter()
    for a in agents:
        big = sum(c["ctx"] + c["out"] for c in a["calls"] if c["ctx"] > BIG_CONTEXT)
        if big:
            long[a["desc"]] += big
        r = rebuys(a["calls"])
        if r:
            rebuy[a["desc"]] += r
        if role(a) in ("runner", "shipper", "reviewer"):
            strong = sum(c["ctx"] + c["out"] for c in a["calls"] if "opus" in c["model"])
            if strong:
                mix[a["desc"]] += strong
    reviews = Counter(_review_key(a["desc"]) for a in agents if role(a) == "reviewer")
    rounds = Counter({k: v for k, v in reviews.items() if v > 2})
    return {"long agents": long, "cache rebuys": rebuy, "model mix": mix, "review rounds": rounds}


def coverage(agents):
    """The share of measured context growth that came with a known source."""
    grown = sum(max(0, c2["ctx"] - c1["ctx"]) * (len(a["calls"]) - k)
                for a in agents for k, (c1, c2) in enumerate(zip(a["calls"], a["calls"][1:]), 1))
    if not grown:
        return None
    return 1 - charges(agents).get("other context", [0])[0] / grown


def diagnose(agents):
    total = sum(tokens(a["calls"]) for a in agents)
    ranked = sorted(charges(agents).items(), key=lambda kv: -kv[1][0])
    causes = [dict(cause=k, tokens=round(v[0]), share=v[0] / total if total else 0.0, fix=FIXES[k],
                   culprits=[[c, round(t)] for c, t in v[1].most_common(3)]) for k, v in ranked]
    pats = [dict(pattern=k, value=sum(ctr.values()), unit="reviewers" if k == "review rounds" else "tokens",
                 fix=FIXES[k], culprits=[[c, v] for c, v in ctr.most_common(3)])
            for k, ctr in patterns(agents).items() if ctr]
    return dict(total=total, causes=causes, patterns=pats, coverage=coverage(agents))


def health(agents, hung_min=10):
    """Agents that died, waited too long on one call, or repeated the same call."""
    found = []
    for a in agents:
        uses = [e for e in a["events"] if e["kind"] == "use"]
        results = {e["id"]: e for e in a["events"] if e["kind"] == "result"}
        last = a["events"][-1] if a["events"] else None
        if last and last["kind"] == "use" and last["id"] not in results:
            found.append(dict(kind="died", agent=a["desc"], detail=f"ended on {last['name']} with no result"))
        for u in uses:
            r = results.get(u["id"])
            if not r:
                continue
            # A subagent or a background command is meant to run long; the agent is not waiting on it.
            waits = u["name"] not in SPAWN and not u["input"].get("run_in_background")
            if waits and u["ts"] and r["ts"]:
                gap = (when(r["ts"]) - when(u["ts"])).total_seconds() / 60
                if gap > hung_min:
                    found.append(dict(kind="hung", agent=a["desc"], detail=f"{u['name']} waited {gap:.0f} min"))
            if u["name"] in SPAWN and DIED_RE.search(r["head"]):
                found.append(dict(kind="died", agent=str(u["input"].get("description", "")),
                                  detail="hit its turn limit or ended without its output"))
        repeats = Counter((u["name"], json.dumps(u["input"], sort_keys=True)) for u in uses)
        for (name, _), n in repeats.items():
            if n >= 3:
                found.append(dict(kind="looping", agent=a["desc"], detail=f"{name} called {n} times with the same input"))
    return found


def report(pdir, ref, hung_min=10):
    """Stats, diagnosis, health and the per-call series for one session, as one JSON-ready dict."""
    pdir, main = find_session(pdir, ref)
    agents = load_session(pdir, main)[2]
    r = stats(pdir, main)
    r.update(diagnosis=diagnose(agents), health=health(agents, hung_min),
             series=[dict(ts=c["ts"], ctx=c["ctx"], out=c["out"], agent=i)
                     for i, a in enumerate(agents) for c in a["calls"]])
    return r
