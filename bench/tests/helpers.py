"""A tiny upstream repository with one bug and its fix, laid out as a benchmark tier."""

import json
import os
import subprocess
import sys

BENCH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(BENCH)
sys.path.insert(0, BENCH)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "scripts", "tests"))


def git_env():
    env = dict(os.environ)
    env.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    return env


def _write(folder, name, text):
    with open(os.path.join(folder, name), "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def make_tier(root, setup=()):
    repo = os.path.join(root, "upstream")
    os.makedirs(repo)

    def git(*args):
        return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True,
                              env=git_env()).stdout.strip()

    git("init", "-q")
    _write(repo, "calc.py", "def add(a, b):\n    return a - b\n")
    _write(repo, "test_basic.py", "import unittest\n\n\nclass T(unittest.TestCase):\n"
                                  "    def test_ok(self):\n        self.assertTrue(True)\n")
    git("add", ".")
    git("commit", "-qm", "base")
    base = git("rev-parse", "HEAD")
    _write(repo, "calc.py", "def add(a, b):\n    return a + b\n")
    _write(repo, "test_hidden.py", "import unittest\n\nfrom calc import add\n\n\nclass H(unittest.TestCase):\n"
                                   "    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n")
    git("add", ".")
    git("commit", "-qm", "fix add")
    fix = git("rev-parse", "HEAD")
    tier = os.path.join(root, "tier-tiny")
    os.makedirs(tier)
    py = f'"{sys.executable}"'
    with open(os.path.join(tier, "tier.json"), "w", encoding="utf-8") as f:
        json.dump(dict(repo=repo, base_commit=base, setup=list(setup),
                       suite_cmd=f"{py} -m unittest discover -v",
                       failure_regex=r"^(\w+) \(.+\) \.\.\. (?:FAIL|ERROR)"), f)
    with open(os.path.join(tier, "add.json"), "w", encoding="utf-8") as f:
        json.dump(dict(name="add", issue="add() subtracts instead of adding.", fix_ref=fix,
                       hidden_tests=["test_hidden.py"], hidden_test_cmd=f"{py} -m unittest test_hidden"), f)
    return tier
