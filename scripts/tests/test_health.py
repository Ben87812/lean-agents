import tempfile
import unittest

from fixtures import STANDARD_SID, Transcript, standard_session, write_session
from transcripts import find_session, load_session
import diagnose as dg


def agents_of(main, subagents=(), sid="eeee5555-0000-4000-8000-000000000000"):
    with tempfile.TemporaryDirectory() as pdir:
        write_session(pdir, sid, main, subagents)
        pdir, path = find_session(pdir, sid[:8])
        return load_session(pdir, path)[2]


class Health(unittest.TestCase):
    def test_healthy_session(self):
        with tempfile.TemporaryDirectory() as pdir:
            pdir, path = find_session(pdir, standard_session(pdir))
            self.assertEqual(dg.health(load_session(pdir, path)[2]), [])

    def test_agent_that_ends_on_a_call_with_no_result_died(self):
        b = Transcript("Build it").call(5_000, tools=[("X1", "Bash", {"command": "make"})])
        h = dg.health(agents_of(Transcript("lead").call(4_000), [(b, {"description": "Build it"})]))
        self.assertEqual(h, [dict(kind="died", agent="Build it", detail="ended on Bash with no result")])

    def test_turn_limit_reported_to_the_lead(self):
        lead = Transcript("lead").call(4_000, tools=[("A1", "Agent", {"description": "Fix tests"})])
        lead.result("A1", text="Agent completed without StructuredOutput").call(4_200, text="ok")
        h = dg.health(agents_of(lead))
        self.assertEqual([(x["kind"], x["agent"]) for x in h], [("died", "Fix tests")])

    def test_hung_call(self):
        lead = Transcript("lead").call(4_000, tools=[("H1", "Bash", {"command": "npm test"})])
        lead.result("H1", chars=10, gap=700).call(4_100, text="ok")
        self.assertEqual(dg.health(agents_of(lead), hung_min=10),
                         [dict(kind="hung", agent="(main thread)", detail="Bash waited 12 min")])
        self.assertEqual(dg.health(agents_of(lead), hung_min=15), [])

    def test_a_long_subagent_or_background_command_is_not_hung(self):
        lead = Transcript("lead").call(4_000, tools=[("A1", "Agent", {"description": "Build"}),
                                                     ("B1", "Bash", {"command": "go test ./...", "run_in_background": True})])
        lead.result("A1", chars=10, gap=1_800).result("B1", chars=10, gap=1).call(4_100, text="ok")
        self.assertEqual(dg.health(agents_of(lead)), [])

    def test_looping(self):
        lead = Transcript("lead")
        for i in range(3):
            lead.call(4_000 + i, tools=[(f"P{i}", "Bash", {"command": "pytest -x"})]).result(f"P{i}", text="1 failed", is_error=True)
        lead.call(5_000, text="giving up")
        self.assertEqual(dg.health(agents_of(lead)),
                         [dict(kind="looping", agent="(main thread)", detail="Bash called 3 times with the same input")])


if __name__ == "__main__":
    unittest.main()
