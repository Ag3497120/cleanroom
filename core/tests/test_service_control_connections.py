"""Explicit service registration/stop through artificial manager processes only."""
from pathlib import Path
import hashlib
import json
import os
import plistlib
import subprocess
import sys

from test_constitution import Fixture
from verantyx.connections_v05 import service_definition
from verantyx.errors import LedgerError
from verantyx.jobs import submit, list_jobs
from verantyx.service_runtime import control, worker


class ServiceControlTests(Fixture):
    def setUp(self):
        super().setUp()
        self.marker = self.root / "manager-calls.jsonl"
        self.launcher = self.root / "verantyx"
        source = str(Path(__file__).resolve().parents[1] / "src")
        self.launcher.write_text("#!" + sys.executable + "\nimport sys\nsys.path.insert(0, " + repr(source) + ")\nfrom verantyx.cli import main\nraise SystemExit(main())\n")
        self.launcher.chmod(0o700)
        self.manager = self.root / "launchctl"
        self.manager.write_text("#!" + sys.executable + "\nimport json,sys,plistlib,subprocess\nfrom pathlib import Path\n"
                                + "with Path(" + repr(str(self.marker)) + ").open('a') as f: f.write(json.dumps(sys.argv[1:])+'\\n')\n")
        self.manager.chmod(0o700)
        self.definition = self.root / "fixture.plist"
        result = service_definition(self.root, executable=self.launcher, kind="launchd", output=self.definition)
        self.sha = result["files"][0]["sha256"]
        self.worker_sha = result["worker_sha256"]

    def action(self, operation="register", key="service", **kwargs):
        return control(self.root, self.cfg, operation=operation, definition=self.definition, expected_sha256=self.sha,
                       manager=self.manager, key=key, worker_sha256=self.worker_sha, clock=self.clock, **kwargs)

    def test_register_runs_real_queue_worker_and_stop_is_explicit_once(self):
        revision = self.run_task("task")["recorded_revision"]
        generator = self.root / "generator.py"
        generator.write_text("import json,sys\nv=json.load(sys.stdin)\nprint(json.dumps(v['proposal_template']))\n")
        adapter = self.root / "adapter.json"
        adapter.write_text(json.dumps({"argv": [sys.executable, str(generator)]}))
        submit(self.root, self.cfg, "task", adapter_path=adapter, key="queued", expected_revision=revision)
        first = self.action()
        self.assertEqual(first["status"], "MANAGER_RETURNED_SUCCESS")
        # A service manager returns from registration before a periodic run.
        # Simulate that independent scheduled run after the command gate closes.
        scheduled = subprocess.run(plistlib.loads(self.definition.read_bytes())["ProgramArguments"], capture_output=True)
        self.assertEqual(scheduled.returncode, 0, scheduled.stderr)
        self.assertEqual(list_jobs(self.root, self.cfg)["jobs"][0]["status"], "COMPLETED")
        self.assertTrue(self.action()["duplicate"])
        self.action("stop", key="stop")
        calls = [json.loads(line) for line in self.marker.read_text().splitlines()]
        self.assertEqual([call[0] for call in calls], ["bootstrap", "bootout"])
        self.assertEqual(calls[0][1], "gui/" + str(os.getuid()))

    def test_service_definition_sha_and_worker_only_contract_are_enforced(self):
        changed = plistlib.loads(self.definition.read_bytes())
        changed["ProgramArguments"][4] = "adopt"
        raw = plistlib.dumps(changed)
        self.definition.write_bytes(raw)
        for sha in (self.sha, hashlib.sha256(raw).hexdigest()):
            with self.assertRaises(LedgerError):
                control(self.root, self.cfg, operation="register", definition=self.definition, expected_sha256=sha,
                        manager=self.manager, key="changed", worker_sha256=self.worker_sha)
        self.assertFalse(self.marker.exists())

    def test_unknown_registration_is_not_retried(self):
        def interrupt(stage):
            if stage == "after_step_0":
                raise RuntimeError("interruption after manager")
        with self.assertRaises(RuntimeError):
            self.action(fault=interrupt)
        with self.assertRaises(LedgerError) as error:
            self.action()
        self.assertEqual(error.exception.code, "BRIDGE_OUTCOME_UNKNOWN")
        self.assertEqual(len(self.marker.read_text().splitlines()), 1)

    def test_replaced_worker_is_rejected_before_and_after_start_marker(self):
        original = self.launcher.read_bytes()
        self.launcher.write_bytes(original + b"\n# fixture replacement\n")
        with self.assertRaises(LedgerError):
            self.action(key="before-start")
        self.assertFalse(self.marker.exists())
        self.launcher.write_bytes(original)
        def replace(stage):
            if stage == "after_started":
                self.launcher.write_bytes(original + b"\n# fixture replacement\n")
        with self.assertRaises(LedgerError):
            self.action(key="after-start", fault=replace)
        self.assertFalse(self.marker.exists())

    def test_failed_manager_is_not_retried_or_mislabeled_success(self):
        self.manager.write_text("#!" + sys.executable + "\nfrom pathlib import Path\n"
                                + "with Path(" + repr(str(self.marker)) + ").open('a') as f: f.write('called\\n')\nraise SystemExit(3)\n")
        for _ in range(2):
            with self.assertRaises(LedgerError):
                self.action()
        self.assertEqual(self.marker.read_text(), "called\n")

    def test_systemd_link_enable_and_disable_stop_are_bounded_commands(self):
        manager = self.root / "systemctl"
        manager.write_text("#!" + sys.executable + "\nimport sys,json\nfrom pathlib import Path\n"
                           + "with Path(" + repr(str(self.marker)) + ").open('a') as f: f.write(json.dumps(sys.argv[1:])+'\\n')\n")
        manager.chmod(0o700)
        definition = self.root / "fixture.service"
        result = service_definition(self.root, executable=self.launcher, kind="systemd", output=definition)
        hashes = {Path(item["path"]).suffix: item["sha256"] for item in result["files"]}
        for operation in ("register", "stop"):
            response = control(self.root, self.cfg, operation=operation, definition=definition, expected_sha256=hashes[".service"],
                               timer_sha256=hashes[".timer"], worker_sha256=result["worker_sha256"], manager=manager, key=operation)
            self.assertEqual(response["steps"], 2)
        calls = [json.loads(line) for line in self.marker.read_text().splitlines()]
        self.assertEqual([call[3] for call in calls], ["link", "enable", "disable", "stop"])
        self.assertTrue(all(call[:3] == ["--user", "--no-ask-password", "--no-pager"] for call in calls))

    def test_partial_authority_installation_does_not_fall_back_to_unsigned_worker(self):
        # This checkout may be tested alone or after authority integration.
        import builtins
        from unittest import mock
        original = builtins.__import__
        def unavailable(name, *args, **kwargs):
            if name == "authority":
                raise ImportError("fixture partial installation")
            return original(name, *args, **kwargs)
        (self.root / ".verantyx/authority.db").write_bytes(b"fixture")
        with mock.patch("builtins.__import__", side_effect=unavailable), self.assertRaises(LedgerError):
            worker(self.root, self.cfg)
