# pytest comparison

Four open feature requests in pytest-dev/pytest at commit `e4f7f17`, built by one Claude Code run without the plugin and one with it, in parallel, with the same prompt (`prompt.txt`), model and permissions. Each run is capped at $25 of API-equivalent usage.

```
sh run.sh <work folder> <path to lean-agents>
```

Then, inside `<work folder>/baseline` and `<work folder>/lean`, run `python <path to lean-agents>/scripts/agent-tokens.py` for the session list, and compare the two with `--share <before session> <after session>`.

`tasks-notes.md` lists the tests that failed before any change on the Windows machine used for the published result. On another platform, run the suite once first and edit that list. `testing/test_faulthandler.py::test_timeout[True]` is timing-based and can fail on a busy machine in either run.

If a run ends while an agent is still working in the background, resume it with `claude -p "Finish the run: ..." --resume <session id>` and the same flags; the session's figures then cover both parts.
