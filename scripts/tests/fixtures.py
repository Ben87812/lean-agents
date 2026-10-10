"""Synthetic Claude Code transcripts for tests. No real transcript text is used."""

import datetime as dt
import itertools
import json
import os
import sys

# Tests import the scripts under test (transcripts, diagnose) by name.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

T0 = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
STANDARD_SID = "aaaa1111-0000-4000-8000-000000000000"
_ids = itertools.count(1)


def ts(sec):
    return (T0 + dt.timedelta(seconds=sec)).isoformat().replace("+00:00", "Z")


class Transcript:
    """The JSONL lines of one agent's transcript, built call by call."""

    def __init__(self, prompt="do the task", start=0, model="claude-opus-5-5"):
        self.lines, self.clock, self.model = [], start, model
        self.lines.append({"type": "user", "timestamp": ts(self.clock),
                           "message": {"role": "user", "content": prompt}})

    def call(self, ctx, out=100, tools=(), text="", gap=10, write=500):
        """One model call with ctx tokens of context; tools is a list of (id, name, input)."""
        self.clock += gap
        n = next(_ids)
        content = [{"type": "text", "text": text}] if text else []
        content += [{"type": "tool_use", "id": i, "name": name, "input": inp} for i, name, inp in tools]
        self.lines.append({"type": "assistant", "timestamp": ts(self.clock), "requestId": f"req{n}",
                           "message": {"id": f"msg{n}", "model": self.model, "content": content,
                                       "usage": {"input_tokens": 10, "cache_read_input_tokens": ctx - 10 - write,
                                                 "cache_creation_input_tokens": write, "output_tokens": out}}})
        return self

    def result(self, tool_id, chars=0, text=None, is_error=False, gap=1, as_blocks=False, images=0):
        self.clock += gap
        body = text if text is not None else "x" * chars
        content = [{"type": "text", "text": body}] if as_blocks or images else body
        if images:
            content += [{"type": "image", "source": {"type": "base64", "data": "Zm9v"}}] * images
        self.lines.append({"type": "user", "timestamp": ts(self.clock), "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": tool_id, "content": content, "is_error": is_error}]}})
        return self

    def message(self, text, gap=5):
        """A user or system message between calls."""
        self.clock += gap
        self.lines.append({"type": "user", "timestamp": ts(self.clock), "message": {"role": "user", "content": text}})
        return self

    def dump(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            for line in self.lines:
                f.write(json.dumps(line) + "\n")


def write_session(pdir, sid, main, subagents=()):
    """Write main (a Transcript) and subagents [(Transcript, meta)] the way Claude Code lays them out."""
    path = os.path.join(pdir, sid + ".jsonl")
    main.dump(path)
    for n, (t, meta) in enumerate(subagents):
        base = os.path.join(pdir, sid, "subagents", f"agent-a{n:04d}")
        t.dump(base + ".jsonl")
        with open(base + ".meta.json", "w", encoding="utf-8") as f:
            json.dump(meta, f)
    return path


def standard_session(pdir, sid=STANDARD_SID):
    """A lead that spawns a builder and a reviewer. The builder reads a file whole, runs the tests,
    then reads the same file again by range under another spelling of its path. Each call's context
    grows by exactly the previous call's output plus the tool results that arrived in between."""
    lead = Transcript("Fix the bug in calc", start=0)
    lead.call(20_000, tools=[("L1", "Agent", {"description": "Build the calc fix",
                                              "subagent_type": "lean-agents:builder", "prompt": "brief"})])
    b = Transcript("Build the calc fix", start=20)
    b.call(8_000, tools=[("B1", "Read", {"file_path": "C:\\repo\\src\\calc.py"})]).result("B1", chars=40_000)
    b.call(18_100, tools=[("B2", "Bash", {"command": "pytest -q"})]).result("B2", chars=8_000)
    b.call(20_200, tools=[("B3", "Read", {"file_path": "c:/repo/src/calc.py", "offset": 10, "limit": 20})])
    b.result("B3", chars=2_000)
    b.call(20_800, text="done")
    lead.result("L1", chars=4_000, gap=200)
    lead.call(21_100, tools=[("L2", "Agent", {"description": "Review the calc fix",
                                              "subagent_type": "lean-agents:reviewer", "prompt": "brief"})])
    r = Transcript("Review the calc fix", start=300, model="claude-sonnet-5-5")
    r.call(6_000, tools=[("R1", "Grep", {"pattern": "def add"})]).result("R1", chars=1_200)
    r.call(6_400, text="approved")
    lead.result("L2", chars=800, gap=100)
    lead.call(21_400, text="all done")
    return write_session(pdir, sid, lead, [
        (b, {"agentType": "lean-agents:builder", "description": "Build the calc fix"}),
        (r, {"agentType": "lean-agents:reviewer", "description": "Review the calc fix"})])
