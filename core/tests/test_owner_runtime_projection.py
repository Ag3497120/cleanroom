"""Real view-reader regressions for current and historical work rows."""
from unittest import TestCase, mock
from test_provenance_mvp import ProvenanceMVP
from verantyx import agent_runtime
from verantyx.cleanroom_view import Reader
from verantyx.cleanroom_owner import render_owner, save_note
import uuid

class OwnerViewRuntime(TestCase):
    def setUp(self):
        self.h = ProvenanceMVP()
        self.h.setUp()
        self.addCleanup(self.h.doCleanups)

    def test_two_recorded_works_keep_navigation_state_and_render_current_owner(self):
        with mock.patch.object(agent_runtime, "invoke", side_effect=self.h.respond):
            first = self.h.create()
            second = self.h.create()
        reader = Reader(self.h.root, self.h.cfg)
        self.addCleanup(reader.close)
        view = reader.read(second["run_id"])
        self.assertEqual(len(view["works"]), 2)
        self.assertTrue(all("state" in work for work in view["works"]))
        self.assertIn(first["run_id"], [item["run_id"] for item in view["owner_items"]])
        body = render_owner(view, view["owner_items"])
        self.assertIn("A useful interpretation", body)
        self.assertIn("検査は未実行", body)
        self.assertNotIn("LAST ASSESSMENT", body)
        # Local search still filters reference entries; it invokes no model.
        search = render_owner(view, view["owner_items"], "main.py")
        self.assertIn("LOCAL SEARCH", search)

    def test_local_jot_is_visible_without_becoming_a_shared_owner_claim(self):
        with mock.patch.object(agent_runtime, "invoke", side_effect=self.h.respond):
            result = self.h.create()
        save_note(self.h.root, "PRIVATE UI JOT", key=uuid.uuid4().hex, run_id=result["run_id"])
        reader = Reader(self.h.root, self.h.cfg)
        self.addCleanup(reader.close)
        view = reader.read(result["run_id"])
        body = render_owner(view, view["owner_items"])
        self.assertIn("PRIVATE UI JOT", body)
        self.assertIn("自動送信なし", body)
        self.assertEqual(view["ownership_projection"]["human_decisions"], [])
        self.assertEqual(view["ownership_projection"]["human_notes"], [])
