"""Cheap unchanged display reads without weakening the event-store contract."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock
import json
import sqlite3
import sys
import uuid

from verantyx import config, agent_runtime
from verantyx.agent_models import identity
from verantyx.agent_schema import REFLECTION_REQUEST
from verantyx.cleanroom_view import Reader
from verantyx.errors import LedgerError
from verantyx.storage.sqlite import EventStore, store_path
from test_work_ownership_planes import work, tool, reflection


class ReaderSnapshotCursor(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cfg = {"schema_version": 1,
                    "project": {"id": str(uuid.uuid4()), "name": "Snapshot cursor", "purpose": "Ownership"},
                    "ui": {"locale": "ja"}, "learning": {"mode": "digest", "max_items": 2},
                    "runtime": {"backend": "none"}, "telemetry": {"enabled": False}}
        config.save(self.root, self.cfg, None)
        self.adapter = self.root / "adapter.json"
        self.adapter.write_text(json.dumps({"argv": [sys.executable, "-c", "raise SystemExit(97)"]}))
        self.model = identity(self.adapter)

    def create_work(self):
        def respond(root, adapter, request, **kwargs):
            document = (reflection(request, text="A sourced interpretation")
                        if request["format"] == REFLECTION_REQUEST else
                        work("Candidate ready", [tool("write_candidate", "sample.py", "print(1)\n")]))
            return {"document": document, "model": deepcopy(self.model)}
        with mock.patch.object(agent_runtime, "invoke", side_effect=respond):
            return agent_runtime.run_work(self.root, self.cfg, request="Build a small example",
                                          work_adapter=str(self.adapter), reflection_adapter=str(self.adapter),
                                          key=uuid.uuid4().hex)

    def store(self, **kwargs):
        return EventStore(self.root, self.cfg["project"]["id"], **kwargs)

    def test_unchanged_cursor_does_not_copy_but_public_snapshot_still_does(self):
        result = self.create_work()
        with self.store() as store:
            token, snapshot = store.project_snapshot_if_changed()
            with mock.patch("verantyx.storage.sqlite.deepcopy", side_effect=AssertionError("Unchanged copy")):
                same_token, unchanged = store.project_snapshot_if_changed(token)
            self.assertIs(same_token, token)
            self.assertIsNone(unchanged)
            snapshot["states"][0]["request"] = "Locally altered copy"
            self.assertEqual(store.project_snapshot()["states"][0]["request"], result["state"]["request"])

    def test_external_append_invalidates_the_token(self):
        self.create_work()
        with self.store() as store:
            token, before = store.project_snapshot_if_changed()
            self.create_work()
            next_token, after = store.project_snapshot_if_changed(token)
            self.assertIsNot(next_token, token)
            self.assertGreater(after["project_revision"], before["project_revision"])
            self.assertEqual(len(after["states"]), 2)

    def test_external_change_with_same_event_count_is_not_skipped(self):
        self.create_work()
        with self.store() as store:
            token, before = store.project_snapshot_if_changed()
            other = sqlite3.connect(store_path(self.root))
            try:
                other.execute("INSERT INTO metadata VALUES (?, ?)", ("cursor-probe", "changed"))
                other.commit()
            finally:
                other.close()
            next_token, after = store.project_snapshot_if_changed(token)
            self.assertIsNot(next_token, token)
            self.assertIsNotNone(after)
            self.assertEqual(after["project_revision"], before["project_revision"])

    def test_same_revision_corruption_is_still_rejected(self):
        self.create_work()
        with self.store() as store:
            token, before = store.project_snapshot_if_changed()
            event = deepcopy(before["events"][0])
            event["project_id"] = str(uuid.uuid4())
            other = sqlite3.connect(store_path(self.root))
            try:
                other.execute("DROP TRIGGER events_no_update")
                other.execute("UPDATE events SET event_json=? WHERE event_id=?",
                              (json.dumps(event), event["event_id"]))
                other.commit()
            finally:
                other.close()
            with self.assertRaises(LedgerError):
                store.project_snapshot_if_changed(token)

    def test_uncommitted_reads_are_never_marked_unchanged(self):
        self.create_work()
        with self.store(create=True) as store:
            token, _ = store.project_snapshot_if_changed()
            store.connection.execute("BEGIN")
            try:
                store.connection.execute("INSERT INTO metadata VALUES (?, ?)", ("rollback-probe", "temporary"))
                transaction_token, snapshot = store.project_snapshot_if_changed(token)
                self.assertIsNone(transaction_token)
                self.assertIsNotNone(snapshot)
            finally:
                store.connection.execute("ROLLBACK")
            next_token, after = store.project_snapshot_if_changed(token)
            self.assertIsNot(next_token, token)
            self.assertIsNotNone(after)

    def test_token_is_not_transferable_to_another_connection(self):
        self.create_work()
        with self.store() as first:
            token, _ = first.project_snapshot_if_changed()
        with self.store() as second:
            next_token, snapshot = second.project_snapshot_if_changed(token)
        self.assertIsNot(next_token, token)
        self.assertIsNotNone(snapshot)

    def test_reader_unchanged_poll_does_not_copy_or_rebuild_the_view(self):
        result = self.create_work()
        reader = Reader(self.root, self.cfg)
        self.addCleanup(reader.close)
        first = reader.read()
        with mock.patch("verantyx.storage.sqlite.deepcopy", side_effect=AssertionError("Unchanged copy")), \
             mock.patch("verantyx.cleanroom_view.project_view", side_effect=AssertionError("Unchanged view")):
            second = reader.read()
        self.assertEqual(second["run_id"], result["run_id"])
        self.assertEqual(first["project_revision"], second["project_revision"])
        self.assertFalse(second["writes"])
        self.assertEqual(second["model_calls"], 0)

    def test_selection_can_change_without_copying_the_ledger_again(self):
        first = self.create_work()
        second = self.create_work()
        reader = Reader(self.root, self.cfg)
        self.addCleanup(reader.close)
        reader.read(selected=first["run_id"])
        with mock.patch("verantyx.storage.sqlite.deepcopy", side_effect=AssertionError("Unchanged copy")):
            selected = reader.read(selected=second["run_id"])
        self.assertEqual(selected["run_id"], second["run_id"])
        self.assertEqual(selected["outcome"]["work"]["answer"], "Candidate ready")

    def test_reader_reopens_with_a_fresh_token(self):
        self.create_work()
        reader = Reader(self.root, self.cfg)
        self.addCleanup(reader.close)
        before = reader.read()
        token = reader.snapshot_token
        reader.close()
        after = reader.read()
        self.assertIsNot(reader.snapshot_token, token)
        self.assertEqual(after["project_revision"], before["project_revision"])

    def test_missing_database_stays_read_only(self):
        with self.store() as store:
            token, snapshot = store.project_snapshot_if_changed()
            self.assertIsNone(token)
            self.assertEqual(snapshot["project_revision"], 0)
            self.assertEqual(store.project_snapshot(), snapshot)
        self.assertFalse(store_path(self.root).exists())
