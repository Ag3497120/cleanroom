"""History scope, source retrieval and honest local request accounting."""
import os
from pathlib import Path
import tempfile
from unittest import TestCase, mock

from verantyx import session_store as sessions
from verantyx.context_meter import capture, composition, read
from verantyx.conversation_view import LineStyles, owner_page
from verantyx.owner_archive import page


class OwnerArchiveTests(TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        (self.root / ".verantyx").mkdir()
        env = mock.patch.dict(os.environ, {"VERANTYX_PERSONAL_HOME": str(self.root / "profile")})
        env.start()
        self.addCleanup(env.stop)
        self.room = sessions.current(self.root)["room"]["id"]

    def test_all_conversations_and_pages_stay_in_the_owner_room(self):
        states = []
        for index in range(15):
            run = "run-" + str(index)
            sessions.new_agent(self.root, "Conversation " + str(index))
            sessions.bind_run(self.root, run)
            states.append({"run_id": run, "request": "Request " + str(index), "work_session": {"context": {}},
                           "work_turns": [{"source_ref": "answer-" + str(index), "revision": 3,
                                           "proposal": {"answer": "Original answer " + str(index), "learning_notes": []}}]})
        for index in range(210):
            sessions.save_memo(self.root, "memo " + str(index), key="memo-" + str(index))
        other = sessions.new_room(self.root, "Separate")
        sessions.save_memo(self.root, "not in first room", key="private")
        sessions.bind_run(self.root, "outside")
        states.append({"run_id": "outside", "request": "outside conversation", "work_session": {"context": {}}})
        snapshot = {"project_revision": 1, "states": states, "events": []}
        first = page(self.root, self.room, snapshot)
        second = page(self.root, self.room, snapshot, offset=200)
        self.assertEqual(first["total"], 240)
        self.assertEqual(len(first["items"]) + len(second["items"]), 240)
        original = page(self.root, self.room, snapshot, query="Original answer 0")
        self.assertIn("Original answer 0", [row["text"] for row in original["items"]])
        foreign = page(self.root, other["room"]["id"], snapshot)
        self.assertEqual(foreign["total"], 2)
        self.assertNotIn("not in first room", str(first["items"] + second["items"]))
        self.assertEqual(sessions.memo_page(self.root, self.room)["total"], 210)

    def test_search_matches_normalized_terms_marks_line_and_keeps_context(self):
        sessions.save_memo(self.root, "before\nＡＢＣ 100%\nafter", key="source")
        result = page(self.root, self.room, {"states": []}, query="abc 100%")
        self.assertEqual(result["total"], 1)
        lexer = LineStyles()
        rendered = owner_page({"owner_archive": True, "memo_page": result}, result["items"],
                              "abc 100%", None, [], 50, "ja", lexer)
        self.assertIn("▶ 2 │ ＡＢＣ 100%", rendered)
        self.assertIn("before", rendered)
        self.assertIn("after", rendered)
        self.assertIn("class:owner.match", lexer.rows)
        self.assertEqual(page(self.root, self.room, {"states": []}, query="_")["total"], 0)

    def test_context_counts_partition_bytes_and_never_store_prompt_bodies(self):
        request = {"run_id": "run", "request": "secret日本語", "turns": [{"answer": "earlier"}],
                   "tool_receipts": [{"text": "tool"}], "project_context": {"skills": {"items": ["procedure"]}},
                   "personal_context": {"sharing": "PRIVATE", "records": []}, "capture_learning": True}
        result = composition(request)
        self.assertEqual(sum(result["categories"].values()), result["bytes"])
        self.assertGreater(result["categories"]["skills"], 0)
        self.assertEqual(result["unit"], "UTF8_BYTES_NOT_TOKENS")
        capture(self.root, request, {})
        self.assertEqual(read(self.root)["sharing"], "PRIVATE")
        text = (self.root / ".verantyx/context-usage.json").read_text()
        self.assertNotIn("secret", text)
        self.assertNotIn("procedure", text)
        self.assertEqual((self.root / ".verantyx/context-usage.json").stat().st_mode & 0o777, 0o600)

    def test_corrupt_meter_cannot_break_the_composer(self):
        path = self.root / ".verantyx/context-usage.json"
        path.write_text('{"unit":"UTF8_BYTES_NOT_TOKENS","bytes":3,"categories":{"skills":"many"}}')
        self.assertIsNone(read(self.root))
