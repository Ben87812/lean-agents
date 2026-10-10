import json
import os
import tempfile
import unittest

from fixtures import STANDARD_SID, Transcript, standard_session, write_session
from transcripts import find_session, load_session


def agents_of(pdir, sid=STANDARD_SID):
    pdir, main = find_session(pdir, sid[:8])
    return load_session(pdir, main)[2]


class Events(unittest.TestCase):
    def test_uses_and_results_in_order(self):
        with tempfile.TemporaryDirectory() as pdir:
            standard_session(pdir)
            builder = agents_of(pdir)[1]
        kinds = [(e["kind"], e["id"]) for e in builder["events"]]
        self.assertEqual(kinds, [("use", "B1"), ("result", "B1"), ("use", "B2"), ("result", "B2"),
                                 ("use", "B3"), ("result", "B3")])
        use, res = builder["events"][0], builder["events"][1]
        self.assertEqual((use["name"], use["call"]), ("Read", 0))
        self.assertEqual(use["input"]["file_path"], "C:\\repo\\src\\calc.py")
        self.assertEqual((res["size"], res["after"], res["is_error"]), (40_000, 1, False))
        self.assertEqual(len(res["head"]), 500)

    def test_result_as_blocks_counts_text_only(self):
        t = Transcript().call(5_000, tools=[("T1", "Read", {"file_path": "a.png"})])
        t.result("T1", text="abc", as_blocks=True)
        t.lines[-1]["message"]["content"][0]["content"].append({"type": "image", "source": {"data": "Zm9v" * 100}})
        with tempfile.TemporaryDirectory() as pdir:
            write_session(pdir, "bbbb2222-0000-4000-8000-000000000000", t)
            main = agents_of(pdir, "bbbb2222")[0]
        self.assertEqual(main["events"][1]["size"], 3)

    def test_bad_lines_and_missing_fields_do_not_crash(self):
        t = Transcript().call(5_000, tools=[("T1", "Bash", {"command": "ls"})]).result("T1", chars=10)
        del t.lines[-1]["timestamp"]
        with tempfile.TemporaryDirectory() as pdir:
            path = write_session(pdir, "cccc3333-0000-4000-8000-000000000000", t)
            with open(path, "a", encoding="utf-8") as f:
                f.write("not json\n" + json.dumps({"type": "assistant", "message": {"content": None}}) + "\n")
            main = agents_of(pdir, "cccc3333")[0]
        self.assertEqual(len(main["calls"]), 1)
        self.assertIsNone(main["events"][1]["ts"])



class Robustness(unittest.TestCase):
    def test_json_lines_that_are_not_objects_are_skipped(self):
        t = Transcript().call(5_000)
        with tempfile.TemporaryDirectory() as pdir:
            path = write_session(pdir, "abab0000-0000-4000-8000-000000000000", t)
            with open(path, "a", encoding="utf-8") as f:
                f.write('[1, 2]\n"text"\n')
            self.assertEqual(len(agents_of(pdir, "abab0000")[0]["calls"]), 1)

    def test_session_without_timestamps_still_has_stats(self):
        import transcripts
        t = Transcript().call(5_000).call(5_200)
        for line in t.lines:
            line.pop("timestamp", None)
        with tempfile.TemporaryDirectory() as pdir:
            path = write_session(pdir, "acac0000-0000-4000-8000-000000000000", t)
            self.assertEqual(transcripts.stats(pdir, path)["hours"], 0)

    def test_attachments_after_the_first_call_are_messages_by_subtype(self):
        t = Transcript().call(5_000)
        t.lines.append({"type": "attachment", "timestamp": "2026-01-01T00:00:20Z",
                        "attachment": {"type": "skill_listing", "content": "s" * 400}})
        t.lines.append({"type": "attachment", "timestamp": "2026-01-01T00:00:21Z",
                        "attachment": {"type": "prompt_snapshot", "content": "p" * 9_000}})
        t.call(5_300)
        with tempfile.TemporaryDirectory() as pdir:
            write_session(pdir, "adad0000-0000-4000-8000-000000000000", t)
            ev = [e for e in agents_of(pdir, "adad0000")[0]["events"] if e["kind"] == "message"]
        self.assertEqual([(e["source"], e["after"]) for e in ev], [("skill_listing", 1)])
        self.assertGreaterEqual(ev[0]["size"], 400)


class ConfigDir(unittest.TestCase):
    def test_claude_config_dir_moves_the_projects_folder(self):
        import transcripts
        old = os.environ.get("CLAUDE_CONFIG_DIR")
        os.environ["CLAUDE_CONFIG_DIR"] = os.path.join("x", "cfg")
        try:
            self.assertTrue(transcripts.project_dir("/a/b").startswith(os.path.join("x", "cfg", "projects")))
        finally:
            if old is None:
                del os.environ["CLAUDE_CONFIG_DIR"]
            else:
                os.environ["CLAUDE_CONFIG_DIR"] = old

if __name__ == "__main__":
    unittest.main()
