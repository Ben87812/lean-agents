import json
import os
import subprocess
import tempfile
import unittest

from helpers import git_env, make_tier
import tasks


class Tasks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ.update(git_env())
        self.tier = tasks.load_tier(make_tier(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_load_and_tasks_md(self):
        self.assertEqual((self.tier["name"], len(self.tier["tasks"])), ("tier-tiny", 1))
        md = tasks.tasks_md(self.tier)
        self.assertIn("## add", md)
        self.assertIn("add() subtracts", md)

    def test_missing_field_is_named(self):
        folder = os.path.join(self.tmp.name, "tier-tiny")
        with open(os.path.join(folder, "bad.json"), "w", encoding="utf-8") as f:
            json.dump({"name": "bad"}, f)
        with self.assertRaisesRegex(ValueError, r"bad\.json: missing issue, fix_ref"):
            tasks.load_tier(folder)

    def test_unfixed_clone_fails_hidden_tests_and_fixed_one_passes(self):
        clone = os.path.join(self.tmp.name, "work", "arm")
        before = tasks.prepare(self.tier, clone)
        self.assertEqual(before, set())
        g = tasks.grade(self.tier, clone, before)
        self.assertEqual((g["tasks"][0]["hidden"], g["new_failures"]), ("fail", []))
        subprocess.run(["git", "reset", "-q", "--hard"], cwd=clone, check=True)
        subprocess.run(["git", "clean", "-qfd"], cwd=clone, check=True)
        with open(os.path.join(clone, "calc.py"), "w", encoding="utf-8") as f:
            f.write("def add(a, b):\n    return a + b\n")
        g = tasks.grade(self.tier, clone, before)
        self.assertEqual(g["tasks"][0]["hidden"], "pass")

    def test_clone_holds_no_history_past_the_base(self):
        clone = os.path.join(self.tmp.name, "work", "arm")
        tasks.prepare(self.tier, clone)
        fix = self.tier["tasks"][0]["fix_ref"]
        reachable = subprocess.run(["git", "rev-list", "--all", "--reflog"], cwd=clone, capture_output=True, text=True).stdout
        self.assertNotIn(fix, reachable)
        self.assertEqual(subprocess.run(["git", "cat-file", "-e", fix], cwd=clone).returncode != 0, True)
        self.assertEqual(subprocess.run(["git", "remote"], cwd=clone, capture_output=True, text=True).stdout.strip(), "")

    def test_hidden_tests_are_removed_after_grading(self):
        clone = os.path.join(self.tmp.name, "work", "arm")
        before = tasks.prepare(self.tier, clone)
        tasks.grade(self.tier, clone, before)
        self.assertFalse(os.path.exists(os.path.join(clone, "test_hidden.py")))

    def test_agent_test_file_that_breaks_the_hidden_run_is_graded_alone_too(self):
        clone = os.path.join(self.tmp.name, "work", "arm")
        before = tasks.prepare(self.tier, clone)
        with open(os.path.join(clone, "calc.py"), "w", encoding="utf-8") as f:
            f.write("def add(a, b):\n    return a + b\n")
        with open(os.path.join(clone, "test_agent.py"), "w", encoding="utf-8") as f:
            f.write("from test_hidden import helper_that_does_not_exist\n")
        self.tier["tasks"][0]["hidden_test_cmd"] = self.tier["suite_cmd"]
        r = tasks.grade(self.tier, clone, before)["tasks"][0]
        self.assertEqual((r["hidden"], r["hidden_alone"]), ("fail", "pass"))
        self.assertTrue(os.path.exists(os.path.join(clone, "test_agent.py")))

    def test_clone_allows_long_paths(self):
        clone = os.path.join(self.tmp.name, "work", "arm")
        tasks.prepare(self.tier, clone)
        out = subprocess.run(["git", "config", "--local", "core.longpaths"], cwd=clone, capture_output=True, text=True)
        self.assertEqual(out.stdout.strip(), "true")

    def test_existing_clone_is_an_error_and_is_kept(self):
        clone = os.path.join(self.tmp.name, "work", "arm")
        os.makedirs(clone)
        open(os.path.join(clone, "keep.txt"), "w").close()
        with self.assertRaisesRegex(RuntimeError, "already exists"):
            tasks.prepare(self.tier, clone)
        self.assertTrue(os.path.exists(os.path.join(clone, "keep.txt")))

    def test_suite_that_cannot_run_at_the_base_is_an_error(self):
        self.tier["suite_cmd"] = "no-such-command-xyz"
        with self.assertRaisesRegex(RuntimeError, "suite"):
            tasks.prepare(self.tier, os.path.join(self.tmp.name, "work", "arm"))

    def test_validate(self):
        self.assertEqual(tasks.validate(self.tier, os.path.join(self.tmp.name, "v")), [])


if __name__ == "__main__":
    unittest.main()
