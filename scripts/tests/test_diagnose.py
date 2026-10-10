import tempfile
import unittest

from fixtures import STANDARD_SID, Transcript, standard_session, write_session
from transcripts import find_session, load_session
import diagnose as dg


def agents_of(pdir, sid):
    pdir, main = find_session(pdir, sid[:8])
    return load_session(pdir, main)[2]


def session(main, subagents=(), sid="dddd4444-0000-4000-8000-000000000000"):
    with tempfile.TemporaryDirectory() as pdir:
        write_session(pdir, sid, main, subagents)
        return agents_of(pdir, sid)


class Charges(unittest.TestCase):
    def setUp(self):
        with tempfile.TemporaryDirectory() as pdir:
            standard_session(pdir)
            self.agents = agents_of(pdir, STANDARD_SID)

    def test_each_cause_is_charged_for_every_later_call(self):
        c = {k: round(v[0]) for k, v in dg.charges(self.agents).items()}
        # builder: 4 calls. B1 (40,000 chars = 10,000 tokens) arrives after call 1 and is re-sent 3 times.
        # Each call's output (100) is in every later call: builder 3+2+1, lead 2+1, reviewer 1.
        self.assertEqual(c, {"start-up": 20_000 * 3 + 8_000 * 4 + 6_000 * 2, "file reads": 30_000,
                             "shell output": 4_000, "re-reads": 500, "subagent reports": 2_000 + 200,
                             "search output": 300, "own output": 100 * (6 + 3 + 1)})

    def test_reread_matches_another_spelling_of_the_same_path(self):
        culprits = dg.charges(self.agents)["re-reads"][1]
        self.assertEqual(list(culprits), ["c:/repo/src/calc.py"])
        self.assertEqual(list(dg.charges(self.agents)["file reads"][1]), ["C:\\repo\\src\\calc.py (whole)"])

    def test_coverage_is_the_share_of_growth_with_a_known_source(self):
        self.assertAlmostEqual(dg.coverage(self.agents), 1.0)

    def test_diagnose_ranks_causes_with_fixes(self):
        d = dg.diagnose(self.agents)
        self.assertEqual(d["causes"][0]["cause"], "start-up")
        self.assertEqual([c["cause"] for c in d["causes"]][:2], ["start-up", "file reads"])
        self.assertTrue(all(c["fix"] for c in d["causes"]))
        self.assertAlmostEqual(sum(c["share"] for c in d["causes"]), sum(c["tokens"] for c in d["causes"]) / d["total"], 3)
        self.assertEqual(d["patterns"], [])


class Patterns(unittest.TestCase):
    def test_long_agents_rebuys_model_mix_and_review_rounds(self):
        lead = Transcript("lead").call(150_000).call(160_000)
        runner = Transcript("Run the suite").call(10_000).call(40_000, write=30_000, gap=400)
        subs = [(runner, {"agentType": "lean-agents:runner", "description": "Run the suite"})]
        for d in ("Review calc fix", "Review calc fix round 2", "Review calc fix round 3"):
            subs.append((Transcript(d, model="claude-sonnet-5-5").call(5_000),
                         {"agentType": "lean-agents:reviewer", "description": d}))
        p = dg.patterns(session(lead, subs))
        self.assertEqual(p["long agents"], {"(main thread)": 150_100 + 160_100})
        self.assertEqual(p["cache rebuys"], {"Run the suite": 30_000})
        self.assertEqual(p["model mix"], {"Run the suite": 10_100 + 40_100})
        self.assertEqual(p["review rounds"], {"review calc fix": 3})

    def test_session_without_subagents(self):
        lead = Transcript("lead").call(5_000, tools=[("T1", "Bash", {"command": "ls"})]).result("T1", chars=400)
        lead.call(5_200, text="done")
        d = dg.diagnose(session(lead))
        self.assertEqual({c["cause"] for c in d["causes"]}, {"start-up", "shell output", "own output"})

    def test_growth_beyond_the_known_sources_goes_to_images_or_other_context(self):
        lead = Transcript("lead").call(5_000, tools=[("I1", "Read", {"file_path": "shot.png"})])
        lead.result("I1", images=1).call(8_100, tools=[("T1", "Bash", {"command": "ls"})])
        lead.result("T1", chars=400).call(9_200).call(9_900, text="done")
        c = {k: round(v[0]) for k, v in dg.charges(session(lead)).items()}
        # The image arrives before call 2 (re-sent 3 times): 3,100 of growth less 100 of output.
        self.assertEqual(c["file reads"], 3_000 * 3)
        # Before call 3: 1,100 of growth, of which 100 output and 100 shell output; 900 has no source.
        self.assertEqual(c["shell output"], 100 * 2)
        # Before call 4: 700 of growth, 100 output, no other source.
        self.assertEqual(c["other context"], 900 * 2 + 600 * 1)
        # Growth is weighted by the calls it is re-sent in, as the charges are.
        self.assertAlmostEqual(dg.coverage(session(lead)), 1 - (900 * 2 + 600) / (3_100 * 3 + 1_100 * 2 + 700))

    def test_messages_between_calls(self):
        lead = Transcript("lead").call(5_000).message("y" * 2_000).call(5_600, text="ok")
        c = {k: round(v[0]) for k, v in dg.charges(session(lead)).items()}
        self.assertEqual(c["messages"], 500)
        self.assertEqual(list(dg.charges(session(lead))["messages"][1]), ["(user and system messages)"])

    def test_attachments_are_charged_to_their_subtype(self):
        lead = Transcript("lead").call(5_000)
        lead.lines.append({"type": "attachment", "timestamp": "2026-01-01T00:00:12Z",
                           "attachment": {"type": "skill_listing", "content": "s" * 1_000}})
        lead.call(5_600, text="ok")
        c = dg.charges(session(lead))
        self.assertIn("skill_listing", c["messages"][1])


if __name__ == "__main__":
    unittest.main()
