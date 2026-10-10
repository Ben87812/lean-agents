import unittest

import helpers  # noqa: F401  (puts bench and scripts/tests on the path)
from fixtures import ts
import report


def arm(name, tokens, ctxs, passed=1):
    series = [dict(ts=ts(i * 60), ctx=c, out=100, agent=0) for i, c in enumerate(ctxs)]
    measure = dict(diagnosis=dict(causes=[dict(cause="start-up", tokens=tokens // 2, share=0.5, fix="Use role agents",
                                               culprits=[])], patterns=[], coverage=0.9, total=tokens),
                   health=[dict(kind="hung", agent="Build <x>", detail="Bash waited 12 min")], series=series)
    figures = dict(tokens=tokens, cost=tokens / 4, usd=None, passed=passed, of=1,
                   tokens_per_pass=tokens / passed if passed else None, wall_min=10.0, min_per_task=10.0,
                   above_100k=0.5, peak=max(ctxs), lead_peak=max(ctxs), startup=8_000, rebuys=0,
                   new_failures=[], stopped=None)
    return dict(arm=name, ref=None, measure=measure, figures=figures)


RESULTS = dict(tier="long", date="2026-10-10", cap=4e7, runs_per_arm=1, tasks=["feature"],
               arms=[arm("baseline", 4_000_000, [20_000, 120_000, 300_000]), arm("lean", 1_000_000, [8_000, 30_000, 9_000])])


class Report(unittest.TestCase):
    def test_render(self):
        html = report.render(RESULTS)
        self.assertIn("<svg", html)
        self.assertEqual(html.count("<svg"), 2)
        self.assertIn("baseline", html)
        self.assertIn("−75%", html)
        self.assertIn("Single run per arm", html)
        self.assertIn("Build &lt;x&gt;", html)

    def test_arm_with_an_error_and_no_figures(self):
        r = dict(RESULTS, arms=RESULTS["arms"] + [dict(arm="broken", ref=None, error="setup failed: boom")])
        self.assertIn("setup failed: boom", report.render(r))


if __name__ == "__main__":
    unittest.main()
