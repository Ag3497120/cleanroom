"""Service definitions remain inactive; transport preserves archive trust and bytes."""
from pathlib import Path
import os
import plistlib
import subprocess
import sys
import tempfile
from unittest import mock

from test_constitution import Fixture
from verantyx import config
from verantyx.application import iso
from verantyx.connections_v05 import service_definition, archive_send, archive_fetch
from verantyx.errors import LedgerError
from verantyx.storage.sqlite import EventStore


class ServiceArchiveConnectionTests(Fixture):
    def test_launchd_definition_roundtrips_without_starting_or_embedding_credentials(self):
        target = self.root / "fixture.plist"
        with mock.patch("subprocess.Popen", side_effect=AssertionError("service started")):
            result = service_definition(self.root, executable=sys.executable, kind="launchd", output=target)
        specification = plistlib.loads(target.read_bytes())
        self.assertEqual(specification["ProgramArguments"], result["argv"])
        self.assertFalse(specification["RunAtLoad"])
        self.assertEqual(specification["StartInterval"], 60)
        self.assertNotIn("EnvironmentVariables", specification)
        self.assertFalse(result["installed"])
        self.assertFalse(result["started"])
        lint = subprocess.run(["/usr/bin/plutil", "-lint", str(target)], capture_output=True, text=True)
        self.assertEqual(lint.returncode, 0, lint.stdout + lint.stderr)

    def test_systemd_service_and_timer_keep_bounded_worker_and_no_shell(self):
        target = self.root / "fixture.service"
        result = service_definition(self.root, executable=sys.executable, kind="systemd", output=target, interval=45, max_jobs=2)
        self.assertEqual(len(result["files"]), 2)
        service = target.read_text()
        self.assertIn("Type=oneshot", service)
        self.assertNotIn("Environment=", service)
        self.assertNotIn("/bin/sh", service)
        self.assertIn('"service-worker" "--max-jobs" "2"', service)
        self.assertIn("OnUnitInactiveSec=45", target.with_suffix(".timer").read_text())
        self.assertIn("Unit=fixture.service", target.with_suffix(".timer").read_text())

    def test_service_paths_cannot_inject_unit_directives_or_overwrite_output(self):
        for interval in (True, 0, 90000):
            with self.assertRaises(LedgerError):
                service_definition(self.root, executable=sys.executable, kind="launchd", output=self.root / "bad.plist", interval=interval)
        target = self.root / "existing.plist"
        target.write_text("keep")
        with self.assertRaises(LedgerError):
            service_definition(self.root, executable=sys.executable, kind="launchd", output=target)
        self.assertEqual(target.read_text(), "keep")

    def transport(self):
        self.run_task("task")
        with EventStore(self.root, self.cfg["project"]["id"], create=True) as store:
            raw = store.export().encode()
            archive_id = store.import_archive(raw, iso(self.clock()))["archive_id"]
        directory = self.root / "selected-transport"
        directory.mkdir()
        return directory, archive_id, raw

    def test_selected_archive_sync_is_byte_preserving_deduplicated_and_inert(self):
        directory, archive_id, raw = self.transport()
        sent = archive_send(self.root, self.cfg, archive_id=archive_id, directory=directory)
        self.assertFalse(sent["duplicate"])
        self.assertTrue(archive_send(self.root, self.cfg, archive_id=archive_id, directory=directory)["duplicate"])
        self.assertEqual(Path(sent["output"]).read_bytes(), raw)
        peer = self.root / "peer"
        peer.mkdir()
        cfg = config.defaults(peer, "ja")
        config.save(peer, cfg, None)
        first = archive_fetch(peer, cfg, expected_sha256=archive_id, directory=directory, clock=self.clock)
        self.assertEqual(first["trust"], "ARCHIVE_ONLY")
        self.assertFalse(first["local_runs_changed"])
        self.assertTrue(archive_fetch(peer, cfg, expected_sha256=archive_id, directory=directory, clock=self.clock)["duplicate"])
        with EventStore(peer, cfg["project"]["id"]) as store:
            self.assertEqual(store.events(), [])
            self.assertEqual(store.export(archive_id).encode(), raw)

    def test_corruption_and_symlink_transport_are_rejected(self):
        directory, archive_id, raw = self.transport()
        archive_send(self.root, self.cfg, archive_id=archive_id, directory=directory)
        target = directory / (archive_id + ".jsonl")
        target.write_bytes(raw + b"corruption")
        for operation in (lambda: archive_send(self.root, self.cfg, archive_id=archive_id, directory=directory),
                          lambda: archive_fetch(self.root, self.cfg, expected_sha256=archive_id, directory=directory, clock=self.clock)):
            with self.assertRaises(LedgerError):
                operation()
        link = self.root / "link"
        link.symlink_to(directory)
        with self.assertRaises(LedgerError):
            archive_fetch(self.root, self.cfg, expected_sha256=archive_id, directory=link, clock=self.clock)

    def test_sync_requires_explicit_archive_sha_not_implicit_whole_project(self):
        directory, archive_id, raw = self.transport()
        for invalid in (None, "../escape", "all", "*"):
            with self.subTest(invalid=invalid), self.assertRaises(LedgerError):
                archive_send(self.root, self.cfg, archive_id=invalid, directory=directory)
