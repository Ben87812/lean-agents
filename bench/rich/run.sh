#!/bin/sh
# Rerun the Rich comparison. Needs git, gh (logged in), uv, and Claude Code.
# usage: sh run.sh <work folder> <path to the lean-agents plugin>
set -e
WORK=$1; PLUGIN=$2; HERE=$(cd "$(dirname "$0")" && pwd)
COMMIT=9d8f9a372cc5916fd4781fec207ced7ddac2f08f
mkdir -p "$WORK" && cd "$WORK"
# The task text is a reviewed snapshot kept next to this script (tasks.md), never fetched at run time:
# issue text can be written or edited by anyone, and the agents run with a shell.
{ cat "$HERE/tasks.md"; echo; cat "$HERE/tasks-notes.md"; } > tasks.md
for arm in baseline lean; do
  git clone -q https://github.com/Textualize/rich.git $arm && git -C $arm checkout -q $COMMIT
  (cd $arm && uv venv -q .venv --python 3.12 && uv pip install -q --python .venv -e . pytest attrs typing-extensions \
     && echo ".venv/" >> .git/info/exclude && echo ".claude/" >> .git/info/exclude)
done
# Both arms switch off any installed lean-agents; the lean arm loads the plugin under test with --plugin-dir.
PY=$(command -v python || command -v python3)
"$PY" "$HERE/../arm_settings.py" baseline
"$PY" "$HERE/../arm_settings.py" lean "$PLUGIN"
run_arm() { arm=$1; shift; (cd $arm && claude -p "$(cat "$HERE/prompt.txt")" --model opus --output-format json \
  --permission-mode acceptEdits --allowedTools Bash PowerShell Read Edit Write Grep Glob Agent \
  --disallowedTools "Bash(git push*)" "Bash(gh *)" "Bash(curl *)" "Bash(pip *)" "Bash(uv *)" "Bash(npm install*)" "Bash(go get*)" \
  "PowerShell(git push*)" "PowerShell(gh *)" "PowerShell(curl *)" "PowerShell(pip *)" "PowerShell(uv *)" \
  "PowerShell(npm install*)" "PowerShell(go get*)" WebFetch WebSearch \
  "$@" > ../$arm.result.json); }
run_arm baseline & run_arm lean --plugin-dir "$PLUGIN" & wait
echo "Measure each arm from inside its folder: python $PLUGIN/scripts/agent-tokens.py"
