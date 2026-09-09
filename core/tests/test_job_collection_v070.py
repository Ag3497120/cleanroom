"""Opt-in proposal jobs collect source-linked experience without effect rights."""
from datetime import timedelta
from pathlib import Path
import json
import os
import subprocess
import sys
import unittest

from test_constitution import Fixture
from test_external_capture_v070 import write_capture_adapter
from verantyx.adapters.invocation_journal import InvocationJournal
from verantyx.application import record_run
from verantyx.errors import LedgerError
from verantyx.jobs import submit, run_job
from verantyx.storage.sqlite import EventStore


class JobCollectionTests(Fixture):
    def setUp(self):
        super().setUp()
        self.revision = record_run(self.root, self.cfg, request="Retry advice", run_id="task",
                                   clock=self.clock)["recorded_revision"]
        self.calls = self.root / "calls.jsonl"
        self.adapter = write_capture_adapter(self.root, self.calls)

    def submitted(self, **kwargs):
        return submit(self.root, self.cfg, "task", adapter_path=self.adapter, key=kwargs.pop("key", "job"),
                      expected_revision=self.revision, clock=self.clock, **kwargs)

    def run_job(self, **kwargs):
        return run_job(self.root, self.cfg, kwargs.pop("key", "job"), clock=self.clock, **kwargs)

    def invocations(self):
        return [json.loads(line) for line in self.calls.read_text().splitlines()] if self.calls.exists() else []

    def test_opt_in_collects_candidates_and_uses_assets_in_both_calls(self):
        self.submitted(collect=True)
        result = self.run_job()
        self.assertEqual(result["status"], "COMPLETED", result)
        self.assertEqual(result["details"]["collection_mode"], "GENERATED")
        self.assertTrue(result["collect"])
        self.assertTrue(self.run_job()["duplicate"])
        self.assertEqual(len(self.invocations()), 2)
        self.assertTrue(all("context_assets" in value for value in self.invocations()))
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            kinds = [event["type"] for event in store.events("task")]
        self.assertIn("ResponseComposed", kinds)
        self.assertIn("LearningCandidateRaised", kinds)
        self.assertNotIn("EffectAuthorized", kinds)
        self.assertNotIn("HumanDecisionRecorded", kinds)

    def test_legacy_false_job_shape_and_single_generation_are_preserved(self):
        self.submitted()
        with InvocationJournal(self.root, "job", "job") as journal:
            document = journal.read("queued")
        self.assertNotIn("collect", document)
        self.assertNotIn("assets_hash", document)
        result = self.run_job()
        self.assertEqual(result["status"], "COMPLETED")
        self.assertNotIn("collect", result)
        self.assertNotIn("response_ref", result["details"])
        self.assertEqual(len(self.invocations()), 1)
        self.assertNotIn("context_assets", self.invocations()[0])

    def test_collect_flag_is_bound_to_submit_intent(self):
        self.submitted(collect=True)
        self.assertTrue(self.submitted(collect=True)["duplicate"])
        with self.assertRaises(LedgerError) as raised:
            self.submitted(collect=False)
        self.assertEqual(raised.exception.code, "IDEMPOTENCY_CONFLICT")
        with self.assertRaises(LedgerError):
            self.submitted(key="invalid", collect=1)

    def test_new_cross_task_assets_stale_a_collect_job_before_dispatch(self):
        self.submitted(collect=True)
        record_run(self.root, self.cfg, request="changed project context", run_id="other", clock=self.clock)
        result = self.run_job()
        self.assertEqual(result["status"], "STALE")
        self.assertEqual(result["details"]["code"], "JOB_CONTEXT_CHANGED")
        self.assertEqual(self.invocations(), [])

    def test_proposal_commit_interruption_resumes_collection_once(self):
        self.submitted(collect=True)
        def stop(stage):
            if stage == "after_proposal":
                raise RuntimeError("interrupted")
        with self.assertRaises(RuntimeError):
            self.run_job(fault=stop)
        self.assertEqual(len(self.invocations()), 1)
        result = self.run_job(recover=True)
        self.assertEqual(result["status"], "COMPLETED", result)
        self.assertEqual(len(self.invocations()), 2)

    def test_ambiguous_collection_is_not_automatically_reinvoked(self):
        self.submitted(collect=True)
        def stop(stage):
            if stage == "respond.after_started":
                raise RuntimeError("interrupted")
        with self.assertRaises(RuntimeError):
            self.run_job(fault=stop)
        result = self.run_job(recover=True)
        self.assertEqual(result["status"], "OUTCOME_UNKNOWN", result)
        self.assertEqual(result["details"]["code"], "BRIDGE_OUTCOME_UNKNOWN")
        self.assertEqual(len(self.invocations()), 1)

    def test_saved_collection_result_recovers_without_calling_models(self):
        self.submitted(collect=True)
        def stop(stage):
            if stage == "respond.after_response":
                raise RuntimeError("interrupted")
        with self.assertRaises(RuntimeError):
            self.run_job(fault=stop)
        result = self.run_job(recover=True)
        self.assertEqual(result["status"], "COMPLETED", result)
        self.assertEqual(len(self.invocations()), 2)

    def test_expiry_after_proposal_does_not_call_collection_model(self):
        self.submitted(collect=True, ttl=1)
        def expire(stage):
            if stage == "after_proposal":
                self.time += timedelta(seconds=2)
        result = self.run_job(fault=expire)
        self.assertEqual(result["status"], "STALE", result)
        self.assertEqual(result["details"]["code"], "JOB_EXPIRED")
        self.assertEqual(len(self.invocations()), 1)

    def test_invalid_collection_output_reports_fallback_not_captured_success(self):
        self.adapter = write_capture_adapter(self.root, self.calls, mutation="if 'response_template' in v: d['approved']=True")
        self.submitted(collect=True)
        result = self.run_job()
        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(result["details"]["collection_mode"], "FALLBACK")
        self.assertEqual(result["details"]["generator_error"], "RESPONSE_INVALID")
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            self.assertNotIn("LearningCandidateRaised", [e["type"] for e in store.events("task")])

    def test_cli_submit_collect_and_run_connect_to_response_collection(self):
        env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
               "PYTHONDONTWRITEBYTECODE": "1"}
        cli = [sys.executable, "-m", "verantyx", "--project", str(self.root), "--json"]
        submitted = subprocess.run([*cli, "job-submit", "task", "--adapter", str(self.adapter), "--collect",
                                    "--key", "cli-job", "--expected-revision", str(self.revision)],
                                   env=env, capture_output=True, text=True)
        self.assertEqual(submitted.returncode, 0, submitted.stdout + submitted.stderr)
        result = subprocess.run([*cli, "job-run", "cli-job"], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["details"]["collection_mode"], "GENERATED")
        self.assertEqual(len(self.invocations()), 2)


if __name__ == "__main__":
    unittest.main()
