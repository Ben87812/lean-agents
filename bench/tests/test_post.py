import unittest

import helpers  # noqa: F401  (puts bench and scripts/tests on the path)
import post
from test_report import RESULTS


class Post(unittest.TestCase):
    def test_render_embeds_every_arm_with_times_from_its_first_call(self):
        page = post.render(RESULTS, "github.com/x/y")
        self.assertIn('"name":"baseline"', page)
        self.assertIn('"name":"lean"', page)
        self.assertIn('"calls":[[0.0,20000,100,0],[60.0,120000,100,0]', page)
        self.assertIn("<title>lean-agents run 2026-10-10</title>", page)

    def test_text_cannot_close_the_data_script(self):
        r = dict(RESULTS, tasks=["</script><b>x"])
        self.assertNotIn("</script><b>", post.render(r, "r").split('<script id="data"')[1].split("</script>")[0])

    def test_arm_without_figures_is_left_out(self):
        r = dict(RESULTS, arms=RESULTS["arms"] + [dict(arm="broken", ref=None, error="setup failed")])
        self.assertNotIn('"name":"broken"', post.render(r, "r"))


if __name__ == "__main__":
    unittest.main()


class Headline(unittest.TestCase):
    def setUp(self):
        from test_report import arm
        self.results = dict(RESULTS, arms=RESULTS["arms"] + [arm("cut", 900_000, [8_000, 9_000], passed=0)])

    def test_headline_is_the_second_arm_not_the_cheapest(self):
        page = post.render(self.results, "r")
        self.assertIn('"headline":"lean"', page)

    def test_only_the_chosen_arms_are_shown(self):
        page = post.render(self.results, "r", arms=["baseline", "lean"])
        self.assertNotIn('"name":"cut"', page)


class PassedAlone(unittest.TestCase):
    def test_a_pass_with_clashing_tests_set_aside_is_counted_and_footnoted(self):
        import copy
        r = copy.deepcopy(RESULTS)
        r["arms"][0]["figures"]["passed"] = 0
        r["arms"][0]["grade"] = {"tasks": [{"task": "feature", "hidden": "fail", "hidden_alone": "pass"}]}
        page = post.render(r, "r")
        self.assertIn('"alone":1', page)
        self.assertIn("own clashing test files were set aside", page)
