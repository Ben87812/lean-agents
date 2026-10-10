---
name: lean-agent-runs
description: Use when leading a multi-agent or long Claude Code run (subagents, workflows, parallel features or tasks), when token use, cost or usage limits are a problem, when agents run long or their context grows past about 100k, or when setting up a repository so agent runs stay cheap.
---

# Lean agent runs

## Overview

A model call re-sends the whole context, so an agent's cost grows with the square of its length. The tokens go to **agents that live too long** and **start-up context re-sent on every call**, not to the task prompt. Cut those two mechanically, then measure.

**The saving grows with the size of the run.** Measured with these rules, quality unchanged in each:

| Run | Size | Tokens saved |
|---|---|---|
| Five bug fixes, Rich (open source) | minutes; no agent past 52k | 38% |
| Four features, pytest (open source) | about an hour; agents to 112k | 56% |
| Multi-hour tasks, private codebase | about 15 hours a task; agents to 746k | 92% |

Start-up savings apply to every run; the rest comes from stopping agents that would otherwise run long. The bigger and longer the run, the more there is to save. Details: reference.md.

## The rules

1. **Measure first.** Run `python <this skill's base directory>/../../scripts/agent-tokens.py` from the repository for a baseline, and again after the run. A claim of savings without both numbers is a guess.
2. **Every subagent is a role agent.** Spawn `lean-agents:builder`, `fixer`, `reviewer`, `runner` or `shipper`, never a general-purpose agent: the role agents carry only the tools they need and skip CLAUDE.md, so they start at about 8k to 10k tokens instead of 35k to 55k. In a workflow script, pass the type on every `agent()` call. If a role agent fails to spawn, report that; don't fall back to a general-purpose agent.
3. **Agents hand over at about 25 tool rounds** (fixers 20): commit, write notes of under 60 lines, end. A fresh agent continues from the notes. Never let one agent carry a task to the end because "it already has the context": that context is what you are paying for on every call.
4. **Every task gets a brief before any agent starts.** Up to one page: goal, files and line ranges to touch, the interfaces to use, the acceptance tests, what is out of scope, the exact test commands, and the **project rules the agents need**, since role agents start without CLAUDE.md. Write it to `<git common dir>/lean-notes/<branch>.brief.md` and pass the path.
5. **Long commands go to a runner.** A builder never waits more than about 5 minutes with a big context, because the cache can expire and the next call pays for all of it again. The builder commits, writes notes and ends; a `runner` (the smallest model) runs the full suite and reports only the failures.
6. **One build or test lane per machine.** Parallel agents fighting over one build lock or CPU waste hours. Parallelise review and writing, not compiling.
7. **Cap reviews.** One reviewer, at most 2 rounds. Minor findings are notes, never another round. Use the strongest model only for risky changes (pass `model` on the spawn).
8. **Models by role.** Builders and fixers inherit your model; reviewers and shippers use a mid-tier model; runners the smallest.
9. **You stay thin too.** The lead lives longest, so its context costs the most. Read reports and notes, not code: for briefs, search and read only the lines that locate the change. Every code edit goes to a builder or fixer, and every investigation (a flaky test, a failing suite) to a runner or fixer, however small. Batch independent tool calls in one message.
10. **Wait for every agent before ending your turn.** In a headless run (`claude -p`, CI, scripts), ending the turn ends the process and kills any agent still running in the background.

## Setup, once per repository

Ask the user before changing settings. The plugin already supplies the agents and the read and shell guards. Merge `settings-snippet.json` from this skill's folder into `.claude/settings.json`: it sets a compact backstop, an hour-long subagent cache, output caps, and switches off claude.ai connectors. Disable plugins the repository never uses, because every listing is re-sent on every call. Put generated files and big shared documents in `LEAN_ALWAYS_RANGED`.

## Red flags

| Thought | Reality |
|---|---|
| "This agent already knows the code; let it finish" | Its context is re-sent every call. Hand over. |
| "A general-purpose agent is simpler" | It starts at 35k+ tokens on every call. Use a role agent. |
| "I'll wait for the tests myself" | Over 5 minutes, the cache expires. Hand the wait to a runner. |
| "One more review round to be safe" | Two rounds maximum; the rest are notes. |
| "It's a one-line fix; I'll make it myself" | Your context is the largest in the run. Send it to a fixer. |
| "Tokens are probably down" | Run the script. |

Background, numbers and the quality check: reference.md.
