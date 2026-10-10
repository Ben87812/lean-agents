"""Write a benchmark arm's project settings, as bench/run.py does: any installed lean-agents
switched off, and for a lean arm the plugin's settings snippet. Used by the shell kits.

    python arm_settings.py <clone>                    # an arm without the plugin
    python arm_settings.py <clone> <plugin folder>    # an arm with it (loaded with --plugin-dir)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from run import write_settings  # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        raise SystemExit(__doc__)
    write_settings(sys.argv[1], sys.argv[2] if len(sys.argv) == 3 else None)
