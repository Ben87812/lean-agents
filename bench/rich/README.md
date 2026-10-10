# Rich comparison

Five open bugs in Textualize/rich at commit `9d8f9a3`, fixed by one Claude Code run without the plugin and one with it, in parallel, with the same prompt (`prompt.txt`), model and permissions.

```
sh run.sh <work folder> <path to lean-agents>
```

Then, inside `<work folder>/baseline` and `<work folder>/lean`, run `python <path to lean-agents>/scripts/agent-tokens.py` for the session list and add the session id for the detail.

`tasks-notes.md` lists 8 tests that failed before any change on the Windows machine used for the published result. On another platform, run the suite once first and edit that list.

Agent runs vary, so expect your figures to differ from the published ones, and run more than once if you can.
