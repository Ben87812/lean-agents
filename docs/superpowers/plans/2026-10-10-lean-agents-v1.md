# lean-agents v1.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship lean-agents v1.0 with a benchmark graded by hidden tests, a diagnosis report that charges every token to its cause, and module notes tested as the first cut through a repeatable loop.

**Architecture:** Transcript parsing moves into `scripts/transcripts.py`. That module is shared by `agent-tokens.py` (the user-facing command), `scripts/diagnose.py` (charging tokens to causes, plus health checks) and the benchmark harness (`bench/tasks.py`, `bench/run.py`, `bench/report.py`). The harness runs each arm (no plugin, or a git ref of this repo checked out as a worktree) in its own clone of a tier, caps its spend by watching its transcript, grades it with hidden tests, and writes `results.json` and an HTML report.

**Tech Stack:** Python 3 standard library only (no dependencies, matching the existing scripts), `unittest`, git, the Claude Code CLI (`claude -p --session-id --plugin-dir`).

**Spec:** `docs/superpowers/specs/2026-10-10-lean-agents-v1-design.md`

## Global Constraints

- Python 3 standard library only; no third-party packages in scripts, hooks or bench.
- Runs on Windows, macOS and Linux. Never use `sh`-only syntax in commands Python runs; use argument lists or commands valid in both `cmd.exe` and `sh`.
- Files use LF line endings (`.gitattributes` has `* text=auto eol=lf`). Open files for writing with `newline="\n"` where line endings matter.
- `agent-tokens.py`'s existing output (session list, detail, `--share`) must not change.
- `--share` prints numbers only: no session ids, prompts, paths, commands or dates.
- No real transcript text is ever committed; test transcripts are built in code by `scripts/tests/fixtures.py`.
- The harness never deletes anything. An existing clone folder is an error.
- The harness never pushes. Agents get `Bash(git push*)`, `Bash(gh *)`, `Bash(curl *)`, `Bash(pip *)`, `Bash(uv *)`, `Bash(npm install*)`, `Bash(go get*)`, `WebFetch` and `WebSearch` disallowed.
- The ship rule for a cut: hidden-test pass rate the same or better, **and** total tokens down by more than 10% against the lean arm, **and** the drop showing in the cause the cut targets.
- Tier files are trusted configuration written by the maintainer: their setup and test commands run through the shell (`shell=True`) on purpose, so that one command string works in `cmd.exe` and `sh`. Never build a command from agent output or transcript text.
- Writing style for prose (README, CUTS.md, agent prompts): plain English, short sentences, as in the existing README.
- Run the tests with `python -m unittest discover -s scripts/tests -v` and `python -m unittest discover -s bench/tests -v` from the repository root.

## Review Focus

1. **Transcript content shapes.** A `tool_result` whose content is a list of blocks (text plus images), lines that aren't JSON, and missing `usage` or `timestamp` fields must parse without a crash, with sizes counting the text only. Pinned in Task 2.
2. **One file, several path spellings.** On Windows, `C:\repo\src\calc.py` and `c:/repo/src/calc.py` are the same file and the second read is a re-read. Pinned in Task 3.
3. **Sessions with no subagents.** `--diagnose` and `--json` must work on a plain session with only a main thread. Pinned in Tasks 3 and 5.
4. **Cap stop with child processes.** When the cap stops an arm, its whole process tree (node, test runners) must die, and grading must still run. Pinned in Task 7.
5. **A tier that can't be set up.** A missing repo, a suite that can't run at the base, or an existing clone folder must stop that arm with a clear error. Other arms carry on and nothing gets deleted. Pinned in Tasks 6 and 7.

---

## File Structure

| File | Responsibility |
|---|---|
| `scripts/transcripts.py` (new) | Find and parse session transcripts: calls, usage, tool events, roles, stats |
| `scripts/diagnose.py` (new) | Charge tokens to causes, detect patterns, check agent health, build the JSON report |
| `scripts/agent-tokens.py` (modify) | The user command: list, detail, `--share`, `--diagnose`, `--json` |
| `scripts/tests/fixtures.py` (new) | Build synthetic transcripts in code |
| `scripts/tests/test_*.py` (new) | Unit tests for the above |
| `scripts/tests/golden_output.txt` (new) | `agent-tokens.py` output before the refactor |
| `bench/tasks.py` (new) | Load tiers, set up clones, grade with hidden tests, validate tiers |
| `bench/run.py` (new) | Run arms in parallel with a spend cap; write `results.json` |
| `bench/report.py` (new) | `results.json` → `report.html` (table, charts, diagnosis, health) |
| `bench/prompt.txt` (new) | The shared lead prompt |
| `bench/tests/` (new) | Tests for the harness, with a fake `claude` |
| `bench/tasks/long/`, `bench/tasks/light/` (new) | Tier definitions |
| `bench/CUTS.md` (new) | Record of every cut, merged or rejected |
| `agents/builder.md`, `agents/fixer.md`, `skills/lean-agent-runs/SKILL.md` (modify, on `cut/module-notes`) | Module notes |
| `README.md`, `.claude-plugin/plugin.json` (modify) | v1.0 |

---

### Task 1: Move transcript parsing into `transcripts.py`, behind a golden-output test

**Files:**
- Create: `scripts/transcripts.py`
- Create: `scripts/tests/fixtures.py`
- Create: `scripts/tests/test_golden.py`
- Create: `scripts/tests/golden_output.txt` (generated)
- Modify: `scripts/agent-tokens.py`

**Interfaces:**
- Produces in `transcripts.py`: `BIG_CONTEXT`, `CACHE_GAP_S`, `ROLES`, `project_root()`, `project_dir(root)`, `when(ts)`, `read_agent(path, seen)`, `load_session(pdir, main) -> (sid, label, agents)`, `tokens(calls)`, `cost(calls)`, `role(agent)`, `find_session(pdir, ref) -> (pdir, main_path)`, `stats(pdir, ref) -> dict`. Each agent is a dict with `desc`, `atype` (subagents only), `calls`, `tools`.
- Produces in `fixtures.py`: `ts(sec)`, `Transcript(prompt="do the task", start=0, model="claude-opus-5-5")` with `.call(ctx, out=100, tools=(), text="", gap=10, write=500)`, `.result(tool_id, chars=0, text=None, is_error=False, gap=1, as_blocks=False)` and `.dump(path)`, `write_session(pdir, sid, main, subagents=()) -> main_path`, `standard_session(pdir, sid=STANDARD_SID) -> main_path`, `STANDARD_SID`.

- [ ] **Step 1: Write the fixture builder**

Create `scripts/tests/fixtures.py`:

```python
"""Synthetic Claude Code transcripts for tests. No real transcript text is used."""

import datetime as dt
import itertools
import json
import os

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

    def result(self, tool_id, chars=0, text=None, is_error=False, gap=1, as_blocks=False):
        self.clock += gap
        body = text if text is not None else "x" * chars
        content = [{"type": "text", "text": body}] if as_blocks else body
        self.lines.append({"type": "user", "timestamp": ts(self.clock), "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": tool_id, "content": content, "is_error": is_error}]}})
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
    then reads the same file again by range under another spelling of its path."""
    lead = Transcript("Fix the bug in calc", start=0)
    lead.call(20_000, tools=[("L1", "Agent", {"description": "Build the calc fix",
                                              "subagent_type": "lean-agents:builder", "prompt": "brief"})])
    b = Transcript("Build the calc fix", start=20)
    b.call(8_000, tools=[("B1", "Read", {"file_path": "C:\\repo\\src\\calc.py"})]).result("B1", chars=40_000)
    b.call(18_000, tools=[("B2", "Bash", {"command": "pytest -q"})]).result("B2", chars=8_000)
    b.call(20_500, tools=[("B3", "Read", {"file_path": "c:/repo/src/calc.py", "offset": 10, "limit": 20})])
    b.result("B3", chars=2_000)
    b.call(21_000, text="done")
    lead.result("L1", chars=4_000, gap=200)
    lead.call(21_500, tools=[("L2", "Agent", {"description": "Review the calc fix",
                                              "subagent_type": "lean-agents:reviewer", "prompt": "brief"})])
    r = Transcript("Review the calc fix", start=300, model="claude-sonnet-5-5")
    r.call(6_000, tools=[("R1", "Grep", {"pattern": "def add"})]).result("R1", chars=1_200)
    r.call(6_400, text="approved")
    lead.result("L2", chars=800, gap=100)
    lead.call(22_000, text="all done")
    return write_session(pdir, sid, lead, [
        (b, {"agentType": "lean-agents:builder", "description": "Build the calc fix"}),
        (r, {"agentType": "lean-agents:reviewer", "description": "Review the calc fix"})])
```

- [ ] **Step 2: Write the golden-output test**

Create `scripts/tests/test_golden.py`:

```python
"""agent-tokens.py's output must not change when its internals move."""

import os
import subprocess
import sys
import tempfile
import unittest

from fixtures import standard_session

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(os.path.dirname(HERE), "agent-tokens.py")
GOLDEN = os.path.join(HERE, "golden_output.txt")


def run_script(pdir, *args):
    return subprocess.run([sys.executable, SCRIPT, *args, "--project-dir", pdir], capture_output=True,
                          text=True, encoding="utf-8", check=True).stdout


class Golden(unittest.TestCase):
    def test_list_detail_and_share_unchanged(self):
        with tempfile.TemporaryDirectory() as pdir:
            standard_session(pdir)
            out = run_script(pdir) + run_script(pdir, "aaaa1111") + run_script(pdir, "--share", "aaaa1111")
        if os.environ.get("UPDATE_GOLDEN"):
            with open(GOLDEN, "w", encoding="utf-8", newline="\n") as f:
                f.write(out)
        with open(GOLDEN, encoding="utf-8") as f:
            self.assertEqual(out, f.read())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Record the golden output from the current code**

PowerShell: `$env:UPDATE_GOLDEN="1"; python -m unittest discover -s scripts/tests -v; Remove-Item Env:UPDATE_GOLDEN`
Bash: `UPDATE_GOLDEN=1 python -m unittest discover -s scripts/tests -v`
Expected: PASS. `scripts/tests/golden_output.txt` exists and holds a session line for `aaaa1111`, the detail block ("session aaaa1111…", "by role: …") and a share table.

Then run `python -m unittest discover -s scripts/tests -v` without the variable. Expected: PASS.

- [ ] **Step 4: Commit the fixtures and golden output**

```bash
git add scripts/tests/fixtures.py scripts/tests/test_golden.py scripts/tests/golden_output.txt
git commit -m "Pin agent-tokens.py's output with a golden test on a synthetic session before moving its internals"
```

- [ ] **Step 5: Create `scripts/transcripts.py` by moving code**

Create `scripts/transcripts.py` with this header, then **move**, unchanged, from `scripts/agent-tokens.py`: the constants `BIG_CONTEXT`, `CACHE_GAP_S`, `ROLES` and the functions `project_root`, `project_dir`, `when`, `read_agent`, `load_session`, `tokens`, `cost`, `role`, `find_session` and `stats` (today lines 32–192, without `summary` and `detail`).

```python
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
```

- [ ] **Step 6: Make `agent-tokens.py` import them**

In `scripts/agent-tokens.py`, delete the moved definitions and the imports only they used. Replace them with the following, keeping `summary`, `detail`, `SHARE_ROWS`, `share` and `main` as they are:

```python
import argparse
import os

from transcripts import BIG_CONTEXT, CACHE_GAP_S, cost, load_session, project_dir, project_root, stats, tokens
```

Keep `import glob` if `summary` still uses it (it does: `glob.glob(os.path.join(pdir, "*.jsonl"))`). Keep the module docstring as it is.

- [ ] **Step 7: Run the golden test**

Run: `python -m unittest discover -s scripts/tests -v`
Expected: PASS (the output is byte-for-byte unchanged).

- [ ] **Step 8: Commit**

```bash
git add scripts/transcripts.py scripts/agent-tokens.py
git commit -m "Move transcript parsing into transcripts.py so the diagnosis and the benchmark can share it"
```

---

### Task 2: Record tool events in the parser

**Files:**
- Modify: `scripts/transcripts.py` (`read_agent`, `load_session`)
- Create: `scripts/tests/test_transcripts.py`

**Interfaces:**
- Consumes: `fixtures.Transcript`, `fixtures.standard_session`, `transcripts.find_session`, `transcripts.load_session`.
- Produces: `read_agent(path, seen) -> dict(calls, label, tools, events)`. Every agent dict from `load_session` gets `events`, a list in transcript order of:
  - `{"kind": "use", "id": str, "name": str, "input": dict, "ts": str|None, "call": int|None}`, where `call` is the index of the model call that made it;
  - `{"kind": "result", "id": str, "size": int, "head": str, "is_error": bool, "ts": str|None, "after": int}`, where `size` is the characters of text, `head` is the first 500 characters (kept in memory only, never printed), and `after` is the number of the agent's calls made before the result arrived.

- [ ] **Step 1: Write the failing tests**

Create `scripts/tests/test_transcripts.py`:

```python
import json
import os
import tempfile
import unittest

from fixtures import STANDARD_SID, Transcript, standard_session, write_session
from transcripts import find_session, load_session


def agents_of(pdir, sid=STANDARD_SID):
    pdir, main = find_session(pdir, sid[:8])
    return load_session(pdir, main)[2]


class Events(unittest.TestCase):
    def test_uses_and_results_in_order(self):
        with tempfile.TemporaryDirectory() as pdir:
            standard_session(pdir)
            builder = agents_of(pdir)[1]
        kinds = [(e["kind"], e["id"]) for e in builder["events"]]
        self.assertEqual(kinds, [("use", "B1"), ("result", "B1"), ("use", "B2"), ("result", "B2"),
                                 ("use", "B3"), ("result", "B3")])
        use, res = builder["events"][0], builder["events"][1]
        self.assertEqual((use["name"], use["call"]), ("Read", 0))
        self.assertEqual(use["input"]["file_path"], "C:\\repo\\src\\calc.py")
        self.assertEqual((res["size"], res["after"], res["is_error"]), (40_000, 1, False))
        self.assertEqual(len(res["head"]), 500)

    def test_result_as_blocks_counts_text_only(self):
        t = Transcript().call(5_000, tools=[("T1", "Read", {"file_path": "a.png"})])
        t.result("T1", text="abc", as_blocks=True)
        t.lines[-1]["message"]["content"][0]["content"].append({"type": "image", "source": {"data": "Zm9v" * 100}})
        with tempfile.TemporaryDirectory() as pdir:
            write_session(pdir, "bbbb2222-0000-4000-8000-000000000000", t)
            main = agents_of(pdir, "bbbb2222")[0]
        self.assertEqual(main["events"][1]["size"], 3)

    def test_bad_lines_and_missing_fields_do_not_crash(self):
        t = Transcript().call(5_000, tools=[("T1", "Bash", {"command": "ls"})]).result("T1", chars=10)
        del t.lines[-1]["timestamp"]
        with tempfile.TemporaryDirectory() as pdir:
            path = write_session(pdir, "cccc3333-0000-4000-8000-000000000000", t)
            with open(path, "a", encoding="utf-8") as f:
                f.write("not json\n" + json.dumps({"type": "assistant", "message": {"content": None}}) + "\n")
            main = agents_of(pdir, "cccc3333")[0]
        self.assertEqual(len(main["calls"]), 1)
        self.assertIsNone(main["events"][1]["ts"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to check they fail**

Run: `python -m unittest discover -s scripts/tests -v`
Expected: FAIL in `test_transcripts` (`KeyError: 'events'` or a tuple-unpacking error).

- [ ] **Step 3: Implement events in `read_agent` and `load_session`**

In `scripts/transcripts.py`, replace `read_agent` with:

```python
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
            m = d.get("message") or {}
            content = m.get("content")
            if d.get("type") == "user":
                if label is None and not d.get("isMeta"):
                    c = content
                    if isinstance(c, list):
                        c = " ".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
                    if isinstance(c, str) and c.strip() and not c.lstrip().startswith("<"):
                        label = re.sub(r"\s+", " ", c.strip())[:60]
                for b in content if isinstance(content, list) else []:
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        text = _text(b.get("content"))
                        events.append(dict(kind="result", id=b.get("tool_use_id"), size=len(text), head=text[:500],
                                           is_error=bool(b.get("is_error")), ts=d.get("timestamp"), after=len(calls)))
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
```

And replace `load_session` with:

```python
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
```

- [ ] **Step 4: Run all script tests**

Run: `python -m unittest discover -s scripts/tests -v`
Expected: PASS, including the golden test (the output is unchanged).

- [ ] **Step 5: Commit**

```bash
git add scripts/transcripts.py scripts/tests/test_transcripts.py
git commit -m "Record each agent's tool calls and result sizes, so tokens can be charged to what brought them in"
```

---

### Task 3: Charge tokens to causes, and detect patterns

**Files:**
- Create: `scripts/diagnose.py`
- Modify: `scripts/transcripts.py` (add `rebuys`, use it in `stats`)
- Create: `scripts/tests/test_diagnose.py`

**Interfaces:**
- Consumes: `transcripts.BIG_CONTEXT`, `CACHE_GAP_S`, `role`, `tokens`, `when`; agent `events` from Task 2.
- Produces:
  - `transcripts.rebuys(calls) -> int`
  - `diagnose.CHARS_PER_TOKEN = 4`, `diagnose.FIXES: dict[str, str]`
  - `diagnose.norm_path(p) -> str`
  - `diagnose.charges(agents) -> {cause: [tokens: float, Counter(culprit -> tokens)]}`
  - `diagnose.patterns(agents) -> {name: Counter(culprit -> value)}`
  - `diagnose.coverage(agents) -> float | None`
  - `diagnose.diagnose(agents) -> dict(total, causes=[dict(cause, tokens, share, fix, culprits=[[label, tokens]])], patterns=[dict(pattern, value, unit, fix, culprits)], coverage)`

- [ ] **Step 1: Write the failing tests**

Create `scripts/tests/test_diagnose.py`:

```python
import tempfile
import unittest

from fixtures import STANDARD_SID, Transcript, standard_session, write_session
from transcripts import find_session, load_session
import diagnose as dg


def agents_of(pdir, sid):
    pdir, main = find_session(pdir, sid[:8])
    return load_session(pdir, main)[2]


def session(main, subagents=(), sid="dddd4444-0000-4000-8000-000000000000"):
    with tempfile.TemporaryDirectory() as pdir:
        write_session(pdir, sid, main, subagents)
        return agents_of(pdir, sid)


class Charges(unittest.TestCase):
    def setUp(self):
        with tempfile.TemporaryDirectory() as pdir:
            standard_session(pdir)
            self.agents = agents_of(pdir, STANDARD_SID)

    def test_each_cause_is_charged_for_every_later_call(self):
        c = {k: round(v[0]) for k, v in dg.charges(self.agents).items()}
        # builder: 4 calls. B1 (40,000 chars = 10,000 tokens) arrives after call 1 and is re-sent 3 times.
        self.assertEqual(c, {"start-up": 20_000 * 3 + 8_000 * 4 + 6_000 * 2, "file reads": 30_000,
                             "shell output": 4_000, "re-reads": 500, "subagent reports": 2_000 + 200,
                             "search output": 300})

    def test_reread_matches_another_spelling_of_the_same_path(self):
        culprits = dg.charges(self.agents)["re-reads"][1]
        self.assertEqual(list(culprits), ["c:/repo/src/calc.py"])
        self.assertEqual(list(dg.charges(self.agents)["file reads"][1]), ["C:\\repo\\src\\calc.py (whole)"])

    def test_coverage_compares_estimate_with_measured_growth(self):
        self.assertAlmostEqual(dg.coverage(self.agents), 14_000 / 14_800)

    def test_diagnose_ranks_causes_with_fixes(self):
        d = dg.diagnose(self.agents)
        self.assertEqual(d["causes"][0]["cause"], "start-up")
        self.assertEqual([c["cause"] for c in d["causes"]][:2], ["start-up", "file reads"])
        self.assertTrue(all(c["fix"] for c in d["causes"]))
        self.assertAlmostEqual(sum(c["share"] for c in d["causes"]), sum(c["tokens"] for c in d["causes"]) / d["total"], 3)
        self.assertEqual(d["patterns"], [])


class Patterns(unittest.TestCase):
    def test_long_agents_rebuys_model_mix_and_review_rounds(self):
        lead = Transcript("lead").call(150_000).call(160_000)
        runner = Transcript("Run the suite").call(10_000).call(40_000, write=30_000, gap=400)
        subs = [(runner, {"agentType": "lean-agents:runner", "description": "Run the suite"})]
        for d in ("Review calc fix", "Review calc fix round 2", "Review calc fix round 3"):
            subs.append((Transcript(d, model="claude-sonnet-5-5").call(5_000),
                         {"agentType": "lean-agents:reviewer", "description": d}))
        p = dg.patterns(session(lead, subs))
        self.assertEqual(p["long agents"], {"(main thread)": 150_100 + 160_100})
        self.assertEqual(p["cache rebuys"], {"Run the suite": 30_000})
        self.assertEqual(p["model mix"], {"Run the suite": 10_100 + 40_100})
        self.assertEqual(p["review rounds"], {"review calc fix": 3})

    def test_session_without_subagents(self):
        lead = Transcript("lead").call(5_000, tools=[("T1", "Bash", {"command": "ls"})]).result("T1", chars=400)
        lead.call(5_200, text="done")
        d = dg.diagnose(session(lead))
        self.assertEqual([c["cause"] for c in d["causes"]], ["start-up", "shell output"])


if __name__ == "__main__":
    unittest.main()
```

The numbers come from `standard_session`. The builder makes 4 calls: B1 arrives after call 1 and is in 3 calls (10,000 × 3), B2 after call 2 is in 2 (2,000 × 2), and B3 after call 3 is in 1 (500 × 1). The lead makes 3 calls: L1 (1,000 tokens) is in 2, and L2 (200) is in 1. The reviewer makes 2 calls: R1 (300) is in 1. Measured growth is the sum of (next context − context − output) over consecutive calls: 9,900 + 2,400 + 400 + 1,400 + 400 + 300 = 14,800. The estimate is the sum of the result sizes ÷ 4 that reach a later call: 12,500 + 1,200 + 300 = 14,000.

- [ ] **Step 2: Run the tests to check they fail**

Run: `python -m unittest discover -s scripts/tests -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'diagnose'`.

- [ ] **Step 3: Add `rebuys` to `transcripts.py` and use it in `stats`**

Add to `scripts/transcripts.py`, after `cost`:

```python
def rebuys(calls):
    """Cache-write tokens bought again after a gap long enough for the cache to expire."""
    total = 0
    for prev, c in zip(calls, calls[1:]):
        if not (prev["ts"] and c["ts"]):
            continue
        if c["write"] > 0.5 * c["ctx"] > 10_000 and (when(c["ts"]) - when(prev["ts"])).total_seconds() > CACHE_GAP_S:
            total += c["write"]
    return total
```

In `stats`, replace the `rewrites = 0` loop (the `for a in agents:` block that walks `zip(cs, cs[1:])`) with:

```python
    rewrites = sum(rebuys(a["calls"]) for a in agents)
```

- [ ] **Step 4: Write `scripts/diagnose.py`**

```python
"""Charge every token to what brought it into context, and check the agents' health.

Anything that enters an agent's context is re-sent on every later call, so a
tool result of n tokens that arrives after call k of an agent's N calls is
charged n x (N - k). Tool output is estimated at CHARS_PER_TOKEN characters a
token; coverage() compares the estimate with the context growth the API
measured.
"""

import json
import re
from collections import Counter, defaultdict

from transcripts import BIG_CONTEXT, find_session, load_session, rebuys, role, stats, tokens, when

CHARS_PER_TOKEN = 4
SHELL = ("Bash", "PowerShell")
SEARCH = ("Grep", "Glob")
SPAWN = ("Agent", "Task")
FIXES = {
    "start-up": "Use role agents, disable plugins the repository never uses, switch claude.ai connectors off",
    "file reads": "Lower LEAN_MAX_LINES or add these paths to LEAN_ALWAYS_RANGED, so they are read by range",
    "re-reads": "Write module notes and put what agents need in the brief",
    "shell output": "Lower bashOutputMaxChars and put quiet test flags in the brief",
    "search output": "Search narrower: give a path or glob, and limit the matches",
    "subagent reports": "Ask the role agents for shorter reports",
    "other tool output": "Check which tool this is and whether its output can be cut",
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


def charges(agents):
    """Tokens charged per cause, with culprits: {cause: [tokens, Counter(culprit -> tokens)]}."""
    first = _first_reads(agents)
    out = defaultdict(lambda: [0.0, Counter()])
    for a in agents:
        n = len(a["calls"])
        if not n:
            continue
        startup = a["calls"][0]["ctx"] * n
        out["start-up"][0] += startup
        out["start-up"][1][a["desc"] or a.get("atype", "")] += startup
        uses = {e["id"]: e for e in a["events"] if e["kind"] == "use"}
        for e in a["events"]:
            if e["kind"] != "result":
                continue
            charge = e["size"] / CHARS_PER_TOKEN * max(0, n - e["after"])
            cause, culprit = classify(uses.get(e["id"]), first)
            out[cause][0] += charge
            out[cause][1][culprit] += charge
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
    """Estimated tool output reaching a later call, over the context growth the API measured."""
    est = sum(e["size"] / CHARS_PER_TOKEN for a in agents for e in a["events"]
              if e["kind"] == "result" and e["after"] < len(a["calls"]))
    grown = sum(max(0, c2["ctx"] - c1["ctx"] - c1["out"]) for a in agents
                for c1, c2 in zip(a["calls"], a["calls"][1:]))
    return est / grown if grown else None


def diagnose(agents):
    total = sum(tokens(a["calls"]) for a in agents)
    ranked = sorted(charges(agents).items(), key=lambda kv: -kv[1][0])
    causes = [dict(cause=k, tokens=round(v[0]), share=v[0] / total if total else 0.0, fix=FIXES[k],
                   culprits=[[c, round(t)] for c, t in v[1].most_common(3)]) for k, v in ranked]
    pats = [dict(pattern=k, value=sum(ctr.values()), unit="reviewers" if k == "review rounds" else "tokens",
                 fix=FIXES[k], culprits=[[c, v] for c, v in ctr.most_common(3)])
            for k, ctr in patterns(agents).items() if ctr]
    return dict(total=total, causes=causes, patterns=pats, coverage=coverage(agents))
```

`find_session`, `load_session`, `stats`, `json` and `when` are imported now for Task 4 and Task 5.

- [ ] **Step 5: Run all script tests**

Run: `python -m unittest discover -s scripts/tests -v`
Expected: PASS, including the golden test (`stats` gives the same rebuy figure).

- [ ] **Step 6: Commit**

```bash
git add scripts/diagnose.py scripts/transcripts.py scripts/tests/test_diagnose.py
git commit -m "Charge every token to what brought it into context, with a suggested fix for each cause"
```

---

### Task 4: Health checks for died, hung and looping agents

**Files:**
- Modify: `scripts/diagnose.py` (add `DIED_RE`, `health`)
- Create: `scripts/tests/test_health.py`

**Interfaces:**
- Consumes: agent `events` from Task 2, `transcripts.when`.
- Produces: `diagnose.health(agents, hung_min=10) -> list[dict(kind, agent, detail)]`, where `kind` is `"died"`, `"hung"` or `"looping"`.

- [ ] **Step 1: Write the failing tests**

Create `scripts/tests/test_health.py`:

```python
import tempfile
import unittest

from fixtures import STANDARD_SID, Transcript, standard_session, write_session
from transcripts import find_session, load_session
import diagnose as dg


def agents_of(main, subagents=(), sid="eeee5555-0000-4000-8000-000000000000"):
    with tempfile.TemporaryDirectory() as pdir:
        write_session(pdir, sid, main, subagents)
        pdir, path = find_session(pdir, sid[:8])
        return load_session(pdir, path)[2]


class Health(unittest.TestCase):
    def test_healthy_session(self):
        with tempfile.TemporaryDirectory() as pdir:
            pdir, path = find_session(pdir, standard_session(pdir))
            self.assertEqual(dg.health(load_session(pdir, path)[2]), [])

    def test_agent_that_ends_on_a_call_with_no_result_died(self):
        b = Transcript("Build it").call(5_000, tools=[("X1", "Bash", {"command": "make"})])
        h = dg.health(agents_of(Transcript("lead").call(4_000), [(b, {"description": "Build it"})]))
        self.assertEqual(h, [dict(kind="died", agent="Build it", detail="ended on Bash with no result")])

    def test_turn_limit_reported_to_the_lead(self):
        lead = Transcript("lead").call(4_000, tools=[("A1", "Agent", {"description": "Fix tests"})])
        lead.result("A1", text="Agent completed without StructuredOutput").call(4_200, text="ok")
        h = dg.health(agents_of(lead))
        self.assertEqual([(x["kind"], x["agent"]) for x in h], [("died", "Fix tests")])

    def test_hung_call(self):
        lead = Transcript("lead").call(4_000, tools=[("H1", "Bash", {"command": "npm test"})])
        lead.result("H1", chars=10, gap=700).call(4_100, text="ok")
        self.assertEqual(dg.health(agents_of(lead), hung_min=10),
                         [dict(kind="hung", agent="(main thread)", detail="Bash waited 12 min")])
        self.assertEqual(dg.health(agents_of(lead), hung_min=15), [])

    def test_looping(self):
        lead = Transcript("lead")
        for i in range(3):
            lead.call(4_000 + i, tools=[(f"P{i}", "Bash", {"command": "pytest -x"})]).result(f"P{i}", text="1 failed", is_error=True)
        lead.call(5_000, text="giving up")
        self.assertEqual(dg.health(agents_of(lead)),
                         [dict(kind="looping", agent="(main thread)", detail="Bash called 3 times with the same input")])


if __name__ == "__main__":
    unittest.main()
```

`test_healthy_session` passes `standard_session`'s return value (a transcript path) to `find_session`, which accepts a `.jsonl` path.

- [ ] **Step 2: Run the tests to check they fail**

Run: `python -m unittest discover -s scripts/tests -v`
Expected: FAIL with `AttributeError: module 'diagnose' has no attribute 'health'`.

- [ ] **Step 3: Implement `health`**

Add to `scripts/diagnose.py`, after `SPAWN`:

```python
DIED_RE = re.compile(r"maxTurns|max turns|without StructuredOutput", re.I)
```

and at the end of the file:

```python
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
            if u["ts"] and r["ts"]:
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
```

- [ ] **Step 4: Run all script tests**

Run: `python -m unittest discover -s scripts/tests -v`
Expected: PASS. In `test_hung_call`, the result arrives 700 s after the call, which prints as "12 min".

- [ ] **Step 5: Commit**

```bash
git add scripts/diagnose.py scripts/tests/test_health.py
git commit -m "Flag agents that died, hung on one call or repeated the same call"
```

---

### Task 5: `--diagnose` and `--json` in `agent-tokens.py`

**Files:**
- Modify: `scripts/diagnose.py` (add `report`)
- Modify: `scripts/agent-tokens.py` (`main`, new `print_diagnosis`)
- Create: `scripts/tests/test_cli.py`

**Interfaces:**
- Consumes: `diagnose.diagnose`, `diagnose.health`, `transcripts.stats`, `transcripts.find_session`, `transcripts.load_session`.
- Produces: `diagnose.report(pdir, ref, hung_min=10) -> dict`, which is `stats(...)` plus `diagnosis`, `health` and `series` (`[dict(ts, ctx, out, agent)]`, one per call, where `agent` is the agent's index). CLI: `--diagnose`, `--json` and `--hung-min MINUTES`, each needing one or more sessions.

- [ ] **Step 1: Write the failing tests**

Create `scripts/tests/test_cli.py`:

```python
import json
import os
import subprocess
import sys
import tempfile
import unittest

from fixtures import Transcript, standard_session, write_session

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agent-tokens.py")


def run(pdir, *args, check=True):
    return subprocess.run([sys.executable, SCRIPT, *args, "--project-dir", pdir], capture_output=True,
                          text=True, encoding="utf-8", check=check)


class Cli(unittest.TestCase):
    def test_json(self):
        with tempfile.TemporaryDirectory() as pdir:
            standard_session(pdir)
            out = json.loads(run(pdir, "--json", "aaaa1111").stdout)
        self.assertEqual(len(out), 1)
        r = out[0]
        self.assertEqual(r["diagnosis"]["causes"][0]["cause"], "start-up")
        self.assertEqual(r["health"], [])
        self.assertEqual(len(r["series"]), 9)
        self.assertEqual(set(r["series"][0]), {"ts", "ctx", "out", "agent"})

    def test_diagnose_prints_causes_culprits_and_health(self):
        with tempfile.TemporaryDirectory() as pdir:
            standard_session(pdir)
            out = run(pdir, "--diagnose", "aaaa1111").stdout
        self.assertIn("where the tokens went", out)
        self.assertIn("re-reads", out)
        self.assertIn("c:/repo/src/calc.py", out)
        self.assertIn("health: no problems found", out)

    def test_plain_session_without_subagents(self):
        lead = Transcript("lead").call(5_000, tools=[("T1", "Bash", {"command": "ls"})]).result("T1", chars=40)
        lead.call(5_100, text="done")
        with tempfile.TemporaryDirectory() as pdir:
            write_session(pdir, "ffff6666-0000-4000-8000-000000000000", lead)
            self.assertIn("shell output", run(pdir, "--diagnose", "ffff6666").stdout)
            self.assertEqual(json.loads(run(pdir, "--json", "ffff6666").stdout)[0]["agents"], 0)

    def test_diagnose_needs_a_session(self):
        with tempfile.TemporaryDirectory() as pdir:
            standard_session(pdir)
            p = run(pdir, "--diagnose", check=False)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("needs one or more sessions", p.stderr)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to check they fail**

Run: `python -m unittest discover -s scripts/tests -v`
Expected: FAIL with `unrecognized arguments: --json` (exit code 2).

- [ ] **Step 3: Add `report` to `diagnose.py`**

```python
def report(pdir, ref, hung_min=10):
    """Stats, diagnosis, health and the per-call series for one session, as one JSON-ready dict."""
    pdir, main = find_session(pdir, ref)
    agents = load_session(pdir, main)[2]
    r = stats(pdir, main)
    r.update(diagnosis=diagnose(agents), health=health(agents, hung_min),
             series=[dict(ts=c["ts"], ctx=c["ctx"], out=c["out"], agent=i)
                     for i, a in enumerate(agents) for c in a["calls"]])
    return r
```

- [ ] **Step 4: Add the CLI**

In `scripts/agent-tokens.py`, add `import json` to the imports, and:

```python
from diagnose import CHARS_PER_TOKEN, report
```

Add after `share`:

```python
def print_diagnosis(pdir, ref, hung_min):
    r = report(pdir, ref, hung_min)
    d = r["diagnosis"]
    print(f"session {r['sid']}  ({r['label']})")
    print(f"  where the tokens went, of {d['total'] / 1e6:.2f}M "
          f"(tool output estimated at {CHARS_PER_TOKEN} characters a token):")
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
        print(f"  the estimate covers {d['coverage']:.0%} of the measured growth in context")
    print("  health: " + ("no problems found" if not r["health"] else f"{len(r['health'])} found"))
    for h in r["health"]:
        print(f"    {h['kind']}: {h['agent']}: {h['detail']}")
```

In `main`, add the arguments after `--share`:

```python
    ap.add_argument("--diagnose", action="store_true",
                    help="for each session: where the tokens went, with a fix per cause, and agent health")
    ap.add_argument("--json", action="store_true", help="for each session: stats, diagnosis and health as JSON")
    ap.add_argument("--hung-min", type=float, default=10,
                    help="minutes a tool call may wait before it counts as hung (default 10)")
```

After `args = ap.parse_args()`, add:

```python
    for flag in ("diagnose", "json"):
        if getattr(args, flag) and not args.sessions:
            raise SystemExit(f"--{flag} needs one or more sessions")
```

In the dispatch, before `elif args.sessions:`, add:

```python
    elif args.json:
        print(json.dumps([report(pdir, s, args.hung_min) for s in args.sessions], indent=1))
    elif args.diagnose:
        for s in args.sessions:
            print_diagnosis(pdir, s, args.hung_min)
```

Add to the module docstring's usage block:

```
    python agent-tokens.py --diagnose 3f2a9c1e   # where the tokens went, with fixes, and agent health
    python agent-tokens.py --json 3f2a9c1e       # the same figures as JSON, for the benchmark
```

- [ ] **Step 5: Run all script tests**

Run: `python -m unittest discover -s scripts/tests -v`
Expected: PASS. The golden test is unchanged, because the docstring only shows in `--help`.

- [ ] **Step 6: Try it on a real session**

Run: `python scripts/agent-tokens.py --project-dir "$HOME/.claude/projects/<your project folder>"` to list sessions, then `--diagnose <prefix>` on the largest one.
Expected: a ranked list of causes. Coverage should land between about 60% and 140%. If it's outside that, note the figure in the task report: it means the characters-per-token estimate is off for this kind of content.

- [ ] **Step 7: Commit**

```bash
git add scripts/agent-tokens.py scripts/diagnose.py scripts/tests/test_cli.py
git commit -m "Add --diagnose and --json: where a session's tokens went, what to change, and which agents failed"
```

---

### Task 6: Tiers, setup, grading and validation (`bench/tasks.py`)

**Files:**
- Create: `bench/tasks.py`
- Create: `bench/tests/helpers.py`
- Create: `bench/tests/test_tasks.py`

**Interfaces:**
- Produces:
  - `tasks.load_tier(folder) -> dict`, with the tier.json fields plus `name` (folder name), `notes` (default `""`) and `tasks` (a list of task dicts). Raises `ValueError` naming the file and the missing fields.
  - `tasks.tasks_md(tier) -> str`
  - `tasks.sh(cmd, cwd, timeout) -> (code | None, output)`
  - `tasks.failing(tier, clone, timeout=1800) -> set[str] | None`
  - `tasks.prepare(tier, clone, timeout=1800) -> set[str]`, the failing test ids at the base. Raises `RuntimeError` if the clone exists, or if cloning, setup or the suite fails.
  - `tasks.grade(tier, clone, before, timeout=1800) -> dict(new_failures: list | None, tasks=[dict(task, hidden: "pass"|"fail"|"error", detail)])`
  - `tasks.validate(tier, workdir, timeout=1800) -> list[str]` of problems (empty means the tier is valid).
- Produces in `bench/tests/helpers.py`: `make_tier(root) -> tier_folder` (a tiny local upstream repo with one task) and `git_env()`.

- [ ] **Step 1: Write the test helper**

Create `bench/tests/helpers.py`:

```python
"""A tiny upstream repository with one bug and its fix, laid out as a benchmark tier."""

import json
import os
import subprocess
import sys

BENCH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(BENCH)
sys.path.insert(0, BENCH)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "scripts", "tests"))


def git_env():
    env = dict(os.environ)
    env.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    return env


def _write(folder, name, text):
    with open(os.path.join(folder, name), "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def make_tier(root, setup=()):
    repo = os.path.join(root, "upstream")
    os.makedirs(repo)

    def git(*args):
        return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True,
                              env=git_env()).stdout.strip()

    git("init", "-q")
    _write(repo, "calc.py", "def add(a, b):\n    return a - b\n")
    _write(repo, "test_basic.py", "import unittest\n\n\nclass T(unittest.TestCase):\n"
                                  "    def test_ok(self):\n        self.assertTrue(True)\n")
    git("add", ".")
    git("commit", "-qm", "base")
    base = git("rev-parse", "HEAD")
    _write(repo, "calc.py", "def add(a, b):\n    return a + b\n")
    _write(repo, "test_hidden.py", "import unittest\n\nfrom calc import add\n\n\nclass H(unittest.TestCase):\n"
                                   "    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n")
    git("add", ".")
    git("commit", "-qm", "fix add")
    fix = git("rev-parse", "HEAD")
    tier = os.path.join(root, "tier-tiny")
    os.makedirs(tier)
    py = f'"{sys.executable}"'
    with open(os.path.join(tier, "tier.json"), "w", encoding="utf-8") as f:
        json.dump(dict(repo=repo, base_commit=base, setup=list(setup),
                       suite_cmd=f"{py} -m unittest discover -v",
                       failure_regex=r"^(\w+) \(.+\) \.\.\. (?:FAIL|ERROR)"), f)
    with open(os.path.join(tier, "add.json"), "w", encoding="utf-8") as f:
        json.dump(dict(name="add", issue="add() subtracts instead of adding.", fix_ref=fix,
                       hidden_tests=["test_hidden.py"], hidden_test_cmd=f"{py} -m unittest test_hidden"), f)
    return tier
```

- [ ] **Step 2: Write the failing tests**

Create `bench/tests/test_tasks.py`:

```python
import json
import os
import subprocess
import tempfile
import unittest

from helpers import git_env, make_tier
import tasks


class Tasks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ.update(git_env())
        self.tier = tasks.load_tier(make_tier(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_load_and_tasks_md(self):
        self.assertEqual((self.tier["name"], len(self.tier["tasks"])), ("tier-tiny", 1))
        md = tasks.tasks_md(self.tier)
        self.assertIn("## add", md)
        self.assertIn("add() subtracts", md)

    def test_missing_field_is_named(self):
        folder = os.path.join(self.tmp.name, "tier-tiny")
        with open(os.path.join(folder, "bad.json"), "w", encoding="utf-8") as f:
            json.dump({"name": "bad"}, f)
        with self.assertRaisesRegex(ValueError, r"bad\.json: missing issue, fix_ref"):
            tasks.load_tier(folder)

    def test_unfixed_clone_fails_hidden_tests_and_fixed_one_passes(self):
        clone = os.path.join(self.tmp.name, "work", "arm")
        before = tasks.prepare(self.tier, clone)
        self.assertEqual(before, set())
        g = tasks.grade(self.tier, clone, before)
        self.assertEqual((g["tasks"][0]["hidden"], g["new_failures"]), ("fail", []))
        subprocess.run(["git", "reset", "-q", "--hard"], cwd=clone, check=True)
        subprocess.run(["git", "clean", "-qfd"], cwd=clone, check=True)
        with open(os.path.join(clone, "calc.py"), "w", encoding="utf-8") as f:
            f.write("def add(a, b):\n    return a + b\n")
        g = tasks.grade(self.tier, clone, before)
        self.assertEqual(g["tasks"][0]["hidden"], "pass")

    def test_existing_clone_is_an_error_and_is_kept(self):
        clone = os.path.join(self.tmp.name, "work", "arm")
        os.makedirs(clone)
        open(os.path.join(clone, "keep.txt"), "w").close()
        with self.assertRaisesRegex(RuntimeError, "already exists"):
            tasks.prepare(self.tier, clone)
        self.assertTrue(os.path.exists(os.path.join(clone, "keep.txt")))

    def test_suite_that_cannot_run_at_the_base_is_an_error(self):
        self.tier["suite_cmd"] = "no-such-command-xyz"
        with self.assertRaisesRegex(RuntimeError, "suite"):
            tasks.prepare(self.tier, os.path.join(self.tmp.name, "work", "arm"))

    def test_validate(self):
        self.assertEqual(tasks.validate(self.tier, os.path.join(self.tmp.name, "v")), [])


if __name__ == "__main__":
    unittest.main()
```

`no-such-command-xyz` exits non-zero and prints no test ids. `failing` treats "exit code not 0 and no failing ids found" as "could not run", returning `None`, and `prepare` raises on `None`.

- [ ] **Step 3: Run the tests to check they fail**

Run: `python -m unittest discover -s bench/tests -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tasks'`.

- [ ] **Step 4: Write `bench/tasks.py`**

```python
"""Benchmark tiers: load them, set up a clone, and grade it with the hidden tests.

A tier is a folder with tier.json (repo, base commit, setup, suite) and one
JSON file per task (issue, fix commit, hidden tests). Every task in a tier
starts from the same base commit, because one session works them all.
"""

import glob
import json
import os
import re
import subprocess

TIER_FIELDS = ("repo", "base_commit", "setup", "suite_cmd", "failure_regex")
TASK_FIELDS = ("name", "issue", "fix_ref", "hidden_tests", "hidden_test_cmd")
EXCLUDE = ".venv/\nnode_modules/\n.claude/\n"


def _load(path, fields):
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    missing = [k for k in fields if k not in d]
    if missing:
        raise ValueError(f"{path}: missing {', '.join(missing)}")
    return d


def load_tier(folder):
    tier = _load(os.path.join(folder, "tier.json"), TIER_FIELDS)
    re.compile(tier["failure_regex"])
    tier["name"] = os.path.basename(os.path.normpath(folder))
    tier.setdefault("notes", "")
    paths = sorted(p for p in glob.glob(os.path.join(folder, "*.json")) if os.path.basename(p) != "tier.json")
    tier["tasks"] = [_load(p, TASK_FIELDS) for p in paths]
    if not tier["tasks"]:
        raise ValueError(f"{folder}: no task files")
    return tier


def tasks_md(tier):
    parts = [f"# Tasks: {len(tier['tasks'])} for this repository", ""]
    for t in tier["tasks"]:
        parts += [f"## {t['name']}", "", t["issue"].strip(), ""]
    if tier["notes"].strip():
        parts += ["## Notes for every task", "", tier["notes"].strip(), ""]
    return "\n".join(parts)


def sh(cmd, cwd, timeout):
    """Run a shell command; return (exit code, output). A timeout gives exit code None."""
    try:
        p = subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return None, f"timed out after {timeout}s"


def failing(tier, clone, timeout=1800):
    """The ids of failing tests in the full suite, or None if the suite could not run."""
    code, out = sh(tier["suite_cmd"], clone, timeout)
    ids = set(re.findall(tier["failure_regex"], out, re.M))
    if code is None or (code != 0 and not ids):
        return None
    return ids


def prepare(tier, clone, timeout=1800):
    """Clone at the base commit, set up, and return the tests already failing there."""
    if os.path.exists(clone):
        raise RuntimeError(f"{clone} already exists; remove it or choose another --work folder")
    os.makedirs(os.path.dirname(clone), exist_ok=True)
    steps = [f'git clone -q "{tier["repo"]}" "{clone}"', f"git -C \"{clone}\" checkout -q {tier['base_commit']}"]
    for step in steps:
        code, out = sh(step, os.path.dirname(clone), 900)
        if code != 0:
            raise RuntimeError(f"{step}: {out[-400:]}")
    with open(os.path.join(clone, ".git", "info", "exclude"), "a", encoding="utf-8", newline="\n") as f:
        f.write(EXCLUDE)
    for step in tier["setup"]:
        code, out = sh(step, clone, timeout)
        if code != 0:
            raise RuntimeError(f"setup step {step!r} failed: {out[-400:]}")
    before = failing(tier, clone, timeout)
    if before is None:
        raise RuntimeError(f"the suite could not run at the base commit: {tier['suite_cmd']}")
    return before


def grade(tier, clone, before, timeout=1800):
    """Compare the suite with the base, then copy in each task's hidden tests and run them."""
    after = failing(tier, clone, timeout)
    out = dict(new_failures=None if after is None else sorted(after - before), tasks=[])
    for t in tier["tasks"]:
        r = dict(task=t["name"])
        paths = " ".join(f'"{p}"' for p in t["hidden_tests"])
        code, msg = sh(f"git checkout {t['fix_ref']} -- {paths}", clone, 120)
        if code != 0:
            r.update(hidden="error", detail=msg[-500:])
        else:
            code, msg = sh(t["hidden_test_cmd"], clone, timeout)
            hidden = "pass" if code == 0 else ("error" if code is None else "fail")
            r.update(hidden=hidden, detail="" if code == 0 else msg[-500:])
        out["tasks"].append(r)
    return out


def validate(tier, workdir, timeout=1800):
    """Every task's hidden tests must fail at the base and pass once the real fixes are applied."""
    problems = []
    clone = os.path.join(workdir, "validate-" + tier["name"])
    before = prepare(tier, clone, timeout)
    for t, r in zip(tier["tasks"], grade(tier, clone, before, timeout)["tasks"]):
        if r["hidden"] != "fail":
            problems.append(f"{t['name']}: hidden tests {r['hidden']} at the base commit; expected fail")
    sh("git reset -q --hard && git clean -qfd", clone, 120)
    for t in tier["tasks"]:
        patch = os.path.join(workdir, f"gold-{t['name']}.patch")
        excludes = " ".join(f'":(exclude){p}"' for p in t["hidden_tests"])
        code, msg = sh(f'git diff {t["fix_ref"]}^1 {t["fix_ref"]} -- . {excludes} > "{patch}"', clone, 120)
        if code == 0:
            code, msg = sh(f'git apply "{patch}"', clone, 120)
        if code != 0:
            problems.append(f"{t['name']}: the real fix does not apply at the base: {msg[-300:]}")
    g = grade(tier, clone, before, timeout)
    for t, r in zip(tier["tasks"], g["tasks"]):
        if r["hidden"] != "pass":
            problems.append(f"{t['name']}: hidden tests {r['hidden']} with the real fix applied: {r['detail'][-300:]}")
    if g["new_failures"]:
        problems.append(f"the real fixes break other tests: {', '.join(g['new_failures'][:10])}")
    return problems
```

- [ ] **Step 5: Run the tests**

Run: `python -m unittest discover -s bench/tests -v`
Expected: PASS (6 tests).

- [ ] **Step 6: Commit**

```bash
git add bench/tasks.py bench/tests/helpers.py bench/tests/test_tasks.py
git commit -m "Add benchmark tiers: set up a clone at the base commit, grade it with hidden tests, and validate the tier"
```

---

### Task 7: Run arms in parallel with a spend cap (`bench/run.py`)

**Files:**
- Modify: `scripts/transcripts.py` (`project_dir` honours `CLAUDE_CONFIG_DIR`)
- Create: `bench/run.py`
- Create: `bench/prompt.txt`
- Create: `bench/tests/fake_claude.py`
- Create: `bench/tests/test_run.py`
- Modify: `scripts/tests/test_transcripts.py` (one test)

**Interfaces:**
- Consumes: `tasks.load_tier`, `tasks.tasks_md`, `tasks.prepare`, `tasks.grade`, `tasks.validate`, `transcripts.project_dir`, `transcripts.load_session`, `transcripts.tokens`, `diagnose.report`.
- Produces:
  - `run.parse_arm(spec) -> dict(name, ref)`
  - `run.run_arm(tier, arm, work, cap, claude, prompt, max_hours=6, poll=60) -> dict`, where `arm` may carry a ready `plugin` path
  - `run.run(tier, arms, work, cap, claude, max_hours=6, poll=60) -> results`, which also writes `<work>/<tier>/results.json`
  - `results = dict(tier, date, cap, runs_per_arm=1, tasks=[names], arms=[dict(arm, ref, cap, session, wall_s, stopped: None|"cap"|"time limit", exit, usd, grade, measure, error?, figures)])`
  - `figures = dict(tokens, cost, usd, passed, of, tokens_per_pass, wall_min, min_per_task, above_100k, peak, lead_peak, startup, rebuys, new_failures, stopped)`

- [ ] **Step 1: Make `project_dir` honour `CLAUDE_CONFIG_DIR`, with a test**

Add to `scripts/tests/test_transcripts.py`:

```python
class ConfigDir(unittest.TestCase):
    def test_claude_config_dir_moves_the_projects_folder(self):
        import transcripts
        old = os.environ.get("CLAUDE_CONFIG_DIR")
        os.environ["CLAUDE_CONFIG_DIR"] = os.path.join("x", "cfg")
        try:
            self.assertTrue(transcripts.project_dir("/a/b").startswith(os.path.join("x", "cfg", "projects")))
        finally:
            if old is None:
                del os.environ["CLAUDE_CONFIG_DIR"]
            else:
                os.environ["CLAUDE_CONFIG_DIR"] = old
```

Run: `python -m unittest discover -s scripts/tests -v`. Expected: FAIL in `test_claude_config_dir_moves_the_projects_folder`.

In `scripts/transcripts.py`, change the return line of `project_dir` to:

```python
    home = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    return os.path.join(home, "projects", re.sub(r"[^A-Za-z0-9]", "-", path))
```

Run the tests again. Expected: PASS.

- [ ] **Step 2: Write the shared prompt**

Create `bench/prompt.txt`:

```
Complete the tasks described in ../tasks.md in this repository. Use subagents: split the work across them, have each change reviewed before you accept it, and make sure the full test suite has no new failures at the end. Add tests for what you build. Commit your work on the current branch, at least one commit per task, with a message naming the task. Never push and never use the network. When done, report per task: the commits, the tests added and the result, then the final full-suite result.
```

- [ ] **Step 3: Write the fake `claude`**

Create `bench/tests/fake_claude.py`:

```python
"""Stands in for `claude -p` in tests. FAKE_MODE=fix writes a short transcript, fixes calc.py and
commits. FAKE_MODE=spend starts a child process, then keeps growing its transcript until killed."""

import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.environ["LEAN_SCRIPTS"])
sys.path.insert(0, os.environ["LEAN_TESTS"])
from fixtures import Transcript  # noqa: E402
from transcripts import project_dir  # noqa: E402

args = sys.argv[1:]
sid = args[args.index("--session-id") + 1]
path = os.path.join(project_dir(os.getcwd()), sid + ".jsonl")
t = Transcript("Complete the tasks")
if os.environ.get("FAKE_MODE") == "spend":
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    with open(os.environ["FAKE_CHILD_PID"], "w") as f:
        f.write(str(child.pid))
    for i in range(2000):
        t.call(50_000 + i * 1_000)
        t.dump(path)
        time.sleep(0.05)
    sys.exit(0)
t.call(10_000, tools=[("F1", "Edit", {"file_path": "calc.py"})]).result("F1", chars=100).call(11_000, text="done")
t.dump(path)
with open("calc.py", "w", encoding="utf-8", newline="\n") as f:
    f.write("def add(a, b):\n    return a + b\n")
subprocess.run(["git", "commit", "-qam", "Fix add"], check=True)
print(json.dumps({"total_cost_usd": 0.01, "plugin": "--plugin-dir" in args}))
```

- [ ] **Step 4: Write the failing tests**

Create `bench/tests/test_run.py`:

```python
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

from helpers import ROOT, git_env, make_tier
import run
import tasks

HERE = os.path.dirname(os.path.abspath(__file__))
FAKE = [sys.executable, os.path.join(HERE, "fake_claude.py")]


def alive(pid):
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


class Run(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ.update(git_env(), CLAUDE_CONFIG_DIR=os.path.join(self.tmp.name, "cfg"),
                          LEAN_SCRIPTS=os.path.join(ROOT, "scripts"), LEAN_TESTS=os.path.join(ROOT, "scripts", "tests"),
                          FAKE_MODE="fix", FAKE_CHILD_PID=os.path.join(self.tmp.name, "child.pid"))
        self.tier = tasks.load_tier(make_tier(self.tmp.name))
        self.work = os.path.join(self.tmp.name, "work")

    def tearDown(self):
        self.tmp.cleanup()

    def test_parse_arm(self):
        self.assertEqual(run.parse_arm("baseline"), dict(name="baseline", ref=None))
        self.assertEqual(run.parse_arm("lean+notes=cut/module-notes"), dict(name="lean+notes", ref="cut/module-notes"))

    def test_two_arms_are_graded_measured_and_written(self):
        arms = [dict(name="baseline", ref=None), dict(name="lean", ref="test", plugin=ROOT)]
        res = run.run(self.tier, arms, self.work, cap=10_000_000, claude=FAKE, poll=0.2)
        by = {a["arm"]: a for a in res["arms"]}
        for a in by.values():
            self.assertNotIn("error", a)
            self.assertEqual(a["grade"]["tasks"][0]["hidden"], "pass")
            self.assertEqual(a["figures"]["passed"], 1)
            self.assertEqual(a["figures"]["tokens"], 10_000 + 100 + 11_000 + 100)
            self.assertEqual(a["usd"], 0.01)
        self.assertTrue(os.path.exists(os.path.join(self.work, "tier-tiny", "lean", ".claude", "settings.json")))
        self.assertFalse(os.path.exists(os.path.join(self.work, "tier-tiny", "baseline", ".claude")))
        with open(os.path.join(self.work, "tier-tiny", "results.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["tasks"], ["add"])

    def test_cap_stops_the_arm_and_its_children_and_still_grades(self):
        os.environ["FAKE_MODE"] = "spend"
        res = run.run(self.tier, [dict(name="baseline", ref=None)], self.work, cap=300_000, claude=FAKE, poll=0.2)
        a = res["arms"][0]
        self.assertEqual(a["stopped"], "cap")
        self.assertEqual(a["grade"]["tasks"][0]["hidden"], "fail")
        with open(os.environ["FAKE_CHILD_PID"]) as f:
            pid = int(f.read())
        time.sleep(1)
        self.assertFalse(alive(pid))

    def test_setup_failure_stops_only_that_arm(self):
        os.makedirs(os.path.join(self.work, "tier-tiny", "broken"))
        arms = [dict(name="broken", ref=None), dict(name="baseline", ref=None)]
        res = run.run(self.tier, arms, self.work, cap=10_000_000, claude=FAKE, poll=0.2)
        by = {a["arm"]: a for a in res["arms"]}
        self.assertIn("already exists", by["broken"]["error"])
        self.assertEqual(by["baseline"]["grade"]["tasks"][0]["hidden"], "pass")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 5: Run the tests to check they fail**

Run: `python -m unittest discover -s bench/tests -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'run'`.

- [ ] **Step 6: Write `bench/run.py`**

```python
"""Run the benchmark: each arm works the same tier in its own clone, then is graded and measured.

    python bench/run.py --tier bench/tasks/long --work D:/bench-work --validate
    python bench/run.py --tier bench/tasks/long --work D:/bench-work --cap 40000000 \\
        --arm baseline --arm lean=v1 --arm lean+notes=cut/module-notes

An arm is a name, optionally with a git ref of this repository: the ref is
checked out as a worktree under <work>/plugins and loaded with --plugin-dir.
An arm without a ref runs without the plugin. Every arm is stopped once its
session passes --cap tokens, and graded on what it left.
"""

import argparse
import concurrent.futures as cf
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import tasks  # noqa: E402
from diagnose import report  # noqa: E402
from transcripts import load_session, project_dir, tokens  # noqa: E402

CLAUDE_FLAGS = ["--model", "opus", "--output-format", "json", "--permission-mode", "acceptEdits",
                "--allowedTools", "Bash", "PowerShell", "Read", "Edit", "Write", "Grep", "Glob", "Agent",
                "--disallowedTools", "Bash(git push*)", "Bash(gh *)", "Bash(curl *)", "Bash(pip *)", "Bash(uv *)",
                "Bash(npm install*)", "Bash(go get*)", "WebFetch", "WebSearch"]


def parse_arm(spec):
    name, _, ref = spec.partition("=")
    return dict(name=name, ref=ref or None)


def plugin_checkout(arm, work):
    """The plugin folder for an arm: a detached worktree of its ref, or None for no plugin."""
    if arm.get("plugin") or not arm["ref"]:
        return arm.get("plugin")
    path = os.path.join(work, "plugins", arm["name"].replace("+", "-"))
    if os.path.isdir(path):
        subprocess.run(["git", "-C", path, "checkout", "-q", "--detach", arm["ref"]], check=True, capture_output=True)
    else:
        subprocess.run(["git", "-C", ROOT, "worktree", "add", "-q", "--detach", path, arm["ref"]],
                       check=True, capture_output=True)
    return path


def kill_tree(proc):
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    else:
        os.killpg(proc.pid, signal.SIGKILL)


def transcript(clone, sid):
    """The session's main transcript, or None. The folder is named after the clone's path, which may
    be spelled through a symlink (macOS /var is /private/var), so both spellings are tried."""
    for root in (clone, os.path.realpath(clone)):
        path = os.path.join(project_dir(root), sid + ".jsonl")
        if os.path.exists(path):
            return path
    return None


def session_tokens(clone, sid):
    main = transcript(clone, sid)
    if not main:
        return 0
    return sum(tokens(a["calls"]) for a in load_session(os.path.dirname(main), main)[2])


def run_arm(tier, arm, work, cap, claude, prompt, max_hours=6, poll=60):
    clone = os.path.join(work, tier["name"], arm["name"])
    res = dict(arm=arm["name"], ref=arm["ref"], cap=cap)
    try:
        plugin = plugin_checkout(arm, work)
        before = tasks.prepare(tier, clone)
    except Exception as e:  # a failed setup stops this arm only
        res["error"] = f"setup failed: {e}"
        return res
    if plugin:
        os.makedirs(os.path.join(clone, ".claude"), exist_ok=True)
        shutil.copy(os.path.join(plugin, "skills", "lean-agent-runs", "settings-snippet.json"),
                    os.path.join(clone, ".claude", "settings.json"))
    sid = str(uuid.uuid4())
    cmd = claude + ["-p", prompt, "--session-id", sid] + CLAUDE_FLAGS + (["--plugin-dir", plugin] if plugin else [])
    start, stopped, out = time.time(), None, []
    with open(os.path.join(work, tier["name"], arm["name"] + ".stderr.txt"), "w", encoding="utf-8") as err:
        proc = subprocess.Popen(cmd, cwd=clone, stdout=subprocess.PIPE, stderr=err, text=True, encoding="utf-8",
                                errors="replace", start_new_session=os.name != "nt")
        reader = threading.Thread(target=lambda: out.append(proc.stdout.read()), daemon=True)
        reader.start()
        while proc.poll() is None:
            time.sleep(poll)
            if session_tokens(clone, sid) > cap:
                stopped = "cap"
            elif time.time() - start > max_hours * 3600:
                stopped = "time limit"
            if stopped:
                kill_tree(proc)
                break
        proc.wait()
        reader.join(10)
    res.update(session=sid, wall_s=round(time.time() - start), stopped=stopped, exit=proc.returncode)
    try:
        res["usd"] = json.loads("".join(out) or "{}").get("total_cost_usd")
    except ValueError:
        res["usd"] = None
    res["grade"] = tasks.grade(tier, clone, before)
    main = transcript(clone, sid)
    if main:
        res["measure"] = report(os.path.dirname(main), main)
    else:
        res["measure"] = None
        res["error"] = f"no transcript for session {sid} in {project_dir(clone)}; compare with the folders under it"
    return res


def summarize(res, n_tasks):
    m, g = res.get("measure"), res.get("grade") or {}
    passed = sum(1 for t in g.get("tasks", []) if t["hidden"] == "pass")
    if m:
        res["figures"] = dict(
            tokens=m["tokens"], cost=m["cost"], usd=res.get("usd"), passed=passed, of=n_tasks,
            tokens_per_pass=m["tokens"] / passed if passed else None, wall_min=res["wall_s"] / 60,
            min_per_task=res["wall_s"] / 60 / n_tasks, above_100k=m["above"], peak=m["peak"],
            lead_peak=m["lead_peak"], startup=m["startup"], rebuys=m["rewrites"],
            new_failures=g.get("new_failures"), stopped=res.get("stopped"))
    return res


def run(tier, arms, work, cap, claude, max_hours=6, poll=60):
    with open(os.path.join(HERE, "prompt.txt"), encoding="utf-8") as f:
        prompt = f.read().strip()
    tdir = os.path.join(work, tier["name"])
    os.makedirs(tdir, exist_ok=True)
    with open(os.path.join(tdir, "tasks.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(tasks.tasks_md(tier))
    with cf.ThreadPoolExecutor(len(arms)) as ex:
        futures = [ex.submit(run_arm, tier, a, work, cap, claude, prompt, max_hours, poll) for a in arms]
        done = [summarize(f.result(), len(tier["tasks"])) for f in futures]
    results = dict(tier=tier["name"], date=time.strftime("%Y-%m-%d"), cap=cap, runs_per_arm=1,
                   tasks=[t["name"] for t in tier["tasks"]], arms=done)
    with open(os.path.join(tdir, "results.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(results, f, indent=1)
    return results


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tier", required=True, help="tier folder, for example bench/tasks/long")
    ap.add_argument("--work", required=True, help="folder for clones and results (outside this repository)")
    ap.add_argument("--arm", action="append", default=[], help="name or name=git-ref; repeat for each arm")
    ap.add_argument("--cap", type=float, help="token ceiling per arm")
    ap.add_argument("--max-hours", type=float, default=6, help="time limit per arm (default 6)")
    ap.add_argument("--poll", type=float, default=60, help="seconds between spend checks (default 60)")
    ap.add_argument("--validate", action="store_true", help="check the tier is gradeable, then stop")
    args = ap.parse_args()
    tier = tasks.load_tier(args.tier)
    work = os.path.abspath(args.work)
    os.makedirs(work, exist_ok=True)
    if args.validate:
        problems = tasks.validate(tier, work)
        print("\n".join(problems) or f"{tier['name']}: every task is gradeable")
        sys.exit(1 if problems else 0)
    if not args.arm or not args.cap:
        ap.error("a run needs --arm (one or more) and --cap")
    res = run(tier, [parse_arm(a) for a in args.arm], work, args.cap, [shutil.which("claude") or "claude"],
              args.max_hours, args.poll)
    for a in res["arms"]:
        f = a.get("figures") or {}
        print(f"{a['arm']:12} {a.get('error') or ''}{f.get('tokens', 0) / 1e6:8.1f}M tokens  "
              f"{f.get('passed', 0)}/{f.get('of', 0)} passed  stopped: {a.get('stopped')}")
    print(os.path.join(work, tier["name"], "results.json"))


if __name__ == "__main__":
    main()
```

- [ ] **Step 7: Run the tests**

Run: `python -m unittest discover -s bench/tests -v`
Expected: PASS (10 tests). The cap test finishes in a few seconds: the fake passes 300,000 tokens on its first write, since each call is 50,000+ of context and the session total is summed over calls, so it passes within about 6 calls.

- [ ] **Step 8: Commit**

```bash
git add bench/run.py bench/prompt.txt bench/tests/fake_claude.py bench/tests/test_run.py scripts/transcripts.py scripts/tests/test_transcripts.py
git commit -m "Add the benchmark runner: arms in parallel clones, a spend cap that stops the whole process tree, grading and results.json"
```

---

### Task 8: The HTML report (`bench/report.py`)

**Files:**
- Create: `bench/report.py`
- Create: `bench/tests/test_report.py`

**Interfaces:**
- Consumes: the `results` dict from Task 7.
- Produces: `report.render(results) -> str` (HTML) and the CLI `python bench/report.py <results.json>`, which writes `report.html` next to it and prints its path.

- [ ] **Step 1: Write the failing test**

Create `bench/tests/test_report.py`:

```python
import unittest

import helpers  # noqa: F401  (puts bench and scripts/tests on the path)
from fixtures import ts
import report


def arm(name, tokens, ctxs, passed=1):
    series = [dict(ts=ts(i * 60), ctx=c, out=100, agent=0) for i, c in enumerate(ctxs)]
    measure = dict(diagnosis=dict(causes=[dict(cause="start-up", tokens=tokens // 2, share=0.5, fix="Use role agents",
                                               culprits=[])], patterns=[], coverage=0.9, total=tokens),
                   health=[dict(kind="hung", agent="Build <x>", detail="Bash waited 12 min")], series=series)
    figures = dict(tokens=tokens, cost=tokens / 4, usd=None, passed=passed, of=1,
                   tokens_per_pass=tokens / passed if passed else None, wall_min=10.0, min_per_task=10.0,
                   above_100k=0.5, peak=max(ctxs), lead_peak=max(ctxs), startup=8_000, rebuys=0,
                   new_failures=[], stopped=None)
    return dict(arm=name, ref=None, measure=measure, figures=figures)


RESULTS = dict(tier="long", date="2026-10-10", cap=4e7, runs_per_arm=1, tasks=["feature"],
               arms=[arm("baseline", 4_000_000, [20_000, 120_000, 300_000]), arm("lean", 1_000_000, [8_000, 30_000, 9_000])])


class Report(unittest.TestCase):
    def test_render(self):
        html = report.render(RESULTS)
        self.assertIn("<svg", html)
        self.assertEqual(html.count("<svg"), 2)
        self.assertIn("baseline", html)
        self.assertIn("−75%", html)
        self.assertIn("Single run per arm", html)
        self.assertIn("Build &lt;x&gt;", html)

    def test_arm_with_an_error_and_no_figures(self):
        r = dict(RESULTS, arms=RESULTS["arms"] + [dict(arm="broken", ref=None, error="setup failed: boom")])
        self.assertIn("setup failed: boom", report.render(r))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to check it fails**

Run: `python -m unittest discover -s bench/tests -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'report'`.

- [ ] **Step 3: Write `bench/report.py`**

```python
"""Turn a results.json into one HTML page: the comparison, the charts, the diagnosis and health.

    python bench/report.py <work>/<tier>/results.json
"""

import datetime as dt
import html
import json
import os
import sys

W, H, PAD = 760, 300, 48
ROWS = [
    ("Hidden tests passed", lambda f: f"{f['passed']}/{f['of']}", None),
    ("Tokens", lambda f: f"{f['tokens'] / 1e6:.1f}M", "tokens"),
    ("Cost-weighted tokens", lambda f: f"{f['cost'] / 1e6:.1f}M", "cost"),
    ("API-equivalent cost", lambda f: f"${f['usd']:.2f}" if f["usd"] is not None else "-", "usd"),
    ("Tokens per passing task", lambda f: f"{f['tokens_per_pass'] / 1e6:.1f}M" if f["tokens_per_pass"] else "-",
     "tokens_per_pass"),
    ("Wall clock", lambda f: f"{f['wall_min']:.0f} min", "wall_min"),
    ("Time per task", lambda f: f"{f['min_per_task']:.0f} min", "min_per_task"),
    ("Tokens on calls above 100k", lambda f: f"{f['above_100k']:.0%}", "above_100k"),
    ("Largest agent context", lambda f: f"{f['peak'] / 1e3:.0f}k" if f["peak"] else "-", "peak"),
    ("Lead peak context", lambda f: f"{f['lead_peak'] / 1e3:.0f}k", "lead_peak"),
    ("Agent start-up (median)", lambda f: f"{f['startup'] / 1e3:.1f}k" if f["startup"] else "-", "startup"),
    ("Cache rebought after waits", lambda f: f"{f['rebuys'] / 1e6:.1f}M", "rebuys"),
    ("New suite failures", lambda f: "-" if f["new_failures"] is None else str(len(f["new_failures"])), None),
    ("Stopped by", lambda f: f["stopped"] or "finished", None),
]
CSS = """
:root{--bg:#fbfaf7;--fg:#1d1d1b;--muted:#6b6a65;--line:#dedcd5;--c0:#b8572f;--c1:#2f6fb8;--c2:#3c8f5a;--c3:#8a4fb0}
@media (prefers-color-scheme:dark){:root{--bg:#18181a;--fg:#ecebe6;--muted:#a3a29c;--line:#3a3a3d;
--c0:#e58a5f;--c1:#6fa6e8;--c2:#6cc58c;--c3:#bd8ae0}}
body{background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif;max-width:820px;margin:0 auto;padding:24px 16px}
table{border-collapse:collapse;width:100%}td,th{padding:4px 8px;border-bottom:1px solid var(--line);text-align:right}
td:first-child,th:first-child{text-align:left}.muted{color:var(--muted)}svg{width:100%;height:auto}
.swatch{display:inline-block;width:10px;height:10px;border-radius:2px;margin:0 4px 0 12px}
"""


def esc(s):
    return html.escape(str(s))


def _minutes(series):
    series = [p for p in series if p["ts"]]
    if not series:
        return []
    t0 = min(dt.datetime.fromisoformat(p["ts"].replace("Z", "+00:00")) for p in series)
    return [((dt.datetime.fromisoformat(p["ts"].replace("Z", "+00:00")) - t0).total_seconds() / 60, p)
            for p in series if p["ts"]]


def chart(title, arms, points_of, dots):
    """An SVG chart, one colour per arm. points_of(series) gives [(minutes, value)]."""
    data = [(i, points_of(_minutes(a["measure"]["series"]))) for i, a in enumerate(arms)]
    xs = [x for _, pts in data for x, _ in pts] or [0]
    ys = [y for _, pts in data for _, y in pts] or [0]
    xmax, ymax = max(xs) or 1, max(ys) or 1

    def sx(x):
        return PAD + x / xmax * (W - 2 * PAD)

    def sy(y):
        return H - PAD + 8 - y / ymax * (H - 2 * PAD)

    parts = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{esc(title)}">',
             f'<line x1="{PAD}" y1="{sy(0)}" x2="{W - PAD}" y2="{sy(0)}" stroke="var(--line)"/>',
             f'<text x="{PAD}" y="16" fill="var(--muted)" font-size="12">{esc(title)}; '
             f'top {ymax / 1e3:,.0f}k, {xmax:.0f} min</text>']
    for i, pts in data:
        colour = f"var(--c{i % 4})"
        if dots:
            parts += [f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="1.8" fill="{colour}" opacity=".6"/>' for x, y in pts]
        else:
            path = " ".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y in pts)
            parts.append(f'<polyline points="{path}" fill="none" stroke="{colour}" stroke-width="2"/>')
    parts.append("</svg>")
    return "".join(parts)


def _context(points):
    return [(x, p["ctx"]) for x, p in points]


def _cumulative(points):
    total, out = 0, []
    for x, p in sorted(points, key=lambda xp: xp[0]):
        total += p["ctx"] + p["out"]
        out.append((x, total))
    return out


def _change(base, value):
    if base in (None, 0) or value is None:
        return ""
    return f"{(value - base) / base:+.0%}".replace("-", "−")


def render(results):
    arms = [a for a in results["arms"] if a.get("figures") and a.get("measure")]
    head = ["<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'>",
            f"<title>Benchmark {esc(results['tier'])}</title><style>{CSS}</style></head><body>",
            f"<h1>lean-agents benchmark: {esc(results['tier'])} tier</h1>",
            f"<p class='muted'>{esc(results['date'])}. Tasks: {esc(', '.join(results['tasks']))}. "
            f"Token cap per arm: {results['cap'] / 1e6:.0f}M.</p>"]
    if results.get("runs_per_arm", 1) == 1:
        head.append("<p><strong>Single run per arm.</strong> Agent runs vary, so differences under about 10% "
                    "are within run-to-run noise.</p>")
    for a in results["arms"]:
        if a.get("error"):
            head.append(f"<p><strong>{esc(a['arm'])}:</strong> {esc(a['error'])}</p>")
    if not arms:
        return "".join(head) + "</body></html>"
    base = arms[0]["figures"]
    table = ["<table><tr><th></th>" + "".join(f"<th>{esc(a['arm'])}</th>" for a in arms) + "</tr>"]
    for name, fmt, key in ROWS:
        cells = []
        for a in arms:
            f = a["figures"]
            change = _change(base.get(key), f.get(key)) if key and a is not arms[0] else ""
            cells.append(f"<td>{esc(fmt(f))} <span class='muted'>{change}</span></td>")
        table.append(f"<tr><td>{esc(name)}</td>{''.join(cells)}</tr>")
    table.append("</table>")
    legend = "<p>" + "".join(f"<span class='swatch' style='background:var(--c{i % 4})'></span>{esc(a['arm'])}"
                             for i, a in enumerate(arms)) + "</p>"
    charts = [legend, chart("Context size of every model call over time", arms, _context, dots=True),
              chart("Cumulative tokens over time", arms, _cumulative, dots=False)]
    diag = ["<h2>Where the tokens went</h2>"]
    for a in arms:
        d, health = a["measure"]["diagnosis"], a["measure"]["health"]
        diag.append(f"<h3>{esc(a['arm'])}</h3><ul>")
        diag += [f"<li>{esc(c['cause'])}: {c['tokens'] / 1e6:.1f}M ({c['share']:.0%}). {esc(c['fix'])}</li>"
                 for c in d["causes"][:3]]
        diag += [f"<li>{esc(h['kind'])}: {esc(h['agent'])}: {esc(h['detail'])}</li>" for h in health]
        diag.append("</ul>")
    return "".join(head + ["<h2>Comparison</h2>"] + table + ["<h2>Over time</h2>"] + charts + diag) + "</body></html>"


def main():
    path = sys.argv[1]
    with open(path, encoding="utf-8") as f:
        results = json.load(f)
    out = os.path.join(os.path.dirname(os.path.abspath(path)), "report.html")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(render(results))
    print(out)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests**

Run: `python -m unittest discover -s bench/tests -v`
Expected: PASS. The lean arm's tokens change is (1M − 4M) / 4M = −75%.

- [ ] **Step 5: Look at it**

Run: `python -c "import sys; sys.path[:0]=['bench','bench/tests','scripts/tests']; import report, test_report; open('report-sample.html','w',encoding='utf-8').write(report.render(test_report.RESULTS))"`, then open `report-sample.html` in a browser, in both light and dark mode. Check that the table reads clearly, the dots and lines show, and nothing scrolls sideways at phone width. Delete `report-sample.html` afterwards.

- [ ] **Step 6: Commit**

```bash
git add bench/report.py bench/tests/test_report.py
git commit -m "Add the benchmark report: a comparison table, context and cost over time, and the diagnosis per arm"
```

---

### Task 9: The long tier (needs the user's choice)

**Files:**
- Create: `bench/tasks/long/tier.json`
- Create: `bench/tasks/long/<task>.json`
- Create: `bench/README.md`

**Interfaces:**
- Consumes: `tasks.load_tier`, `run.py --validate`.

- [ ] **Step 1: Find candidates**

Dispatch one research agent (`general-purpose`, mid-tier model) with this prompt:

> Find 3 candidate benchmark tasks: merged GitHub pull requests in active TypeScript or Go open-source repositories. Each must add one feature that touches 15–40 files (not counting lock files, generated files or snapshots), with substantial new or changed tests in the PR. There must be a clear issue or design description that explains what to build without giving the code. The test suite must run offline in under 10 minutes with no database, Docker or network, and the repository must install with a standard command (`npm ci`, `pnpm install`, `go mod download`). For each, report: repo URL, PR number and title, merge commit sha, the parent commit sha, the files-changed count, the test files in the PR, the install and test commands, the time the suite takes if the repo documents it, and a link to the issue or description. Prefer PRs from the last 2 years. Report in under 60 lines. Do not clone large repositories; use `gh` or the GitHub web pages.

- [ ] **Step 2: The user chooses one**

Show the user the 3 candidates in a table and ask which to use. Stop until they answer.

- [ ] **Step 3: Write the tier**

`bench/tasks/long/tier.json`:

```json
{
  "repo": "<repo URL from the chosen candidate>",
  "base_commit": "<the parent commit sha>",
  "setup": ["<install command>"],
  "suite_cmd": "<full test command>",
  "failure_regex": "<regex whose first group is a failing test id in this runner's output>",
  "notes": "Install is done. Never run the install command again."
}
```

`bench/tasks/long/<short-name>.json`:

```json
{
  "name": "<short-name>",
  "issue": "<the issue or design text, copied in full; no PR description, no code from the PR>",
  "fix_ref": "<the merge commit sha>",
  "hidden_tests": ["<each test file the PR added or changed>"],
  "hidden_test_cmd": "<command that runs only those test files>"
}
```

For `failure_regex`, use the runner's per-test failure line: for Go, `^--- FAIL: (\S+)`; for Vitest or Jest, find the line format in the repo's own test output by running the suite once at the base with one test deliberately broken.

- [ ] **Step 4: Validate the tier**

Run: `python bench/run.py --tier bench/tasks/long --work <a folder outside this repo>/validate --validate`
Expected: `long: every task is gradeable`. If it fails, fix the commands or regex, or go back to Step 2 with the next candidate.

- [ ] **Step 5: Write `bench/README.md`**

```markdown
# Benchmark

Real changes from open-source repositories, with the tests from the real fix hidden from the agents and run afterwards. Each arm works the same tier in its own clone, at the same time, with the same prompt (`prompt.txt`), model and permissions.

    python bench/run.py --tier bench/tasks/long --work <folder> --validate
    python bench/run.py --tier bench/tasks/long --work <folder> --cap <tokens> --arm baseline --arm lean=main
    python bench/report.py <folder>/long/results.json

An arm is a name, with an optional git ref of this repository whose plugin it loads. `--cap` stops any arm whose session passes that many tokens and grades what it left. Results are graded on the hidden tests passed and any new suite failures, and measured with `scripts/agent-tokens.py`.

`rich/` holds the first published comparison (five open Rich bugs, graded by hand, so it is not part of the graded suite). `CUTS.md` records every cut tried and its result.
```

- [ ] **Step 6: Commit**

```bash
git add bench/tasks/long bench/README.md
git commit -m "Add the long tier: one large merged change, validated so its hidden tests fail at the base and pass with the real fix"
```

---

### Task 10: The module-notes cut (on its own branch)

**Files (on branch `cut/module-notes`, from `v1` after Task 9):**
- Modify: `agents/builder.md` (new section before `## Report`)
- Modify: `agents/fixer.md` (new section before `## Report`)
- Modify: `skills/lean-agent-runs/SKILL.md` (rule 4)

- [ ] **Step 1: Branch**

```bash
git switch -c cut/module-notes v1
```

- [ ] **Step 2: Add the section to `agents/builder.md`**

Insert before `## Report`:

```markdown
## Module notes

What you learned about the code outlives your task in `<git common dir>/lean-notes/modules/<area>.md`, one file per area you worked in (a folder or a subsystem; name it after the folder). Before you end, for each area you actually learned, rewrite that file whole in under about 40 lines: where things live (files and line ranges), the conventions, the traps, the exact command that tests the area, and on the first line the commit you checked it at. Merge with what is there; never just append. Don't write notes for areas you only glanced at.

Notes you are given are hints. If the files have changed since the commit on a note's first line, check the lines you rely on with a targeted search.
```

- [ ] **Step 3: Add the same section to `agents/fixer.md`**

Insert the identical block from Step 2 before `## Report` in `agents/fixer.md`.

- [ ] **Step 4: Extend rule 4 in `SKILL.md`**

In `skills/lean-agent-runs/SKILL.md`, at the end of rule 4 (after "...and pass the path."), add:

```markdown
 Before writing a brief, look for module notes in `<git common dir>/lean-notes/modules/` for the areas the task touches, and paste the lines the agent needs into the brief. Never tell an agent to read all the notes.
```

- [ ] **Step 5: Check the agents still load**

Run: `claude -p "List the agents you can spawn whose names start with lean-agents" --plugin-dir . --output-format text`
Expected: the output names `lean-agents:builder` and `lean-agents:fixer` (the frontmatter is unchanged, so they still load).

- [ ] **Step 6: Commit**

```bash
git add agents/builder.md agents/fixer.md skills/lean-agent-runs/SKILL.md
git commit -m "Try module notes: builders and fixers keep short notes per area, and the lead pastes the relevant lines into briefs"
git switch v1
```

---

### Task 11: The run (needs the user's go-ahead)

**Files:**
- Create: `bench/results/<date>-long/results.json` and `report.html` (copied from the work folder)

- [ ] **Step 1: Dry run on the tiny tier**

Build the tiny tier from the tests in a scratch folder, and run it with the real `claude` and a small cap, to check the real CLI flags, the transcript location and the plugin loading:

```bash
python -c "import sys; sys.path[:0]=['bench/tests']; import helpers; print(helpers.make_tier(sys.argv[1]))" <scratch>/tiny
python bench/run.py --tier <scratch>/tiny/tier-tiny --work <scratch>/dry --cap 400000 --poll 15 --arm baseline --arm lean=v1
```

Expected: both arms finish or stop at the cap. `results.json` has a `measure` for each arm, and the lean arm's `measure.by_role` shows `lean-agents:` role agents if any were spawned. If an arm has `error: no transcript at …`, compare that folder name with the folders under `~/.claude/projects/` and fix `project_dir`. Then render the report: `python bench/report.py <scratch>/dry/tier-tiny/results.json`.

- [ ] **Step 2: Set the cap with the user**

Run `python scripts/agent-tokens.py --project-dir <a project folder with heavy past sessions>` and show the user the largest recent sessions' token totals. Ask the user how much weekly usage one of those sessions took, and agree a cap per arm such that the total of all three arms at the cap stays well inside the 35% they have. Write the agreed cap down in the task report. Stop until the user agrees.

- [ ] **Step 3: The real run**

```bash
python bench/run.py --tier bench/tasks/long --work <work folder outside the repo> --cap <agreed> \
  --arm baseline --arm lean=v1 --arm lean+notes=cut/module-notes
python bench/report.py <work folder>/long/results.json
```

Run it in the background. It can take hours. When it finishes, open `report.html` and read the per-arm diagnosis.

- [ ] **Step 4: Keep the result**

```bash
mkdir -p bench/results/<date>-long
cp <work folder>/long/results.json <work folder>/long/report.html bench/results/<date>-long/
git add bench/results/<date>-long
git commit -m "Record the first long-tier run: baseline, lean and lean with module notes"
```

---

### Task 12: Verdict, CUTS.md, README and v1.0

**Files:**
- Create: `bench/CUTS.md`
- Modify: `README.md`
- Modify: `.claude-plugin/plugin.json`
- Modify: `bench/README.md` (link to the result)

- [ ] **Step 1: Apply the ship rule to module notes**

From `bench/results/<date>-long/results.json`, compare `lean+notes` with `lean`. The cut passes only if all three hold: (1) `passed` is the same or higher; (2) `tokens` is more than 10% lower; (3) in `measure.diagnosis.causes`, the `re-reads` tokens are lower.

- [ ] **Step 2: Write `bench/CUTS.md`**

```markdown
# Cuts

Every change tried to make runs cheaper, with its benchmark result. A cut merges only if the hidden tests pass as often or more, total tokens fall by more than 10% against the current plugin, and the drop shows in the cause it targets. Single runs per arm unless noted.

| Date | Cut | Tier | Tests passed (lean → cut) | Tokens (lean → cut) | Targeted cause (lean → cut) | Verdict |
|---|---|---|---|---|---|---|
| <date> | Module notes (`cut/module-notes`) | long | <a>/<n> → <b>/<n> | <x>M → <y>M (<change>) | re-reads <p>M → <q>M | <Merged / Rejected: reason> |
```

Fill the row from `results.json`.

- [ ] **Step 3: Merge the cut if it passed**

If it passed: `git merge --no-ff cut/module-notes -m "Merge module notes: <change> tokens on the long tier with tests passing as before"`. If it didn't, leave the branch unmerged; CUTS.md records why.

- [ ] **Step 4: Rewrite the README**

Edit `README.md`:
- Replace the "Tested on an open-source repo" section with **"Benchmark"**: a table for the long tier (baseline against lean, plus the cut's column if it merged), using the `ROWS` figures from the report, followed by the context-over-time chart. Commit the chart as an image: take a screenshot of the first chart in `report.html`, save it as `bench/results/<date>-long/context.png`, and link it. Then one paragraph saying it is a single run per arm, what the cap was and whether it stopped any arm, and that the tests were hidden from the agents. Keep the Rich result as two sentences with a link to `bench/rich`, described as the light-job minimum.
- Add `--diagnose` to "Where it helps most" → "Measure first": "Run `scripts/agent-tokens.py --diagnose <session>` to see which causes your tokens went to, and the setting or rule that cuts each one."
- Add a short "Keep cutting" section: the loop in four lines (diagnose → cut on a branch → benchmark → ship rule), with links to `bench/README.md` and `bench/CUTS.md`.
- Keep the existing install, use and settings sections as they are.

- [ ] **Step 5: Version**

In `.claude-plugin/plugin.json`, change `"version": "0.1.0"` to `"version": "1.0.0"`.

- [ ] **Step 6: Run every test**

Run: `python -m unittest discover -s scripts/tests -v` and `python -m unittest discover -s bench/tests -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add bench/CUTS.md README.md .claude-plugin/plugin.json bench/README.md bench/results
git commit -m "v1.0: the long-tier benchmark result, the diagnosis report and the cut loop"
```

Then use superpowers:finishing-a-development-branch to merge `v1` into `main` or open a PR.
