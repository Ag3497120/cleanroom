"""Independent service/notification boundary checks; synthetic managers only.

VERANTYX_AUDIT_SOURCE selects src/ under inspection. A replaced notification
executor is tested only inside a temporary source copy. Optional
VERANTYX_AUDIT_AUTHORITY_SOURCE supplies the authority module during the
pre-merge review of the connection-only checkout.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(os.environ.get("VERANTYX_AUDIT_SOURCE", str(Path(__file__).resolve().parents[1] / "src"))).resolve()
sys.path[:0] = [str(SOURCE), str(SOURCE.parent / "tests")]


class ConnectionsRuntimeAuditTests(unittest.TestCase):
    def authority(self):
        import verantyx
        authority_source = os.environ.get("VERANTYX_AUDIT_AUTHORITY_SOURCE")
        if authority_source:
            path = str(Path(authority_source).resolve() / "verantyx")
            if path not in verantyx.__path__:
                verantyx.__path__.append(path)
        from verantyx import authority, commands_authority, commands_v04
        existing = commands_v04.modules
        if commands_authority not in existing():
            patcher = mock.patch.object(commands_v04, "modules", side_effect=lambda: (*existing(), commands_authority))
            patcher.start()
            self.addCleanup(patcher.stop)
        return authority

    def enable(self, fixture):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        authority = self.authority()
        key = Ed25519PrivateKey.generate()  # Artificial fixture only, not user consent.
        public = fixture.root / "artificial-operator.pem"
        public.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        approval = authority.request(fixture.root, fixture.cfg, ["authority-enable", "--public-key", str(public)], clock=fixture.clock)
        authority.execute(fixture.root, fixture.cfg, approval, key.sign(authority.signing_bytes(approval)), clock=fixture.clock)
        return authority, key

    def notification(self):
        from test_notification_connections import NotificationTests
        fixture = NotificationTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        return fixture

    def test_notification_executor_replacement_is_rejected_before_any_code_runs(self):
        with tempfile.TemporaryDirectory(prefix="verantyx-notifier-code-audit-") as temporary:
            copy = Path(temporary)
            shutil.copytree(SOURCE, copy / "src", ignore=shutil.ignore_patterns("__pycache__"))
            shutil.copytree(SOURCE.parent / "tests", copy / "tests", ignore=shutil.ignore_patterns("__pycache__"))
            script = r'''import json
from pathlib import Path
from test_notification_connections import NotificationTests
from verantyx import notification_http,notifications
from verantyx.errors import LedgerError
fixture=NotificationTests(); fixture.setUp()
try:
    fixture.permit()
    marker=fixture.root/'must-not-execute'
    source=Path(notification_http.__file__)
    source.write_text("import json\nfrom pathlib import Path\nPath("+repr(str(marker))+").write_text('changed executor ran')\nprint(json.dumps({'status':'HTTP_ACCEPTED','http_status':202,'response_bytes':0,'delivery_confirmed':False,'response_body_retained':False}))\n")
    error=None
    try: notifications.send(fixture.root,fixture.cfg,'delivery',clock=fixture.clock)
    except LedgerError as exc: error=exc.code
    print(json.dumps({'executor_ran':marker.exists(),'error':error,'network_calls':len(fixture.calls)}))
finally: fixture.tearDown()
'''
            env = {**os.environ, "PYTHONPATH": os.pathsep.join((str(copy / "src"), str(copy / "tests"))), "PYTHONDONTWRITEBYTECODE": "1"}
            completed = subprocess.run([sys.executable, "-c", script], cwd=copy, env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            result = json.loads(completed.stdout)
            self.assertFalse(result["executor_ran"], result)
            self.assertIsNotNone(result["error"], result)
            self.assertEqual(result["network_calls"], 0)

    def test_notification_expiry_is_bound_to_the_original_authorized_ttl(self):
        from verantyx.adapters.invocation_journal import InvocationJournal
        from verantyx.application import iso
        from verantyx.errors import LedgerError
        from verantyx.notifications import send
        fixture = self.notification()
        fixture.permit(ttl=1)
        journal = InvocationJournal(fixture.root, "notification-delivery", "delivery")
        lease = journal.read("authorized")
        # The packet, endpoint, ttl and original intent hash remain unchanged.
        # An unbound expiry field must not silently extend the actual grant.
        lease["expires_at"] = iso(fixture.time + timedelta(hours=1))
        journal.path("authorized").write_text(json.dumps(lease))
        fixture.time += timedelta(seconds=2)
        with self.assertRaises(LedgerError):
            send(fixture.root, fixture.cfg, "delivery", clock=fixture.clock)
        self.assertEqual(len(fixture.calls), 0)

    def test_notification_checks_expiry_again_after_transport_setup(self):
        self._assert_notification_deadline_before_post()

    def test_notification_checks_expiry_again_after_connection_established(self):
        self._assert_notification_deadline_before_post(expire_during_connect=True)

    def _assert_notification_deadline_before_post(self, expire_during_connect=False):
        from verantyx import notification_http
        from verantyx.application import iso
        from verantyx.errors import LedgerError
        moment = [datetime.now(timezone.utc)]
        calls = []
        class ObservedDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return moment[0]
        class Response:
            status = 202
            def getheader(self, name, default=None):
                return "0" if name == "Content-Length" else default
            def read1(self, size):
                return b""
        class Socket:
            def settimeout(self, timeout):
                pass
        class Connection:
            sock = None
            def __init__(self, *args, **kwargs):
                # Setup delay before any request bytes have been transmitted.
                if not expire_during_connect:
                    moment[0] += timedelta(seconds=2)
            def connect(self):
                self.sock = Socket()
                if expire_during_connect:
                    moment[0] += timedelta(seconds=2)
            def request(self, *args):
                calls.append(args)
            def getresponse(self):
                return Response()
            def close(self):
                pass
        value = {"connection": {"endpoint": "http://127.0.0.1:1/fixture", "key_env": None, "allow_loopback_http": True},
                 "packet": {"synthetic": True}, "delivery_id": "fixture", "expires_at": iso(moment[0] + timedelta(seconds=1)), "timeout": 30}
        with mock.patch.object(notification_http, "datetime", ObservedDateTime), mock.patch.object(notification_http.http.client, "HTTPConnection", Connection):
            with self.assertRaises(LedgerError):
                notification_http.deliver(value)
        self.assertEqual(calls, [])

    def test_service_signed_worker_hash_rejects_replacement_before_manager(self):
        from test_service_control_connections import ServiceControlTests
        from verantyx.errors import LedgerError
        fixture = ServiceControlTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        authority, key = self.enable(fixture)
        argv = ["service-register", "--definition", str(fixture.definition), "--sha256", fixture.sha,
                "--manager", str(fixture.manager), "--key", "service-audit", "--worker-sha256", fixture.worker_sha]
        approval = authority.request(fixture.root, fixture.cfg, argv, clock=fixture.clock)
        self.assertEqual(approval["operation"]["arguments"]["worker_sha256"], fixture.worker_sha)
        original = fixture.launcher.read_bytes()
        fixture.launcher.write_bytes(original + b"\n# worker changed after the reviewed signature\n")
        with self.assertRaises(LedgerError):
            authority.execute(fixture.root, fixture.cfg, approval, key.sign(authority.signing_bytes(approval)), clock=fixture.clock)
        self.assertFalse(fixture.marker.exists())
        fixture.launcher.write_bytes(original)
        # The unchanged worker and a fresh, independent signature still work.
        approval = authority.request(fixture.root, fixture.cfg, argv, clock=fixture.clock)
        result = authority.execute(fixture.root, fixture.cfg, approval, key.sign(authority.signing_bytes(approval)), clock=fixture.clock)
        self.assertEqual(result["result"]["status"], "MANAGER_RETURNED_SUCCESS")
        self.assertEqual(len(fixture.marker.read_text().splitlines()), 1)

    def test_service_interruption_and_changed_manager_do_not_register_twice(self):
        from test_service_control_connections import ServiceControlTests
        from verantyx.errors import LedgerError
        fixture = ServiceControlTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        # Use an artificial manager that records a call and never talks to the OS.
        fixture.manager.write_text("#!" + sys.executable + "\nfrom pathlib import Path\nwith Path(" + repr(str(fixture.marker)) + ").open('a') as out: out.write('called\\n')\n")
        def interrupt(stage):
            if stage == "after_step_0":
                raise RuntimeError("synthetic interruption")
        with self.assertRaises(RuntimeError):
            fixture.action(fault=interrupt)
        before = fixture.marker.read_text()
        fixture.manager.write_text(fixture.manager.read_text() + "# executor changed after interrupted action\n")
        with self.assertRaises(LedgerError):
            fixture.action()
        self.assertEqual(fixture.marker.read_text(), before)

    def test_service_does_not_begin_a_second_effect_after_signed_expiry(self):
        from test_service_control_connections import ServiceControlTests
        from verantyx import service_runtime
        from verantyx.connections_v05 import service_definition
        from verantyx.errors import LedgerError
        fixture = ServiceControlTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        manager = fixture.root / "systemctl"
        manager.write_text("#!" + sys.executable + "\nimport sys,json\nfrom pathlib import Path\nwith Path(" + repr(str(fixture.marker)) + ").open('a') as out: out.write(json.dumps(sys.argv[1:])+'\\n')\n")
        manager.chmod(0o700)
        definition = fixture.root / "fixture.service"
        result = service_definition(fixture.root, executable=fixture.launcher, kind="systemd", output=definition)
        hashes = {Path(item["path"]).suffix: item["sha256"] for item in result["files"]}
        authority, key = self.enable(fixture)
        argv = ["service-register", "--definition", str(definition), "--sha256", hashes[".service"],
                "--timer-sha256", hashes[".timer"], "--manager", str(manager), "--key", "expiry-audit", "--worker-sha256", fixture.worker_sha]
        approval = authority.request(fixture.root, fixture.cfg, argv, ttl=1, clock=fixture.clock)
        original_process = service_runtime.BoundedProcess
        process_count = []
        class AdvancingProcess(original_process):
            def document(self, *args, **kwargs):
                result = super().document(*args, **kwargs)
                process_count.append(1)
                if len(process_count) == 1:
                    # The real artificial manager finished its first effect,
                    # and the operator grant expires before the next starts.
                    fixture.time += timedelta(seconds=2)
                return result
        error = None
        with mock.patch.object(service_runtime, "BoundedProcess", AdvancingProcess):
            try:
                authority.execute(fixture.root, fixture.cfg, approval, key.sign(authority.signing_bytes(approval)), clock=fixture.clock)
            except LedgerError as exc:
                error = exc.code
        calls = [json.loads(line) for line in fixture.marker.read_text().splitlines()]
        self.assertEqual([call[3] for call in calls], ["link"], {"calls": calls, "error": error})
        self.assertIsNotNone(error)

    def test_signed_mode_service_worker_rejects_unapproved_and_tampered_jobs(self):
        from test_constitution import Fixture
        from verantyx.adapters.invocation_journal import InvocationJournal
        from verantyx.application import now
        from verantyx import jobs
        from verantyx.service_runtime import worker
        self.authority()
        fixture = Fixture()
        fixture.setUp()
        fixture.time = now()
        self.addCleanup(fixture.tearDown)
        run = fixture.run_task("task")
        marker = fixture.root / "generator-calls"
        generator = fixture.root / "generator.py"
        generator.write_text("import json,sys\nfrom pathlib import Path\nvalue=json.load(sys.stdin)\nwith Path(" + repr(str(marker)) + ").open('a') as output: output.write('called\\n')\nprint(json.dumps(value['proposal_template']))\n")
        adapter = fixture.root / "adapter.json"
        adapter.write_text(json.dumps({"argv": [sys.executable, str(generator)]}))
        jobs.submit(fixture.root, fixture.cfg, "task", adapter_path=adapter, key="queued", expected_revision=run["recorded_revision"], clock=fixture.clock)
        authority, key = self.enable(fixture)
        refused = worker(fixture.root, fixture.cfg, clock=fixture.clock)
        self.assertEqual(refused["processed"], [])
        self.assertEqual(refused["refused"][0]["code"], "AUTHORITY_JOB_MISMATCH")
        self.assertFalse(marker.exists())
        argv = ["job-submit", "task", "--adapter", str(adapter), "--key", "queued", "--expected-revision", str(run["recorded_revision"])]
        approval = authority.request(fixture.root, fixture.cfg, argv, clock=fixture.clock)
        authority.execute(fixture.root, fixture.cfg, approval, key.sign(authority.signing_bytes(approval)), clock=fixture.clock)
        journal = InvocationJournal(fixture.root, "job", "queued")
        path = journal.path("operator-approval-" + approval["nonce"])
        original = path.read_bytes()
        tampered = json.loads(original)
        tampered["job_hash"] = "f" * 64
        path.write_text(json.dumps(tampered))
        rejected = worker(fixture.root, fixture.cfg, clock=fixture.clock)
        self.assertEqual(rejected["processed"], [])
        self.assertEqual(rejected["refused"][0]["code"], "AUTHORITY_JOB_MISMATCH")
        self.assertFalse(marker.exists())
        path.write_bytes(original)
        completed = worker(fixture.root, fixture.cfg, clock=fixture.clock)
        self.assertTrue(completed["ok"], completed)
        self.assertEqual(completed["processed"][0]["status"], "COMPLETED")
        self.assertEqual(marker.read_text(), "called\n")
        self.assertEqual(worker(fixture.root, fixture.cfg, clock=fixture.clock)["processed"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
