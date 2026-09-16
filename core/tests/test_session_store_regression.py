"""Private, fresh-profile regression coverage for independent console sessions."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from verantyx import session_store as sessions
from verantyx.errors import LedgerError


class SessionStoreRegression(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / "project"
        self.root.mkdir()
        self.environment = patch.dict(os.environ, {"VERANTYX_PERSONAL_HOME": str(self.base / "profile")})
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.temp.cleanup()

    def test_empty_profile_initializes_tables_before_indexes_and_reopens(self):
        first = sessions.current(self.root)
        self.assertEqual(first, sessions.current(self.root))
        with sessions.db() as store:
            self.assertEqual(store.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertIsNotNone(store.execute(
                "SELECT 1 FROM sqlite_master WHERE name='cr_summary_session'").fetchone())

    def test_new_agent_does_not_replace_owner_room_or_memos(self):
        first = sessions.current(self.root)
        sessions.save_memo(self.root, "Keep local copies", key="memo-1")
        second = sessions.new_agent(self.root, "Follow-up")
        self.assertNotEqual(first["agent"]["id"], second["agent"]["id"])
        self.assertEqual(first["room"], second["room"])
        self.assertEqual(sessions.memo_rows(self.root)[0]["body"], "Keep local copies")

    def test_owner_switch_preserves_agent_and_history(self):
        first = sessions.current(self.root)
        sessions.save_memo(self.root, "Original room", key="memo-1")
        second = sessions.new_room(self.root, "Research")
        self.assertEqual(first["agent"], second["agent"])
        self.assertEqual(sessions.memo_rows(self.root), [])
        sessions.switch_room(self.root, first["room"]["id"])
        self.assertEqual(sessions.memo_rows(self.root)[0]["body"], "Original room")
        with self.assertRaises(LedgerError):
            sessions.new_room(self.root, "RESEARCH")

    def test_memos_are_paginated_without_losing_older_records(self):
        for index in range(9):
            sessions.save_memo(self.root, "memo " + str(index), key=str(index))
        first = sessions.memo_page(self.root, limit=4)
        second = sessions.memo_page(self.root, limit=4, offset=4)
        final = sessions.memo_page(self.root, limit=4, offset=8)
        rows = first["rows"] + second["rows"] + final["rows"]
        self.assertEqual(first["total"], 9)
        self.assertEqual(len({row["id"] for row in rows}), 9)
        self.assertTrue(all(row["created_at"] for row in rows))
        self.assertEqual(sessions.memo_page(self.root, query="%")["total"], 0)

    def test_summary_keeps_coverage_and_original_memo(self):
        active = sessions.current(self.root)
        sessions.save_memo(self.root, "Private original", key="memo-1")
        document = {"text": "Bounded summary", "coverage": [
            {"source_ref": "event-1", "event_hash": "abc", "run_id": "run-1"}]}
        saved = sessions.save_summary(self.root, active["agent"]["id"], document)
        self.assertEqual(sessions.summary(self.root, active["agent"]["id"]), saved)
        self.assertEqual(sessions.covered_sources(
            self.root, active["agent"]["id"], ["event-1"]), {"event-1": "abc"})
        self.assertEqual(sessions.memo_rows(self.root)[0]["body"], "Private original")

    def test_workspace_edit_grant_is_scoped_and_revocable(self):
        other = self.base / "other"
        other.mkdir()
        self.assertIsNone(sessions.edit_grant(self.root))
        sessions.grant(self.root, "workspace")
        self.assertEqual(sessions.edit_grant(self.root)["scope"], "workspace")
        self.assertIsNone(sessions.edit_grant(other))
        sessions.revoke(self.root)
        self.assertIsNone(sessions.edit_grant(self.root))
