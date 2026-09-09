"""Cross-review counterexamples at dispatch, signed input and recovery boundaries."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from unittest import mock
import hashlib
import json
import unittest

from test_constitution import Fixture
from test_external_capture_v070 import write_capture_adapter
from verantyx import authority, bridges, commands_v03, jobs
from verantyx.application import iso, record_run
from verantyx.cli import parse
from verantyx.errors import LedgerError
from verantyx.external_capture import capture, read_body


class CaptureBoundaryReviewTests(Fixture):
    def setUp(self):
        super().setUp()
        self.revision = record_run(self.root, self.cfg, request="Synthetic retry", run_id="task", clock=self.clock)["recorded_revision"]
        self.calls = self.root / "calls.jsonl"
        self.adapter = write_capture_adapter(self.root, self.calls)
        self.script = self.root / "capture_model.py"

    def count(self):
        return len(self.calls.read_text().splitlines()) if self.calls.exists() else 0

    def captured(self, **kwargs):
        return capture(self.root, self.cfg, "task", body="Synthetic outside AI advice", provider="fixture", model="model-A",
                       key="capture", expected_revision=self.revision, adapter_path=self.adapter, clock=self.clock, **kwargs)

    def change_script(self):
        self.script.write_text(self.script.read_text() + "\n# altered fixture launcher\n")

    @contextmanager
    def active_approval(self, *, input_files=()):
        # An artificial active command context, testing the late guard rather
        # than Ed25519 itself (covered by test_authority's real signatures).
        value = {"issued_at": iso(self.time), "expires_at": iso(self.time + timedelta(seconds=1)),
                 "input_files": list(input_files)}
        token = authority._APPROVED.set(value)
        clock_token = authority._APPROVED_CLOCK.set(self.clock)
        try:
            yield
        finally:
            authority._APPROVED.reset(token)
            authority._APPROVED_CLOCK.reset(clock_token)

    def test_capture_launcher_change_after_propose_marker_prevents_first_call(self):
        def change(stage):
            if stage == "propose.after_started":self.change_script()
        with self.assertRaisesRegex(LedgerError, "JOB_ADAPTER_CHANGED"):
            self.captured(fault=change)
        self.assertEqual(self.count(), 0)

    def test_expired_signature_after_capture_prevents_proposal_call(self):
        def expire(stage):
            if stage == "after_capture":self.time += timedelta(seconds=2)
        with self.active_approval():
            with self.assertRaisesRegex(LedgerError, "AUTHORITY_EXPIRED"):
                self.captured(fault=expire)
        self.assertEqual(self.count(), 0)

    def test_capture_between_models_keeps_original_executor(self):
        def change(stage):
            if stage == "after_proposal":self.change_script()
        with self.assertRaisesRegex(LedgerError, "JOB_ADAPTER_CHANGED"):
            self.captured(fault=change)
        self.assertEqual(self.count(), 1)

    def test_standalone_collect_between_models_keeps_original_executor(self):
        _, args = parse(["propose", "task", "--adapter", str(self.adapter), "--key", "standalone",
                         "--expected-revision", str(self.revision), "--collect"])
        original = bridges.propose
        def changed(*a, **kw):
            result = original(*a, **kw)
            self.change_script()
            return result
        with mock.patch("verantyx.bridges.propose", side_effect=changed):
            with self.assertRaisesRegex(LedgerError, "JOB_ADAPTER_CHANGED"):
                commands_v03.dispatch(self.root, self.cfg, args, "ja")
        self.assertEqual(self.count(), 1)

    def test_saved_collection_result_can_recover_after_job_expiry(self):
        jobs.submit(self.root, self.cfg, "task", adapter_path=self.adapter, key="job", expected_revision=self.revision,
                    collect=True, ttl=1, clock=self.clock)
        def stop(stage):
            if stage == "respond.after_response":raise RuntimeError("interrupted")
        with self.assertRaises(RuntimeError):jobs.run_job(self.root, self.cfg, "job", clock=self.clock, fault=stop)
        self.assertEqual(self.count(), 2)
        self.time += timedelta(seconds=2)
        result = jobs.run_job(self.root, self.cfg, "job", clock=self.clock, recover=True)
        self.assertEqual(result["status"], "COMPLETED", result)
        self.assertEqual(self.count(), 2)

    def test_ambiguous_collection_stays_unknown_after_job_expiry(self):
        jobs.submit(self.root, self.cfg, "task", adapter_path=self.adapter, key="job", expected_revision=self.revision,
                    collect=True, ttl=1, clock=self.clock)
        def stop(stage):
            if stage == "respond.after_started":raise RuntimeError("interrupted")
        with self.assertRaises(RuntimeError):jobs.run_job(self.root, self.cfg, "job", clock=self.clock, fault=stop)
        self.time += timedelta(seconds=2)
        result = jobs.run_job(self.root, self.cfg, "job", clock=self.clock, recover=True)
        self.assertEqual(result["status"], "OUTCOME_UNKNOWN", result)
        self.assertEqual(self.count(), 1)

    def test_selected_body_must_match_signed_input_at_read_boundary(self):
        path = self.root / "quote.txt"
        original = b"approved synthetic quotation"
        path.write_bytes(original)
        manifest = [{"path": str(path), "sha256": hashlib.sha256(original).hexdigest()}]
        with self.active_approval(input_files=manifest):
            self.assertEqual(read_body(path), original.decode())
            path.write_text("substituted quotation after the command gate")
            with self.assertRaisesRegex(LedgerError, "AUTHORITY_INPUT_CHANGED"):
                read_body(path)

    def test_final_proposal_boundary_checks_project_changes_before_model(self):
        def change(stage):
            if stage == "propose.after_started":
                record_run(self.root, self.cfg, request="concurrent task", run_id="other", clock=self.clock)
        with self.assertRaisesRegex(LedgerError, "REVISION_CONFLICT"):
            self.captured(fault=change)
        self.assertEqual(self.count(), 0)

    def test_standalone_collect_recovers_saved_response_and_keeps_legacy_child_keys(self):
        from verantyx.external_capture import collect_proposal
        def call(**kwargs):
            return collect_proposal(self.root, self.cfg, "task", adapter_path=self.adapter, key="collected",
                                    expected_revision=self.revision, clock=self.clock, **kwargs)
        def stop(stage):
            if stage == "respond.after_response":raise RuntimeError("interrupted")
        with self.assertRaises(RuntimeError):call(fault=stop)
        result = call()
        self.assertTrue(result["collected"])
        self.assertEqual(result["state"]["latest_response"]["mode"], "GENERATED")
        self.assertEqual(self.count(), 2)
        self.assertTrue(call()["duplicate"])
        self.assertEqual(self.count(), 2)

    def test_next_task_model_receives_captured_excerpt_and_collected_candidate(self):
        captured = self.captured()
        other = record_run(self.root, self.cfg, request="Second artificial task", run_id="other", clock=self.clock)
        result = bridges.propose(self.root, self.cfg, "other", adapter_path=self.adapter, key="model-B",
                                 expected_revision=other["recorded_revision"], reuse_assets=True)
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        self.assertEqual(len(calls), 3)
        rows = calls[-1]["context_assets"]["reuse_candidates"]
        quoted = next(row for row in rows if row["kind"] == "EXTERNAL_CAPTURE")
        self.assertEqual(quoted["quoted_excerpt"], "Synthetic outside AI advice")
        self.assertEqual(quoted["source_refs"], [captured["capture_source_ref"]])
        self.assertEqual(quoted["authority"], "REFERENCE_ONLY")
        idea = next(row for row in rows if row["kind"] == "MODEL_CANDIDATE")
        self.assertEqual(idea["procedure"], "Check one applied effect")
        self.assertEqual(idea["verification"], "UNVERIFIED")
        self.assertEqual(result["state"]["human_decisions"], {})
        self.assertEqual(result["state"]["effects"], {})

    def signed_setup(self):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        key = Ed25519PrivateKey.generate()
        public = self.root / "operator.pem"
        public.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        approval = authority.request(self.root, self.cfg, ["authority-enable", "--public-key", str(public)], clock=self.clock)
        authority.execute(self.root, self.cfg, approval, key.sign(authority.signing_bytes(approval)), clock=self.clock)
        return key

    def test_real_signed_capture_detects_substitution_after_generic_command_gate(self):
        key = self.signed_setup()
        path = self.root / "approved-quote.txt"
        path.write_text("approved quoted bytes")
        argv = ["capture", "task", "--input", str(path), "--provider", "fixture", "--model", "fixture",
                "--key", "signed-capture", "--expected-revision", str(self.revision), "--reference-only"]
        approval = authority.request(self.root, self.cfg, argv, clock=self.clock)
        original = read_body
        def changed_body(*args, **kwargs):
            path.write_text("substituted between gate and selected-input read")
            return original(*args, **kwargs)
        with mock.patch("verantyx.external_capture.read_body", side_effect=changed_body):
            with self.assertRaisesRegex(LedgerError, "AUTHORITY_INPUT_CHANGED"):
                authority.execute(self.root, self.cfg, approval, key.sign(authority.signing_bytes(approval)), clock=self.clock)
        from verantyx.storage.sqlite import EventStore
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            self.assertEqual(store.events("task")[-1]["revision"], self.revision)

    def test_signed_job_collect_flag_cannot_be_removed_and_old_shape_stays_valid(self):
        key = self.signed_setup()
        argv = ["job-submit", "task", "--adapter", str(self.adapter), "--key", "signed-job", "--collect",
                "--expected-revision", str(self.revision)]
        approval = authority.request(self.root, self.cfg, argv, clock=self.clock)
        authority.execute(self.root, self.cfg, approval, key.sign(authority.signing_bytes(approval)), clock=self.clock)
        from verantyx.adapters.invocation_journal import InvocationJournal
        with InvocationJournal(self.root, "job", "signed-job") as journal:
            queued = journal.read("queued")
        authority._job_matches(approval, queued)
        legacy = deepcopy(queued)
        legacy.pop("collect")
        legacy.pop("assets_hash")
        jobs._validate(legacy)
        with self.assertRaisesRegex(LedgerError, "AUTHORITY_JOB_MISMATCH"):
            authority._job_matches(approval, legacy)
        old_approval = deepcopy(approval)
        old_approval["operation"]["arguments"].pop("collect")
        authority._job_matches(old_approval, legacy)


if __name__ == "__main__":
    unittest.main()
