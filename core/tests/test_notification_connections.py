"""Explicit learning notification grants, loopback delivery, and uncertain outcomes."""
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import shutil
from pathlib import Path
import threading
from unittest import mock

from test_constitution import Fixture
from verantyx.application import iso, now
from verantyx.errors import LedgerError
from verantyx.learning import control_learning
from verantyx.learning_exercises import control_exercises
from verantyx.learning_materials import builtin_exercise
from verantyx.notifications import prepare, authorize, send
from verantyx.storage.sqlite import EventStore
from verantyx.adapters.invocation_journal import InvocationJournal
from verantyx.domain.codec import canonical, digest


class NotificationTests(Fixture):
    def setUp(self):
        super().setUp()
        self.time = now()
        run = self.run_task("task")
        control_learning(self.root, self.cfg, "task", "raise", candidate_id="practice", concept_id="parallel_writers",
                         concept="Worktree separation", why_now=["fixture"], minimum_model="separate files",
                         counterexample="shared index", check="explain", source_refs=[run["state"]["request_ref"]], clock=self.clock)
        self.exercise = builtin_exercise("parallel_writers", "ja")
        self.exercise_id = self.exercise["id"]
        control_exercises(self.root, self.cfg, "task", "register", candidate_id="practice", document=self.exercise, clock=self.clock)
        control_exercises(self.root, self.cfg, "task", "schedule", candidate_id="practice", exercise_id=self.exercise_id,
                          due_at=iso(self.time + timedelta(seconds=1)), reason="fixture opted-in review", clock=self.clock)
        self.time += timedelta(seconds=2)
        self.packet = self.root / "notification.json"
        self.prepared = prepare(self.root, self.cfg, "task", candidate_id="practice", exercise_id=self.exercise_id, output=self.packet, clock=self.clock)
        self.calls, self.mode = [], "ok"
        fixture = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                value = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                fixture.calls.append({"value": value, "headers": dict(self.headers)})
                if fixture.mode == "slow":
                    threading.Event().wait(2)
                self.send_response(307 if fixture.mode == "redirect" else 503 if fixture.mode == "fail" else 202)
                self.send_header("Location", "http://127.0.0.1:1/do-not-follow")
                body = b"fixture-webhook-secret"
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass
        self.http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.endpoint = "http://127.0.0.1:" + str(self.http.server_port) + "/selected-due-item"

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()
        super().tearDown()

    def permit(self, key="delivery", **kwargs):
        return authorize(self.root, self.cfg, packet_path=self.packet, expected_sha256=self.prepared["file_sha256"],
                         endpoint=self.endpoint, key=key, allow_loopback_http=True, clock=self.clock, **kwargs)

    def test_review_authorize_send_is_once_and_does_not_claim_delivery_or_mastery(self):
        self.assertEqual(self.calls, [])
        self.permit(key_env="VERANTYX_FIXTURE_NOTIFICATION_KEY")
        self.assertEqual(self.calls, [])
        with mock.patch.dict(os.environ, {"VERANTYX_FIXTURE_NOTIFICATION_KEY": "fixture-webhook-secret"}):
            response = send(self.root, self.cfg, "delivery", clock=self.clock)
            self.assertTrue(send(self.root, self.cfg, "delivery", clock=self.clock)["duplicate"])
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(response["receipt"]["http_status"], 202)
        self.assertFalse(response["receipt"]["delivery_confirmed"])
        self.assertEqual(response["mastery_assessment"], "NOT_ASSESSED")
        self.assertFalse(self.calls[0]["value"]["packet"]["contains_raw_answers"])
        self.assertNotIn('"answers":', json.dumps(self.calls[0]["value"]))
        self.assertNotIn('"statement":', json.dumps(self.calls[0]["value"]))
        self.assertEqual(self.calls[0]["headers"]["Authorization"], "Bearer fixture-webhook-secret")
        for path in (self.root / ".verantyx/bridges").glob("*.json"):
            self.assertNotIn("fixture-webhook-secret", path.read_text())
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            self.assertNotIn("HumanDecisionRecorded", [e["type"] for e in store.events()])

    def test_missing_authorization_changed_packet_and_expiry_do_not_post(self):
        with self.assertRaises(LedgerError):
            send(self.root, self.cfg, "missing", clock=self.clock)
        self.permit(ttl=1)
        self.time += timedelta(seconds=2)
        with self.assertRaises(LedgerError) as error:
            send(self.root, self.cfg, "delivery", clock=self.clock)
        self.assertEqual(error.exception.code, "LEASE_EXPIRED")
        self.packet.write_text(self.packet.read_text() + " ")
        with self.assertRaises(LedgerError):
            self.permit("changed")
        self.assertEqual(self.calls, [])

    def test_cancelled_review_and_learning_off_invalidate_undelivered_grant(self):
        self.permit()
        control_exercises(self.root, self.cfg, "task", "cancel", candidate_id="practice", exercise_id=self.exercise_id,
                          reason="fixture cancelled", clock=self.clock)
        with self.assertRaises(LedgerError):
            send(self.root, self.cfg, "delivery", clock=self.clock)
        self.assertEqual(self.calls, [])

    def test_unknown_or_failed_delivery_never_retries_the_same_grant(self):
        for mode in ("redirect", "fail", "slow"):
            self.mode = mode
            self.permit(mode, timeout=1)
            before = len(self.calls)
            for _ in range(2):
                with self.assertRaises(LedgerError):
                    send(self.root, self.cfg, mode, clock=self.clock)
            self.assertEqual(len(self.calls), before + 1)

    def test_started_or_http_completed_interruption_does_not_repeat_effect(self):
        for stage in ("after_started", "after_http"):
            self.permit(stage)
            def interrupt(current):
                if current == stage:
                    raise RuntimeError("fixture interruption")
            before = len(self.calls)
            with self.assertRaises(RuntimeError):
                send(self.root, self.cfg, stage, clock=self.clock, fault=interrupt)
            with self.assertRaises(LedgerError) as error:
                send(self.root, self.cfg, stage, clock=self.clock)
            self.assertEqual(error.exception.code, "BRIDGE_OUTCOME_UNKNOWN")
            self.assertEqual(len(self.calls), before + (stage == "after_http"))

    def test_expiry_after_started_refuses_before_network(self):
        self.permit(ttl=1)
        def delay(stage):
            self.time += timedelta(seconds=2)
        with self.assertRaises(LedgerError) as error:
            send(self.root, self.cfg, "delivery", clock=self.clock, fault=delay)
        self.assertEqual(error.exception.code, "LEASE_EXPIRED")
        self.assertEqual(self.calls, [])

    def test_replaced_sender_implementation_is_rejected_before_any_process(self):
        from verantyx import notifications
        package = self.root / "inspected-package"
        shutil.copytree(Path(notifications.__file__).parent, package, ignore=shutil.ignore_patterns("__pycache__"))
        with mock.patch.object(notifications, "__file__", str(package / "notifications.py")):
            self.permit()
            (package / "notification_http.py").write_text("raise SystemExit('fixture replaced code')\n")
            with mock.patch.object(notifications, "BoundedProcess") as process, self.assertRaises(LedgerError) as error:
                send(self.root, self.cfg, "delivery", clock=self.clock)
            self.assertEqual(error.exception.code, "PRECONDITION_CHANGED")
            process.assert_not_called()
        self.assertEqual(self.calls, [])

    def test_changed_expiry_is_rejected_even_with_recomputed_outer_hash(self):
        for reseal in (False, True):
            key = "reseal" if reseal else "direct"
            self.permit(key, ttl=1)
            journal = InvocationJournal(self.root, "notification-delivery", key)
            lease = journal.read("authorized")
            lease["expires_at"] = iso(self.time + timedelta(hours=1))
            if reseal:
                lease["lease_sha256"] = digest({k: v for k, v in lease.items() if k != "lease_sha256"})
            journal.path("authorized").write_text(canonical(lease))
            with self.assertRaises(LedgerError) as error:
                send(self.root, self.cfg, key, clock=self.clock)
            self.assertEqual(error.exception.code, "PRECONDITION_CHANGED")
        self.assertEqual(self.calls, [])

    def test_expiry_during_transport_connection_prevents_request_bytes(self):
        from verantyx import notification_http
        moment = [now()]
        calls = []
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return moment[0]
        class Connection:
            sock = mock.Mock()
            def __init__(self, *args, **kwargs):
                pass
            def connect(self):
                moment[0] += timedelta(seconds=2)
            def request(self, *args):
                calls.append(args)
            def close(self):
                pass
        value = {"connection": {"endpoint": self.endpoint, "key_env": None, "allow_loopback_http": True}, "packet": {},
                 "delivery_id": "after-connect", "expires_at": iso(moment[0] + timedelta(seconds=1)), "timeout": 30}
        with mock.patch.object(notification_http, "datetime", Clock), mock.patch.object(notification_http.http.client, "HTTPConnection", Connection):
            with self.assertRaises(LedgerError):
                notification_http.deliver(value)
        self.assertEqual(calls, [])
