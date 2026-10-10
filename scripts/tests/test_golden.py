"""agent-tokens.py's output must not change when its internals move."""

import os
import subprocess
import sys
import tempfile
import unittest

from fixtures import standard_session

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(os.path.dirname(HERE), "agent-tokens.py")
GOLDEN = os.path.join(HERE, "golden_output.txt")


def run_script(pdir, *args):
    return subprocess.run([sys.executable, SCRIPT, *args, "--project-dir", pdir], capture_output=True,
                          text=True, encoding="utf-8", check=True).stdout


class Golden(unittest.TestCase):
    def test_list_detail_and_share_unchanged(self):
        with tempfile.TemporaryDirectory() as pdir:
            standard_session(pdir)
            out = run_script(pdir) + run_script(pdir, "aaaa1111") + run_script(pdir, "--share", "aaaa1111")
        if os.environ.get("UPDATE_GOLDEN"):
            with open(GOLDEN, "w", encoding="utf-8", newline="\n") as f:
                f.write(out)
        with open(GOLDEN, encoding="utf-8") as f:
            self.assertEqual(out, f.read())


if __name__ == "__main__":
    unittest.main()
