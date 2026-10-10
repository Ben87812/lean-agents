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
        self.assertTrue(os.path.exists(os.path.join(self.work, "tier-tiny", "lean", "repo", ".claude", "settings.json")))
        with open(os.path.join(self.work, "tier-tiny", "results.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["tasks"], ["add"])

    def test_installed_lean_agents_is_switched_off_in_every_arm(self):
        cfg = os.environ["CLAUDE_CONFIG_DIR"]
        os.makedirs(cfg, exist_ok=True)
        with open(os.path.join(cfg, "settings.json"), "w", encoding="utf-8") as f:
            json.dump({"enabledPlugins": {"lean-agents@lean-agents": True, "other@market": True}}, f)
        arms = [dict(name="baseline", ref=None), dict(name="lean", ref="test", plugin=ROOT)]
        run.run(self.tier, arms, self.work, cap=10_000_000, claude=FAKE, poll=0.2)
        for arm in ("baseline", "lean"):
            with open(os.path.join(self.work, "tier-tiny", arm, "repo", ".claude", "settings.json"), encoding="utf-8") as f:
                settings = json.load(f)
            self.assertEqual(settings["enabledPlugins"], {"lean-agents@lean-agents": False})
        self.assertIn("env", settings)  # the lean arm keeps the settings snippet

    def test_each_arm_has_its_own_folder_so_nothing_written_above_the_clone_is_shared(self):
        arms = [dict(name="baseline", ref=None), dict(name="lean", ref="test", plugin=ROOT)]
        run.run(self.tier, arms, self.work, cap=10_000_000, claude=FAKE, poll=0.2)
        for arm in ("baseline", "lean"):
            folder = os.path.join(self.work, "tier-tiny", arm)
            self.assertTrue(os.path.isdir(os.path.join(folder, "repo", ".git")))
            self.assertTrue(os.path.isfile(os.path.join(folder, "tasks.md")))
        self.assertFalse(os.path.exists(os.path.join(self.work, "tier-tiny", "tasks.md")))

    def test_an_arm_with_no_model_calls_is_recorded_and_results_are_still_written(self):
        os.environ["FAKE_MODE"] = "empty"
        res = run.run(self.tier, [dict(name="baseline", ref=None)], self.work, cap=10_000_000, claude=FAKE, poll=0.2)
        self.assertIn("no model calls", res["arms"][0]["error"])
        self.assertTrue(os.path.exists(os.path.join(self.work, "tier-tiny", "results.json")))

    def test_powershell_gets_the_same_blocks_as_bash(self):
        flags = run.CLAUDE_FLAGS
        for cmd in ("git push*", "gh *", "curl *", "pip *", "uv *", "npm install*", "go get*"):
            self.assertIn(f"Bash({cmd})", flags)
            self.assertIn(f"PowerShell({cmd})", flags)

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
        os.makedirs(os.path.join(self.work, "tier-tiny", "broken", "repo"))
        arms = [dict(name="broken", ref=None), dict(name="baseline", ref=None)]
        res = run.run(self.tier, arms, self.work, cap=10_000_000, claude=FAKE, poll=0.2)
        by = {a["arm"]: a for a in res["arms"]}
        self.assertIn("already exists", by["broken"]["error"])
        self.assertEqual(by["baseline"]["grade"]["tasks"][0]["hidden"], "pass")


if __name__ == "__main__":
    unittest.main()
