# lean-agents v1.0: benchmark, diagnosis and the cut loop

Date: 2026-10-10. Status: approved in conversation, awaiting review of this written spec.

## Goal

Ship lean-agents as a public v1.0, together with a loop that keeps cutting tokens. "Skinnier" means fewer tokens with output that stays as good or better. Every cut is accepted or rejected by an objective benchmark, and users get the same diagnosis tool to cut their own runs.

## Scope

In v1.0:

1. A benchmark harness with held-out tests (`bench/run.py`, `bench/report.py`).
2. A diagnosis report in `agent-tokens.py` (`--diagnose`, `--json`), including health checks after the run.
3. Module notes as the first cut, run through the loop; it merges only if it passes the ship rule.
4. A README rewrite around the new benchmark result.

Later (v1.x): a live run monitor, a stacked ultracode mode, more repeats and tasks. Out of scope here: agent guardrails, which will be a separate plugin in the same marketplace.

## 1. Benchmark harness

### Tasks

A tier's tasks run in one session on one checkout, so they share one base commit. Each tier is a folder `bench/tasks/<tier>/` with a `tier.json`:

```json
{
  "repo": "https://github.com/owner/repo.git",
  "base_commit": "<sha that every task in the tier starts from>",
  "setup": ["commands that install the environment"],
  "suite_cmd": "command that runs the full suite",
  "failure_regex": "regex whose first group is the id of a failing test in the suite output",
  "notes": "optional notes given to the agents with every task"
}
```

and one JSON file per task:

```json
{
  "name": "...",
  "issue": "Issue text given to the agents (no PR text, no fix)",
  "fix_ref": "<sha of the merged fix>",
  "hidden_tests": ["paths of test files taken from the fix"],
  "hidden_test_cmd": "command that runs only the hidden tests"
}
```

Tests that already fail at the base commit are found by running the suite there before the agents start, so no list is kept by hand. A tier is checked before use (`run.py --validate`): every task's hidden tests must fail at the base commit, and must pass once the real fixes (each fix commit's diff without its test files) are applied, with no new suite failures.

Only tasks closed by a merged PR with tests are usable. The five open Rich bugs in `bench/rich/` have no upstream fix, so they stay as the published historical result and are not part of the graded suite.

### Tiers

| Tier | Content | Runs per arm (this round) |
|---|---|---|
| long | One large task: a single big merged PR, or a short chain of dependent PRs, from a TypeScript or Go repo. About 15–40 files touched, substantial new tests, a clear issue or design description, and tests that run fast and offline (no databases, no Docker). Big enough that a baseline lead and its subagents grow past 100k of context. | 1 |
| light | 5 closed Rich bugs with merged fixes and tests. Run only if usage remains after the long tier. | 1 |

A tier's tasks run in one session, the way real multi-agent work does. Grading is per task. The long task is chosen by the user from 3 candidates that a search agent finds, each with its file and test counts.

### Arms

An arm is a name plus a plugin source: none (baseline), or a git ref of this repo checked out as a worktree and passed with `--plugin-dir`. Lean arms also get `settings-snippet.json` merged into the clone's `.claude/settings.json`. This round runs three arms in parallel: `baseline`, `lean` (current `v1`) and `lean+notes` (branch `cut/module-notes`). Every arm gets the same prompt (`bench/prompt.txt`), model (Opus as lead), permissions and disallowed tools as `bench/rich/run.sh`.

### Run sequence (`bench/run.py`)

For each tier and arm:

1. Clone the repo into `<work>/<tier>/<arm>` at `base_commit`, run `setup`, add `.venv/`, `node_modules/` and `.claude/` to `.git/info/exclude`, and record the suite's failing tests. An existing clone folder is an error; the harness never deletes anything.
2. Write the tasks file (the issue texts plus the notes on known failures) next to the clone.
3. Run `claude -p` with the shared prompt, `--output-format json`, and the arm's plugin flags. Record the session id.
4. **Spend cap.** Every minute, read the session's transcripts with `transcripts.py`. If the arm passes its token ceiling, stop the process and go on to grading. The ceiling is set per run with `--cap` and recorded in the results. The default comes from the user's recent sessions, so the whole run stays inside the usage they have available.
5. Grade: run `suite_cmd` and record new failures (failing now, not failing at the base). Then copy each task's `hidden_tests` from `fix_ref` into the clone, run `hidden_test_cmd`, and record pass/fail per task.
6. Collect figures with `transcripts.py` and the diagnosis code (section 2) into `<work>/results.json`.

The harness is Python, so it runs on Windows, macOS and Linux. It never pushes and never uses the network after setup, except to clone.

### Results and report

`results.json` holds, per tier and arm:

- **Cost:** tokens, cost-weighted tokens, API-equivalent dollars, tokens per passing task.
- **Efficiency:** wall-clock time, time per task, cache rebuys.
- **Long-run behaviour:** share of tokens on calls above 100k, largest context, median start-up.
- **Quality:** hidden-test pass rate per task, new suite failures.
- **Run state:** whether the cap stopped the arm.
- **Series:** context size of every call, with timestamp and agent, for the charts.

`bench/report.py` turns it into one HTML page (`<work>/report.html`):

- a comparison table, arms side by side, with the change against baseline;
- a chart of context size per call over time, one line per arm (baseline ramps against the lean sawtooth);
- cumulative cost over time per arm;
- the diagnosis summary per arm.

With one run per arm, the report states plainly that it is a single run, with no claim of statistical strength.

## 2. Diagnosis report

### Shared parsing

Transcript parsing moves out of `agent-tokens.py` into `scripts/transcripts.py`: session discovery, per-agent calls and usage, tool-use inputs, and tool-result sizes. `agent-tokens.py` and `bench/run.py` both import it. `agent-tokens.py` stays the one command users run, and its current output does not change.

### Charging tokens to causes

Anything that enters an agent's context is re-sent on every later call. A tool result of n tokens arriving before call k, in an agent with N calls, is charged n × (N − k). Result sizes are estimated as characters ÷ 4, labelled approximate, and checked against the measured growth in context between calls.

| Cause | How it's spotted | Suggested fix |
|---|---|---|
| Start-up | First call's context × number of calls | Role agents; disable unused plugins; connectors off |
| File reads | Read results; whole-file reads against reads by range | Lower `LEAN_MAX_LINES`; add paths to `LEAN_ALWAYS_RANGED` |
| Re-reads | Same file read again by the same or a later agent in the session | Module notes; a better brief |
| Shell output | Bash/PowerShell results, largest commands listed | `bashOutputMaxChars`; quiet test flags in the brief |
| Subagent reports | Agent results flowing back into the lead | Shorter report format per role |
| Long agents | Tokens on calls above 100k, per agent | Hand over earlier (lower the turn cap) |
| Cache rebuys | Existing measure: cache writes after gaps over 5 minutes | Long commands to a runner |
| Model mix | Strongest model on runner, shipper or reviewer work | Model per role |
| Review rounds | More than 2 reviewer spawns for a task | Cap reviews |

### Health checks

- **Died:** the transcript ends on a tool call with no result, the agent hit `maxTurns`, or it ended without the expected output (for example "completed without StructuredOutput").
- **Hung:** the gap between a tool call and its result exceeds a threshold (default 10 minutes, `--hung-min`).
- **Looping:** the same tool call (name and identical input) 3 or more times in one agent, or the same test command failing with the same error 3 or more times.

### Interface

- `agent-tokens.py --diagnose <session>`: ranked causes with tokens, share of the total, suggested fix, the top 3 culprits per cause (file paths, commands), then any health warnings. Local output only.
- `agent-tokens.py --json <session>`: the stats, the causes and the health findings as JSON, for the harness.
- `--share` stays numbers-only: no paths, commands, prompts or ids.

## 3. Module notes (the first cut)

Notes live in `<git common dir>/lean-notes/modules/<area>.md`: outside git, shared by every worktree, and lasting across sessions in that clone. Each file records where things live, the conventions, the traps, the exact test command for the area, and the commit it was written at.

Rules:

- **Merge, never append.** An agent rewrites the whole file, under about 40 lines.
- **The lead reads, agents don't browse.** When the lead writes a brief, it pastes in the relevant lines or names the file. No agent is told to read all the notes.
- **Hints, not truth.** If the files have changed since the note's commit, agents check with a targeted search before relying on it.
- **Writers:** builders and fixers, at hand-over or at the end, for areas they actually learned. Reviewers, runners and shippers never write them.

Changes: a short section in `agents/builder.md` and `agents/fixer.md`, and one rule in `skills/lean-agent-runs/SKILL.md`. No new script. The work lives on branch `cut/module-notes`.

## The cut loop

1. Find a cause in the diagnosis report (benchmark runs or users' sessions).
2. Make the cut on a branch `cut/<name>`.
3. Run the benchmark with the arms `lean` (the current main line) and `lean+<name>`, plus `baseline` when a fresh reference is needed.
4. **Ship rule.** The cut merges only if all three hold:
   - the hidden-test pass rate is the same or better;
   - total tokens fall by more than 10% against the lean arm (with one run per arm, smaller differences are within noise);
   - the diagnosis report shows the drop in the cause the cut targets.
5. Record every cut, merged or rejected, in `bench/CUTS.md` with its numbers and the date.

## Testing

- `transcripts.py` and the diagnosis code get unit tests against small synthetic transcripts built in code by `scripts/tests/fixtures.py`: one per cause, plus the died, hung and looping cases. No real transcript text is committed.
- Before the refactor, record `agent-tokens.py`'s output on fixture sessions, and check it is unchanged afterwards.
- Dry-run `bench/run.py` on a tiny task with a cap of a few thousand tokens before the real run. That checks the clone, cap, grading and report steps cheaply.

## Error handling

- A failure in setup or cloning stops that arm and is recorded. The other arms carry on.
- A crash or cap stop of `claude -p` still goes to grading. Partial work is graded as committed and as left in the working tree.
- A hidden test that cannot be copied or run is recorded as an error, not a fail, and the report shows it.
- Missing transcripts (for example a wrong project folder) produce a clear error that names the folder searched.

## Budget for this round

The user has about 35% of their weekly usage until it resets. The long tier runs once per arm, with a cap set so that the whole benchmark fits comfortably inside that. The light tier runs only if usage remains.
