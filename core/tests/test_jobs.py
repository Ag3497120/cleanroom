"""Durable proposal dispatch, cancellation, staleness and uncertain outcomes."""
from datetime import timedelta
import json
import sys
import unittest

from test_constitution import Fixture
from verantyx.jobs import submit, run_job, cancel, worker, list_jobs
from verantyx.application import record_run
from verantyx.errors import LedgerError
from verantyx.storage.sqlite import EventStore


class JobTests(Fixture):
    def setUp(self):
        super().setUp()
        self.revision = self.run_task("task")["recorded_revision"]
        self.marker = self.root / "calls"
        self.script = self.root / "fixture_adapter.py"
        self.script.write_text("import json,sys\nfrom pathlib import Path\n"
                               + "p=Path(" + repr(str(self.marker)) + ")\n"
                               + "with p.open('a') as f: f.write('1')\n"
                               + "value=json.load(sys.stdin)\nprint(json.dumps(value['proposal_template']))\n")
        self.adapter = self.root / "adapter.json"
        self.adapter.write_text(json.dumps({"argv": [sys.executable, str(self.script)]}))

    def submit(self, key="job", **kwargs):
        return submit(self.root, self.cfg, "task", adapter_path=self.adapter, key=key,
                      expected_revision=self.revision, clock=self.clock, **kwargs)

    def dispatch_job(self, key="job", **kwargs):
        return run_job(self.root, self.cfg, key, clock=self.clock, **kwargs)

    def test_dispatch_records_proposal_once_and_keeps_authority_separate(self):
        self.submit()
        result = worker(self.root, self.cfg, clock=self.clock)
        self.assertEqual(result["processed"][0]["status"], "COMPLETED")
        self.assertTrue(self.dispatch_job()["duplicate"])
        self.assertEqual(self.marker.read_text(), "1")
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            types = [e["type"] for e in store.events("task")]
        self.assertEqual(types.count("ProposalRecorded"), 2)
        self.assertNotIn("EffectAuthorized", types)
        self.assertNotIn("HumanDecisionRecorded", types)

    def test_cancelled_and_delayed_jobs_are_not_delivered(self):
        self.submit("cancel")
        cancel(self.root, self.cfg, "cancel", reason="fixture", clock=self.clock)
        self.submit("later", delay=60)
        self.assertEqual(worker(self.root, self.cfg, clock=self.clock)["processed"], [])
        self.assertFalse(self.marker.exists())
        self.time += timedelta(seconds=61)
        self.assertEqual(worker(self.root, self.cfg, clock=self.clock)["processed"][0]["status"], "COMPLETED")

    def test_expired_job_and_changed_context_do_not_call_adapter(self):
        self.submit("expired", ttl=1)
        self.time += timedelta(seconds=2)
        self.assertEqual(self.dispatch_job("expired")["status"], "STALE")
        self.submit("changed")
        record_run(self.root, self.cfg, run_id="task", resume=True, key="refresh", clock=self.clock)
        self.assertEqual(self.dispatch_job("changed")["details"]["code"], "JOB_CONTEXT_CHANGED")
        self.assertFalse(self.marker.exists())

    def test_changed_adapter_is_not_silently_delivered(self):
        self.submit()
        self.adapter.write_text(json.dumps({"argv": [sys.executable, "-c", "print('changed')"]}))
        result = self.dispatch_job()
        self.assertEqual(result["status"], "STALE")
        self.assertEqual(result["details"]["code"], "JOB_ADAPTER_CHANGED")
        self.assertFalse(self.marker.exists())

    def test_changed_launcher_script_is_not_silently_delivered(self):
        self.submit()
        self.script.write_text("print('substituted')\n")
        result = self.dispatch_job()
        self.assertEqual(result["details"]["code"], "JOB_ADAPTER_CHANGED")
        self.assertFalse(self.marker.exists())

    def test_expiry_immediately_before_dispatch_does_not_call_adapter(self):
        self.submit(ttl=1)
        def delay(stage):
            if stage == "after_started":
                self.time += timedelta(seconds=2)
        result = self.dispatch_job(fault=delay)
        self.assertEqual(result["details"]["code"], "JOB_EXPIRED")
        self.assertFalse(self.marker.exists())

    def test_unknown_call_is_not_automatically_retried(self):
        self.submit()
        def fault(stage):
            if stage == "bridge.after_started":
                raise RuntimeError("interrupted")
        with self.assertRaises(RuntimeError):
            self.dispatch_job(fault=fault)
        self.assertEqual(worker(self.root, self.cfg, clock=self.clock)["processed"], [])
        self.assertEqual(list_jobs(self.root, self.cfg)["jobs"][0]["status"], "RUNNING_OR_INTERRUPTED")
        self.assertEqual(self.dispatch_job(recover=True)["status"], "OUTCOME_UNKNOWN")
        self.assertFalse(self.marker.exists())

    def test_persisted_response_and_committed_proposal_recover_without_call(self):
        for stage in ("bridge.after_response", "after_proposal"):
            with self.subTest(stage=stage):
                key = stage.replace(".", "-")
                with EventStore(self.root, self.cfg["project"]["id"]) as store:
                    self.revision = store.events("task")[-1]["revision"]
                self.submit(key)
                def fault(current):
                    if current == stage:
                        raise RuntimeError("interrupted")
                with self.assertRaises(RuntimeError):
                    self.dispatch_job(key, fault=fault)
                before = self.marker.read_text()
                result = self.dispatch_job(key, recover=True)
                self.assertEqual(result["status"], "COMPLETED", result)
                self.assertTrue(result["details"]["recovered"])
                self.assertEqual(self.marker.read_text(), before)

    def test_submit_idempotency_binds_the_request(self):
        self.submit()
        self.assertTrue(self.submit()["duplicate"])
        with self.assertRaises(LedgerError) as error:
            self.submit(delay=10)
        self.assertEqual(error.exception.code, "IDEMPOTENCY_CONFLICT")
