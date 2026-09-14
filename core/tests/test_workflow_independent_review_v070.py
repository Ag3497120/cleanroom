"""Independent counterexamples for compiled/reused workflow and answer hooks."""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from unittest import mock
import json
import sys
import unittest

import test_asset_workflow_v070 as base_fixture
from verantyx.application import get_projection, record_run
from verantyx.domain.asset_workflow import compile_document, validate_project_bindings
from verantyx.domain.codec import canonical, digest
from verantyx.domain.events import make_event
from verantyx.errors import LedgerError
from verantyx.kernel.reducer import replay
from verantyx.responses import compose
from verantyx.storage.sqlite import EventStore
from verantyx.workflow_presentation import snapshot


class IndependentWorkflowReview(unittest.TestCase):
    setUp = base_fixture.AssetWorkflowTests.setUp
    tearDown = base_fixture.AssetWorkflowTests.tearDown
    request = base_fixture.AssetWorkflowTests.request
    adapter_mode = base_fixture.AssetWorkflowTests.adapter_mode
    call = base_fixture.AssetWorkflowTests.call
    events = base_fixture.AssetWorkflowTests.events

    def state(self):
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            return get_projection(store, "first")["state"]

    def test_negative_control_that_passes_is_contested_not_success(self):
        self.script.write_text(base_fixture.MODEL.replace("b'{\"answer\":41}'", "b'{\"answer\":42}'"))
        self.adapter_mode("negative")
        result = self.call()
        self.assertEqual(result["workflow"]["status"], "CONTESTED")
        self.assertFalse(result["ok"])
        self.assertEqual(self.counter.read_text(), "1")
        control = next(iter(result["state"]["verifications"].values()))["receipt"]["result"]["negative_controls"][0]
        self.assertFalse(control["rejected"])

    def test_unknown_or_no_check_never_looks_successful(self):
        self.adapter_mode("none")
        result = self.call()
        self.assertEqual(result["workflow"]["status"], "NO_PLAN")
        self.assertFalse(result["ok"])
        self.assertEqual(result["workflow"]["results"], [])

    def test_reused_contract_refutes_new_target_with_identical_negative_control(self):
        self.adapter_mode("negative")
        first = self.call()
        (self.root / "report.json").write_text('{"answer":99,"ok":true}')
        self.request("second")
        self.adapter_mode("reuse")
        result = self.call("second", key="second")
        self.assertEqual(result["workflow"]["status"], "REFUTED")
        self.assertFalse(result["ok"])
        for name in ("checks", "negative_controls", "method", "property"):
            self.assertEqual(first["workflow"]["plan"]["steps"][0]["spec"][name],
                             result["workflow"]["plan"]["steps"][0]["spec"][name])
        self.assertEqual(self.counter.read_text(), "2")

    def test_timeout_has_one_attempt_and_no_implicit_repair_call(self):
        self.script.write_text(base_fixture.MODEL.replace("pathlib.Path(os.environ['INPUT']).write_text(json.dumps(r))",
                                            "pathlib.Path(os.environ['INPUT']).write_text(json.dumps(r))\nimport time; time.sleep(0.5)"))
        with self.assertRaises(LedgerError) as first:
            self.call(timeout=0.15)
        self.assertEqual(first.exception.code, "BRIDGE_TIMEOUT")
        calls = self.counter.read_text() if self.counter.exists() else "0"
        with self.assertRaises(LedgerError) as second:
            self.call(timeout=0.15)
        self.assertEqual(second.exception.code, "BRIDGE_TIMEOUT")
        self.assertEqual(self.counter.read_text() if self.counter.exists() else "0", calls)
        self.assertFalse(any(event["type"] == "VerificationStarted" for event in self.events()))

    def test_new_proposal_between_steps_stops_before_second_check(self):
        self.adapter_mode("multiple")
        def change(stage):
            if stage == "after_check":
                record_run(self.root, self.cfg, run_id="first", resume=True, clock=self.clock)
        with self.assertRaises(LedgerError) as raised:
            self.call(fault=change)
        self.assertEqual(raised.exception.code, "REVISION_CONFLICT")
        self.assertEqual(sum(event["type"] == "VerificationStarted" for event in self.events()), 1)
        self.assertFalse(any(event["type"] == "AssetWorkflowFinished" for event in self.events()))

    def test_forged_source_with_consistent_local_hashes_fails_project_binding(self):
        self.call()
        self.adapter_mode("reuse")
        second = self.call(key="reuse")
        events = self.events()
        planned = next(event for event in reversed(events) if event["type"] == "AssetWorkflowPlanned")
        payload = deepcopy(planned["payload"])
        source = payload["context"]["available_methods"][0]
        source["spec"]["checks"][0]["expected"] = 99
        source["contract_hash"] = digest(source["spec"])
        payload["context_sha256"] = digest(payload["context"])
        payload["document"]["context_sha256"] = payload["context_sha256"]
        # The current literal-binding contract rejects the forged value before
        # any replacement plan can be compiled.  This is stronger than the
        # older downstream project-binding rejection.
        with self.assertRaises(LedgerError) as raised:
            compile_document(payload["context"], payload["document"], payload["max_checks"])
        self.assertEqual(raised.exception.details["reason"], "EXPECTATION_LITERAL_MISMATCH")
        return

    def test_changed_observation_marks_previous_workflow_historical(self):
        self.call()
        (self.root / "report.json").write_text('{"answer":99}')
        record_run(self.root, self.cfg, run_id="first", resume=True, clock=self.clock)
        value = snapshot(self.state())
        self.assertEqual(value.get("currentness"), "HISTORICAL", value)
        self.assertIn("SELECTED_FILE_CHANGED", value["stale_reasons"])

    def test_expired_result_is_historical_in_new_answer_input(self):
        self.call()
        self.time += timedelta(minutes=6)
        record_run(self.root, self.cfg, run_id="first", resume=True, clock=self.clock)
        state = self.state()
        result = compose(self.root, self.cfg, "first", key="new-answer", expected_revision=state["revision"], clock=self.clock)
        workflow = result["state"]["latest_response"]["request_snapshot"]["asset_workflow"]
        self.assertEqual(workflow.get("currentness"), "HISTORICAL", workflow)
        self.assertIn("RESULT_EXPIRED", workflow["stale_reasons"])

    def test_response_time_detects_expiry_without_extra_observation(self):
        self.call()
        self.time += timedelta(minutes=6)
        state = self.state()
        count = len(state["observations"])
        result = compose(self.root, self.cfg, "first", key="elapsed", expected_revision=state["revision"], clock=self.clock)
        workflow = result["state"]["latest_response"]["request_snapshot"]["asset_workflow"]
        self.assertEqual(workflow["currentness"], "HISTORICAL")
        self.assertIn("RESULT_EXPIRED", workflow["stale_reasons"])
        self.assertEqual(len(result["state"]["observations"]), count)

    def test_current_display_marks_expiry_at_explicit_time(self):
        self.call()
        from verantyx.workflow_presentation import lines
        from verantyx.application import iso
        before = lines(self.state(), "ja", as_of=iso(self.clock()))
        later = lines(self.state(), "ja", as_of=iso(self.clock() + timedelta(minutes=6)))
        self.assertFalse(any("以前の対象" in value for value in before))
        self.assertTrue(any("以前の対象" in value for value in later))
        self.assertTrue(any("検査結果の有効期限" in value for value in later))

    def test_new_proposal_does_not_borrow_prior_workflow_currentness(self):
        self.call()
        state = self.state()
        proposal = deepcopy(state["proposal"])
        proposal.update(context_revision=state["revision"], summary="A newly interpreted proposal")
        path = self.root / "new-proposal.json"
        path.write_text(json.dumps(proposal))
        record_run(self.root, self.cfg, run_id="first", resume=True, proposal_path=path, clock=self.clock)
        value = snapshot(self.state())
        self.assertEqual(value["status"], "COMPLETED")
        self.assertEqual(value["currentness"], "HISTORICAL")
        self.assertIn("PROPOSAL_CHANGED", value["stale_reasons"])

    def test_old_response_snapshot_replays_unchanged_without_clock_or_files(self):
        self.call()
        state = self.state()
        original = snapshot
        def legacy(current, **kwargs):
            return original(current, version=1)
        with mock.patch("verantyx.workflow_presentation.snapshot", side_effect=legacy):
            old = compose(self.root, self.cfg, "first", key="legacy", expected_revision=state["revision"], clock=self.clock)
        recorded = old["state"]["latest_response"]
        self.assertNotIn("currentness", recorded["request_snapshot"]["asset_workflow"])
        events = self.events("first")
        with mock.patch("verantyx.application.now", side_effect=AssertionError("clock in replay")), \
             mock.patch("builtins.open", side_effect=AssertionError("file read in replay")), \
             mock.patch("subprocess.run", side_effect=AssertionError("process in replay")):
            recovered = replay(events)
        self.assertEqual(recovered["latest_response"], recorded)

    def test_resuming_saved_response_preserves_its_original_as_of(self):
        self.call()
        state = self.state()
        def stop(stage):
            if stage == "after_response":
                raise RuntimeError("interrupted after persisted answer")
        with self.assertRaises(RuntimeError):
            compose(self.root, self.cfg, "first", key="saved", expected_revision=state["revision"],
                    clock=self.clock, fault=stop)
        original_time = self.clock()
        self.time += timedelta(minutes=6)
        result = compose(self.root, self.cfg, "first", key="saved", expected_revision=state["revision"], clock=self.clock)
        stored = result["state"]["latest_response"]["request_snapshot"]["asset_workflow"]
        from verantyx.application import iso
        self.assertEqual(stored["as_of"], iso(original_time))
        self.assertEqual(stored["currentness"], "CURRENT")
        self.assertEqual(snapshot(result["state"], as_of=iso(self.clock()))["currentness"], "HISTORICAL")


if __name__ == "__main__":
    unittest.main()
