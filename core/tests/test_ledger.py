"""Persistence, hostile-input, and process restart tests, with independent checks."""
from datetime import timedelta
from pathlib import Path
from unittest import mock
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from test_constitution import Fixture, proposal, SCOPE
from verantyx import config
from verantyx.application import record_run, get_projection, load_proposal
from verantyx.adapters.observations import observe, read_document
from verantyx.domain.codec import canonical, decode, digest
from verantyx.domain.events import make_event, citation
from verantyx.errors import LedgerError
from verantyx.storage.sqlite import EventStore, parse_archive


class LedgerTests(Fixture):
    def test_file_evidence_does_not_verify_prose_and_stale_resume_changes_verdict(self):
        path = self.root / "data.txt"
        path.write_text("initial")
        first = record_run(self.root, self.cfg, request="観測", run_id="observe", observe_paths=["data.txt"], clock=self.clock)
        ref = first["state"]["latest_observations"]["data.txt"]
        document = proposal("observe", first["state"]["revision"])
        document["decision_points"] = []
        document["claims"] = [{"id": "claim", "statement": "このファイルは完全に正しい", "source_refs": [ref]}]
        document["actions"] = [{"id": "read", "tool_id": "file.observe", "arguments": {"path": "data.txt"},
                                "reason": "観測", "source_refs": [ref]}]
        proposal_path = self.root / "proposal.json"
        proposal_path.write_text(json.dumps(document))
        view = record_run(self.root, self.cfg, run_id="observe", proposal_path=proposal_path, resume=True, clock=self.clock)
        self.assertEqual(view["state"]["assessment"]["claims"][0]["verification"], "UNVERIFIED")
        self.assertEqual(view["state"]["assessment"]["actions"][0]["gate"], "OBSERVATION_AVAILABLE")
        path.write_text("changed")
        changed = record_run(self.root, self.cfg, run_id="observe", resume=True, clock=self.clock)
        self.assertEqual(changed["state"]["assessment"]["actions"][0]["reason"], "SOURCE_CHANGED")
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            self.assertEqual(store.events("observe")[1]["payload"]["sha256"], hashlib.sha256(b"initial").hexdigest())

    def test_proposal_cannot_read_file_or_grant_scope(self):
        document = proposal("missing")
        document["actions"] = [{"id": "read", "tool_id": "file.observe", "arguments": {"path": "private.txt"},
                                "reason": "必要", "source_refs": []}]
        (self.root / "private.txt").write_text("must never be observed")
        with mock.patch("verantyx.application.observe", side_effect=AssertionError("ungranted I/O")):
            result = self.run_task("missing", document)
        self.assertEqual(result["state"]["read_scope"], [])
        self.assertEqual(result["state"]["assessment"]["actions"][0]["gate"], "NEED_DECISION")
        self.assertEqual(result["state"]["observations"], {})

    def test_strict_json_duplicate_keys_nan_deep_and_unknown_fields(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}', b'[' * 42 + b'0' + b']' * 42):
            with self.assertRaises(LedgerError):
                decode(raw)
        for value in (True, -1, "0"):
            document = proposal("invalid")
            document["context_revision"] = value
            with self.assertRaises(LedgerError):
                self.run_task("invalid", document)

    def test_symlink_fifo_and_scope_escape_do_not_read_other_files(self):
        outside = self.root.parent / (self.root.name + "-private")
        outside.write_text("secret")
        try:
            (self.root / "link").symlink_to(outside)
            (self.root / "dirlink").symlink_to(self.root.parent, target_is_directory=True)
            os.mkfifo(self.root / "pipe")
            for name in ("link", "dirlink/" + outside.name, "pipe"):
                result = observe(self.root, name, "2000-01-01T00:00:00.000000Z", "2000-01-02T00:00:00.000000Z")
                self.assertEqual(result["status"], "UNREADABLE")
                self.assertIsNone(result["sha256"])
            with self.assertRaises(LedgerError):
                read_document(self.root / "pipe")
            for name in ("../outside", ".git/config", ".verantyx/state.db", "/etc/passwd"):
                with self.assertRaises(LedgerError):
                    observe(self.root, name, "", "")
        finally:
            outside.unlink()

    def test_idempotency_and_revision_conflicts_survive_reopen(self):
        first = self.run_task("retry", key="same")
        with mock.patch("verantyx.application.observe", side_effect=AssertionError("repeat")):
            second = self.run_task("retry", key="same")
        self.assertTrue(second["duplicate"])
        self.assertEqual(first["projection_hash"], second["projection_hash"])
        with self.assertRaises(LedgerError) as error:
            self.run_task("different", key="same")
        self.assertEqual(error.exception.code, "IDEMPOTENCY_CONFLICT")
        with self.assertRaises(LedgerError) as error:
            record_run(self.root, self.cfg, run_id="retry", resume=True, expected_revision=0, clock=self.clock)
        self.assertEqual(error.exception.code, "REVISION_CONFLICT")
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            self.assertEqual(store.project_revision(), first["recorded_revision"])

    def test_transactions_crash_before_and_after_commit_in_separate_process(self):
        script = '''from pathlib import Path
import os,sys
from verantyx import config
from verantyx.application import record_run
root=Path(sys.argv[1]); value,_=config.load(root)
def crash(stage):
 if stage==sys.argv[2]: os._exit(73)
record_run(root,value,request='crash fixture',run_id='crash',key='crash-key',fault=crash)
'''
        for stage in ("after_events", "before_commit", "after_commit"):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                cfg = config.defaults(root, "en")
                config.save(root, cfg, None)
                result = subprocess.run([sys.executable, "-c", script, str(root), stage], capture_output=True)
                self.assertEqual(result.returncode, 73, result.stderr)
                with EventStore(root, cfg["project"]["id"]) as store:
                    count = len(store.events())
                    commands = store.connection.execute("SELECT COUNT(*) FROM commands").fetchone()[0]
                    outbox = store.connection.execute("SELECT COUNT(*) FROM outbox").fetchone()[0]
                self.assertEqual(count > 0, stage == "after_commit")
                self.assertEqual((commands, outbox), (1, 1) if stage == "after_commit" else (0, 0))
                retried = record_run(root, cfg, request="crash fixture", run_id="crash", key="crash-key")
                self.assertEqual(retried["duplicate"], stage == "after_commit")

    def test_append_only_triggers_and_hash_tamper_detection(self):
        self.run_task("immutable")
        database = self.root / ".verantyx/state.db"
        from contextlib import closing
        with closing(sqlite3.connect(database)) as db, db:
            for table in ("events", "commands", "outbox", "metadata"):
                with self.assertRaises(sqlite3.IntegrityError):
                    db.execute("DELETE FROM " + table)
            db.execute("DROP TRIGGER events_no_update")
            row = db.execute("SELECT seq,event_json FROM events LIMIT 1").fetchone()
            event = json.loads(row[1]); event["payload"]["request"] = "tampered"
            db.execute("UPDATE events SET event_json=? WHERE seq=?", (json.dumps(event), row[0]))
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            with self.assertRaises(LedgerError):
                store.events("immutable")

    def test_archive_roundtrip_preserves_citations_but_never_restores_authority(self):
        self.promote()
        (self.root / "public.txt").write_text("reference")
        record_run(self.root, self.cfg, request="read", run_id="read", observe_paths=["public.txt"], clock=self.clock)
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            raw = store.export().encode()
            expected = [citation(event) for event in store.events()]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(); cfg = config.defaults(root, "en"); config.save(root, cfg, None)
            with EventStore(root, cfg["project"]["id"], create=True) as store:
                imported = store.import_archive(raw, "2026-09-06T00:00:00.000000Z")
                archive = store.archive(imported["archive_id"])
                self.assertEqual(store.events(), [])
                self.assertEqual(store.export(imported["archive_id"]).encode(), raw)
                self.assertEqual([citation(e) for e in archive["events"]], expected)
                view = get_projection(store, "read", imported["archive_id"])
                self.assertEqual(view["state"]["rights"]["effective_read_paths"], [])
                self.assertFalse(view["state"]["can_execute_effects"])
                self.assertEqual(view["state"]["trust"], "ARCHIVE_ONLY")
                with self.assertRaises(LedgerError):
                    store.import_archive(raw.replace(b'reference', b'corrupt', 1)[:-4], "2026-09-06T00:00:00.000000Z")

    def test_cross_task_revision_conflict_rejects_stale_policy_capture(self):
        first = self.run_task("base")
        with EventStore(self.root, self.cfg["project"]["id"], create=True) as store:
            before = store.project_revision()
            old = store.events("base")
            self.run_task("parallel")
            import uuid
            event = make_event(store.project_id, "base", old[-1]["revision"] + 1, str(uuid.uuid4()),
                               "2026-09-06T00:00:00.000000Z", "EvaluationRecorded",
                               {"as_of": "2026-09-06T00:00:00.000000Z", "evaluator": "m1.v1"}, str(uuid.uuid4()), old[-1])
            with self.assertRaises(LedgerError) as error:
                store.append("stale-global", digest({"stale": True}), "base", old[-1]["revision"], [event], project_revision=before)
            self.assertEqual(error.exception.code, "REVISION_CONFLICT")

    def test_cli_new_workflow_localized_and_replayed_in_new_process(self):
        self.promote()
        for lang in ("ja", "en", "zh-Hans", "ko", "es"):
            for command in (("replay", "first"), ("learn", "first"), ("rules",), ("events", "first"), ("gaps", "first")):
                result = subprocess.run([sys.executable, "-m", "verantyx", "--project", str(self.root), "--lang", lang, *command],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn("Traceback", result.stdout)
            result = subprocess.run([sys.executable, "-m", "verantyx", "--project", str(self.root), "--lang", lang,
                                     "--json", "rule-activate", "missing"], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(json.loads(result.stdout)["error"]["code"], "RULE_NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
