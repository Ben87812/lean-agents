# Benchmark

Real changes from open-source repositories, with the tests from the real fix hidden from the agents and run afterwards. Each arm works the same tier in its own clone, at the same time, with the same prompt (`prompt.txt`), model and permissions.

    python bench/run.py --tier bench/tasks/long --work <folder> --validate
    python bench/run.py --tier bench/tasks/long --work <folder> --cap <tokens> --arm baseline --arm lean=main
    python bench/report.py <folder>/long/results.json

An arm is a name, with an optional git ref of this repository whose plugin it loads. `--cap` stops any arm whose session passes that many tokens and grades what it left. Results are graded on the hidden tests passed and any new suite failures, and measured with `scripts/agent-tokens.py`.

`results/2026-10-10-long/` holds the first graded run (results, report, post card and replay). `rich/` holds the first published comparison (five open Rich bugs, graded by hand, so it is not part of the graded suite). `CUTS.md` records every cut tried and its result.

On Windows, use a short `--work` folder (such as `C:/bw`): some repositories have paths too long for deep folders. The long tier needs Go 1.26 or later on the PATH.
