# Why these rules, and what they saved

## Where the tokens went

An audit of the saved transcripts of twelve multi-agent runs on one private codebase covered 849 agents and 5.2 billion tokens. It found:

| Finding | Figure |
|---|---|
| Start-up context per agent (its task prompt was about 1k of this) | 51k to 55k tokens |
| Share of all tokens that was start-up, re-sent on every call | 30% |
| Context growth per call | about 3k tokens, so an agent's cost grows with the square of its length |
| Share of tokens on calls above 100k context | 88% |
| Tool calls per model call (almost nothing batched) | 1.07 |
| Share of tokens on the strongest model, whatever the role | 78% |
| Tokens rewritten into the cache after 5 to 60 minute gaps | 155M |
| Shell reads (`cat`, `sed -n`, `Get-Content`) against Read-tool reads | 16% against 12% of tokens |
| Ten largest agents' share in one run (context up to 746k, never handed over) | 62.5% |

Writing rules into prompts did not fix this: agents still ran to 400k to 750k context. It took making the rules mechanical (turn caps, guards, lean agent types) to change the numbers.

## Which rule fixes which cost

| Cost | Fix | Where |
|---|---|---|
| Start-up re-sent on every call | Role agents with only the tools they need and `omitClaudeMd`; unused plugins and connectors off | `agents/`, settings |
| Long-lived agents | Hand over at about 25 rounds with short notes; `maxTurns` as the hard stop; compact window as a backstop | `agents/`, settings |
| Re-reading the project's documents | One brief per task with exactly what the task needs | the lead writes it |
| Whole-file reads | Read and shell guards; output caps | `hooks/`, settings |
| Cache expiry while waiting | Long commands go to a runner; 1-hour subagent cache | `agents/runner.md`, settings |
| Strongest model everywhere | A model per role | agent frontmatter |
| Review loops | One reviewer, two rounds, minor findings as notes | the lead |
| Build-lock contention | One build lane per machine | the lead |

## Measured result

The same codebase and process, with tasks of similar size, before and after the rules:

| Per merged task | Before (4 tasks) | After (6 tasks) | Change |
|---|---|---|---|
| Tokens | 345M | 28M | −92% |
| Cost-weighted tokens (cache read 0.1, write 1.25, output 5) | 67M | 4.7M | −93% |
| Wall-clock hours | 15.3 | 3.2 | −79% |
| Median agent start-up | about 51k | 7.5k to 10k | −80% to −85% |

The largest gains come where agents run long: in the original runs they grew to as much as 746k of context without handing over. The share of tokens on calls above 100k context shows how much a run stands to save. Measure your own runs; the script makes that one command.

## Did quality drop?

Fewer tokens is worthless if the code gets worse, so compare before and after on:

- tests per 1,000 changed lines, and the test share of changed lines (leave generated files out);
- CI passing on its first run, and failed CI runs per task;
- fixer agents per task, and serious review findings per task;
- shortcuts: skipped or loosened tests, `TODO`s and lint suppressions added.

On the codebase above, all of these held level or improved: 18 tasks before against 6 after.

## Reading `agent-tokens.py`

- **tokens on calls above 100k context**: should fall towards zero once hand-over works.
- **agent start-up context**: should be about 10k with the role agents. 30k or more means general-purpose agents are still being spawned.
- **cache rewritten after gaps**: should be near zero with the 1-hour subagent cache and runners taking the long waits.
- **tool calls per model call**: higher is better; it means agents batch.
- **by model**: should show runners on the smallest model and reviewers on a mid-tier one.
