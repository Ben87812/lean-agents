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
