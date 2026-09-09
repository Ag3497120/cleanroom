"""Artificial signed CLI workflows coupled to bounded service and notification effects."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import unittest
from unittest import mock

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from test_constitution import Fixture
from verantyx import authority, jobs
from verantyx.application import now
from verantyx.connections_v05 import service_definition
from verantyx.errors import LedgerError
from verantyx.storage.sqlite import EventStore


class SignedServiceTests(Fixture):
    def setUp(self):
        super().setUp()
        self.time = now()
        self.key = Ed25519PrivateKey.generate()
        self.public = self.root / "fixture.pem"
        self.public.write_bytes(self.key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        self.command = [sys.executable, "-m", "verantyx", "--project", str(self.root), "--json"]
        self.generator = self.root / "generator.py"
        self.marker = self.root / "generator.calls"
        self.generator.write_text("import json,sys\nfrom pathlib import Path\nv=json.load(sys.stdin)\n"
                                  + "with Path(" + repr(str(self.marker)) + ").open('a') as f: f.write(v['proposal_template']['task_id']+'\\n')\n"
                                  + "print(json.dumps(v['proposal_template']))\n")
        self.adapter = self.root / "adapter.json"
        self.adapter.write_text(json.dumps({"argv": [sys.executable, str(self.generator)]}))

    def signed(self, argv):
        approval = authority.request(self.root, self.cfg, argv)
        signature = self.key.sign(authority.signing_bytes(approval))
        return authority.execute(self.root, self.cfg, approval, signature)

    def enable(self):
        self.signed(["authority-enable", "--public-key", str(self.public)])

    def queued(self, run_id, key, *, signed=True):
        revision = self.run_task(run_id)["recorded_revision"]
        argv = ["job-submit", run_id, "--adapter", str(self.adapter), "--key", key, "--expected-revision", str(revision)]
        if signed:
            return self.signed(argv)
        return jobs.submit(self.root, self.cfg, run_id, adapter_path=self.adapter, key=key, expected_revision=revision)

    def test_signed_submit_and_real_unsigned_service_cli_only_deliver_attested_job(self):
        self.queued("legacy", "unsigned-job", signed=False)
        self.enable()
        self.queued("signed", "signed-job")
        blocked = subprocess.run([*self.command, "worker", "--max-jobs", "2"], capture_output=True)
        self.assertNotEqual(blocked.returncode, 0)
        self.assertEqual(json.loads(blocked.stdout)["error"]["code"], "AUTHORITY_REQUIRED")
        scheduled = subprocess.run([*self.command, "service-worker", "--max-jobs", "2"], capture_output=True)
        result = json.loads(scheduled.stdout)
        self.assertEqual([item["job_id"] for item in result["processed"]], ["signed-job"])
        self.assertEqual(result["refused"], [{"job_id": "unsigned-job", "code": "AUTHORITY_JOB_MISMATCH"}])
        self.assertEqual(self.marker.read_text(), "signed\n")
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            kinds = [event["type"] for event in store.events()]
        self.assertNotIn("ToolExecutionCompleted", kinds)
        self.assertNotIn("HumanDecisionRecorded", kinds)
        again = subprocess.run([*self.command, "service-worker", "--max-jobs", "2"], capture_output=True)
        self.assertEqual(json.loads(again.stdout)["processed"], [])
        self.assertEqual(self.marker.read_text(), "signed\n")

    def test_signed_service_registration_and_stop_do_not_grant_unsigned_jobs(self):
        self.enable()
        self.queued("task", "allowed")
        launcher = self.root / "verantyx"
        source = str(Path(__file__).resolve().parents[1] / "src")
        launcher.write_text("#!" + sys.executable + "\nimport sys\nsys.path.insert(0," + repr(source) + ")\nfrom verantyx.cli import main\nraise SystemExit(main())\n")
        launcher.chmod(0o700)
        manager = self.root / "launchctl"
        calls = self.root / "manager.calls"
        manager.write_text("#!" + sys.executable + "\nimport sys\nfrom pathlib import Path\n"
                           + "with Path(" + repr(str(calls)) + ").open('a') as f: f.write(sys.argv[1]+'\\n')\n")
        manager.chmod(0o700)
        definition = self.root / "fixture.plist"
        generated = self.signed(["service-definition", "--kind", "launchd", "--executable", str(launcher), "--output", str(definition)])["result"]
        args = ["--definition", str(definition), "--sha256", generated["files"][0]["sha256"],
                "--worker-sha256", generated["worker_sha256"], "--manager", str(manager)]
        refused = subprocess.run([*self.command, "service-register", *args, "--key", "unapproved"], capture_output=True)
        self.assertNotEqual(refused.returncode, 0)
        self.assertFalse(calls.exists())
        receipt = self.signed(["service-register", *args, "--key", "register"])["result"]
        self.assertEqual(receipt["status"], "MANAGER_RETURNED_SUCCESS")
        scheduled = subprocess.run(generated["argv"], capture_output=True)
        self.assertEqual(scheduled.returncode, 0, scheduled.stderr)
        self.assertEqual(json.loads(scheduled.stdout)["processed"][0]["status"], "COMPLETED")
        self.signed(["service-stop", *args, "--key", "stop"])
        self.assertEqual(calls.read_text(), "bootstrap\nbootout\n")

    def test_service_worker_digest_is_part_of_signed_operation_and_checked_before_manager(self):
        self.enable()
        launcher = self.root / "verantyx"
        launcher.write_text("#!" + sys.executable + "\nraise SystemExit(0)\n")
        launcher.chmod(0o700)
        manager = self.root / "launchctl"
        sentinel = self.root / "should-not-exist"
        manager.write_text("#!" + sys.executable + "\nfrom pathlib import Path\nPath(" + repr(str(sentinel)) + ").touch()\n")
        manager.chmod(0o700)
        definition = self.root / "fixture.plist"
        generated = service_definition(self.root, executable=launcher, kind="launchd", output=definition)
        argv = ["service-register", "--definition", str(definition), "--sha256", generated["files"][0]["sha256"],
                "--worker-sha256", generated["worker_sha256"], "--manager", str(manager), "--key", "register"]
        approval = authority.request(self.root, self.cfg, argv)
        self.assertEqual(approval["operation"]["arguments"]["worker_sha256"], hashlib.sha256(launcher.read_bytes()).hexdigest())
        signature = self.key.sign(authority.signing_bytes(approval))
        launcher.write_text("#!" + sys.executable + "\nraise SystemExit(3)\n")
        with self.assertRaises(LedgerError) as error:
            authority.execute(self.root, self.cfg, approval, signature)
        self.assertEqual(error.exception.code, "BRIDGE_CONFIG")
        self.assertFalse(sentinel.exists())


    def test_expired_signature_between_systemd_steps_prevents_enable(self):
        from datetime import timedelta
        from verantyx.adapters.command_process import BoundedProcess
        self.enable()
        launcher = self.root / "verantyx"
        launcher.write_text("#!" + sys.executable + "\nraise SystemExit(0)\n")
        launcher.chmod(0o700)
        manager = self.root / "systemctl"
        calls = self.root / "manager.calls"
        manager.write_text("#!" + sys.executable + "\nimport sys\nfrom pathlib import Path\n"
                           + "with Path(" + repr(str(calls)) + ").open('a') as f: f.write(sys.argv[4]+'\\n')\n")
        manager.chmod(0o700)
        definition = self.root / "fixture.service"
        generated = service_definition(self.root, executable=launcher, kind="systemd", output=definition)
        hashes = {Path(item["path"]).suffix: item["sha256"] for item in generated["files"]}
        argv = ["service-register", "--definition", str(definition), "--sha256", hashes[".service"],
                "--timer-sha256", hashes[".timer"], "--worker-sha256", generated["worker_sha256"],
                "--manager", str(manager), "--key", "register"]
        self.time = now()
        approval = authority.request(self.root, self.cfg, argv, ttl=1, clock=self.clock)
        original = BoundedProcess.document
        def finish_then_expire(process, *args, **kwargs):
            response = original(process, *args, **kwargs)
            self.time += timedelta(seconds=2)
            return response
        with mock.patch.object(BoundedProcess, "document", finish_then_expire):
            with self.assertRaises(LedgerError):
                authority.execute(self.root, self.cfg, approval, self.key.sign(authority.signing_bytes(approval)), clock=self.clock)
        self.assertEqual(calls.read_text(), "link\n")


class SignedNotificationTests(unittest.TestCase):
    def test_reviewed_notification_requires_signed_grant_and_send_and_is_once(self):
        from datetime import timedelta
        from unittest import mock
        from test_notification_connections import NotificationTests
        fixture = NotificationTests(methodName="runTest")
        with mock.patch("test_notification_connections.now", side_effect=lambda: now() - timedelta(seconds=10)):
            fixture.setUp()
        try:
            key = Ed25519PrivateKey.generate()
            public = fixture.root / "fixture.pem"
            public.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
            command = [sys.executable, "-m", "verantyx", "--project", str(fixture.root), "--json"]
            def signed(argv):
                approval = authority.request(fixture.root, fixture.cfg, argv)
                approval_file = fixture.root / (approval["nonce"] + ".json")
                signature_file = fixture.root / (approval["nonce"] + ".sig")
                approval_file.write_bytes(authority.signing_bytes(approval))
                signature_file.write_bytes(key.sign(authority.signing_bytes(approval)))
                result = subprocess.run([*command, "authority-execute", "--approval", str(approval_file), "--signature", str(signature_file)], capture_output=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                return json.loads(result.stdout)
            signed(["authority-enable", "--public-key", str(public)])
            permit = ["notification-authorize", "--packet", str(fixture.packet), "--sha256", fixture.prepared["file_sha256"],
                      "--endpoint", fixture.endpoint, "--allow-loopback-http", "--key", "signed-delivery"]
            blocked = subprocess.run([*command, *permit], capture_output=True)
            self.assertNotEqual(blocked.returncode, 0)
            self.assertEqual(json.loads(blocked.stdout)["error"]["code"], "AUTHORITY_REQUIRED")
            signed(permit)
            self.assertEqual(fixture.calls, [])
            blocked = subprocess.run([*command, "notification-send", "signed-delivery"], capture_output=True)
            self.assertNotEqual(blocked.returncode, 0)
            self.assertEqual(fixture.calls, [])
            first = signed(["notification-send", "signed-delivery"])["result"]
            self.assertEqual(first["receipt"]["http_status"], 202)
            second = signed(["notification-send", "signed-delivery"])["result"]
            self.assertTrue(second["duplicate"])
            self.assertEqual(len(fixture.calls), 1)
            self.assertFalse(first["receipt"]["delivery_confirmed"])
            self.assertEqual(first["mastery_assessment"], "NOT_ASSESSED")
        finally:
            fixture.tearDown()
