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
if os.environ.get("FAKE_MODE") == "empty":
    t.dump(path)  # a session that made no model calls, as when a usage limit is hit at once
    sys.exit(1)
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
