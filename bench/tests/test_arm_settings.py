import json
import os
import subprocess
import sys
import tempfile
import unittest

from helpers import BENCH, ROOT

SCRIPT = os.path.join(BENCH, "arm_settings.py")


class ArmSettings(unittest.TestCase):
    """The shell kits (bench/rich, bench/pytest) write each arm's settings through arm_settings.py."""

    def run_script(self, cfg, *args):
        env = dict(os.environ, CLAUDE_CONFIG_DIR=cfg)
        subprocess.run([sys.executable, SCRIPT, *args], check=True, env=env)

    def test_baseline_and_lean_arms_switch_off_an_installed_lean_agents(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = os.path.join(tmp, "cfg")
            os.makedirs(cfg)
            with open(os.path.join(cfg, "settings.json"), "w", encoding="utf-8") as f:
                json.dump({"enabledPlugins": {"lean-agents@lean-agents": True}}, f)
            base, lean = os.path.join(tmp, "baseline"), os.path.join(tmp, "lean")
            os.makedirs(base)
            os.makedirs(lean)
            self.run_script(cfg, base)
            self.run_script(cfg, lean, ROOT)
            with open(os.path.join(base, ".claude", "settings.json"), encoding="utf-8") as f:
                b = json.load(f)
            with open(os.path.join(lean, ".claude", "settings.json"), encoding="utf-8") as f:
                l = json.load(f)
        self.assertEqual(b, {"enabledPlugins": {"lean-agents@lean-agents": False}})
        self.assertEqual(l["enabledPlugins"], {"lean-agents@lean-agents": False})
        self.assertIn("env", l)


if __name__ == "__main__":
    unittest.main()
