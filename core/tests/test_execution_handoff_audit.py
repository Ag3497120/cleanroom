"""Independent handoff audit of dispatch freshness and effect replay gates."""
from copy import deepcopy
from datetime import timedelta
import json
import sys
import threading
import unittest
import uuid

from test_constitution import Fixture, PRECEDENT, proposal
from verantyx.application import record_run
from verantyx.domain.codec import digest
from verantyx.domain.events import make_event
from verantyx.domain.effects import unittest_closure
from verantyx.effects import authorize, execute
from verantyx.errors import LedgerError
from verantyx.jobs import cancel, run_job, submit, worker
from verantyx.kernel.reducer import replay
from verantyx.storage.sqlite import EventStore


class DispatchHandoffAudit(Fixture):
    def setUp(self):
        super().setUp()
        self.revision = self.run_task("task")["recorded_revision"]
        self.marker = self.root / "calls"
        self.script = self.root / "adapter.py"
        self.script.write_text("import json,sys\nfrom pathlib import Path\n"
                              + "p=Path(" + repr(str(self.marker)) + ")\n"
                              + "with p.open('a') as f: f.write('1')\n"
                              + "value=json.load(sys.stdin)\nprint(json.dumps(value['proposal_template']))\n")
        self.adapter = self.root / "adapter.json"
        self.adapter.write_text(json.dumps({"argv": [sys.executable, "-u", str(self.script)]}))

    def submit(self, **kwargs):
        return submit(self.root, self.cfg, "task", adapter_path=self.adapter, key="job", expected_revision=self.revision,
                      clock=self.clock, **kwargs)

    def dispatch(self, **kwargs):
        return run_job(self.root, self.cfg, "job", clock=self.clock, **kwargs)

    def test_script_after_interpreter_options_is_bound_to_the_queued_job(self):
        self.submit()
        self.script.write_text(self.script.read_text().replace("f.write('1')", "f.write('2')"))
        result = self.dispatch()
        self.assertEqual(result["status"], "STALE")
        self.assertEqual(result["details"]["code"], "JOB_ADAPTER_CHANGED")
        self.assertFalse(self.marker.exists())

    def test_relative_script_in_explicit_working_directory_is_bound(self):
        self.adapter.write_text(json.dumps({"argv": [sys.executable, "-u", self.script.name], "cwd": str(self.root)}))
        self.submit()
        self.script.write_text(self.script.read_text().replace("f.write('1')", "f.write('2')"))
        result = self.dispatch()
        self.assertEqual(result["status"], "STALE")
        self.assertFalse(self.marker.exists())

    def test_adapter_change_after_job_started_is_checked_before_invocation(self):
        self.submit()
        def mutate(stage):
            if stage == "after_started":
                self.adapter.write_text(json.dumps({"argv": [sys.executable, "-c", "raise SystemExit(0)"]}))
        result = self.dispatch(fault=mutate)
        self.assertEqual(result["details"]["code"], "JOB_ADAPTER_CHANGED")
        self.assertFalse(self.marker.exists())

    def test_script_change_after_bridge_started_is_checked_before_invocation(self):
        self.submit()
        def mutate(stage):
            if stage == "bridge.after_started":
                self.script.write_text(self.script.read_text().replace("f.write('1')", "f.write('2')"))
        result = self.dispatch(fault=mutate)
        self.assertEqual(result["status"], "STALE")
        self.assertEqual(result["details"]["code"], "JOB_ADAPTER_CHANGED")
        self.assertFalse(self.marker.exists())

    def test_expiry_after_bridge_started_prevents_process_creation(self):
        self.submit(ttl=1)
        def delay(stage):
            if stage == "bridge.after_started":
                self.time += timedelta(seconds=2)
        result = self.dispatch(fault=delay)
        self.assertEqual(result["details"]["code"], "JOB_EXPIRED")
        self.assertFalse(self.marker.exists())

    def test_context_change_after_bridge_started_prevents_delivery(self):
        self.submit()
        def mutate(stage):
            if stage == "bridge.after_started":
                record_run(self.root, self.cfg, run_id="task", resume=True, key="changed-context", clock=self.clock)
        result = self.dispatch(fault=mutate)
        self.assertEqual(result["details"]["code"], "JOB_CONTEXT_CHANGED")
        self.assertFalse(self.marker.exists())

    def test_second_worker_and_cancel_cannot_duplicate_an_active_dispatch(self):
        self.submit()
        entered, release = threading.Event(), threading.Event()
        results = []
        def pause(stage):
            if stage == "after_started":
                entered.set()
                if not release.wait(10):
                    raise RuntimeError("test coordination timeout")
        def first():
            try:
                results.append(self.dispatch(fault=pause))
            except BaseException as error:
                results.append(error)
        thread = threading.Thread(target=first)
        thread.start()
        try:
            self.assertTrue(entered.wait(10))
            self.assertEqual(worker(self.root, self.cfg, clock=self.clock)["processed"], [])
            with self.assertRaises(LedgerError) as error:
                cancel(self.root, self.cfg, "job", reason="late cancellation", clock=self.clock)
            self.assertEqual(error.exception.code, "STORE_BUSY")
        finally:
            release.set()
            thread.join(10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(results[0]["status"], "COMPLETED", results)
        self.assertEqual(self.marker.read_text(), "1")


@unittest.skipUnless(PRECEDENT, "requires explicit Precedent path")
class EffectReplayHandoffAudit(Fixture):
    def setUp(self):
        super().setUp()
        self.init_git()
        self.run_task("task", proposal("task", action=True))
        self.command("decide", "task", point_id="separation", choice="isolate", reason="fixture")
        self.authorized = authorize(self.root, self.cfg, "task", "writer", PRECEDENT, "allow", clock=self.clock, backend=self.backend)
        self.lease_id = next(iter(self.authorized["state"]["effects"]))

    def events(self):
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            return store.events("task")

    def rechain(self, events):
        previous = None
        result = []
        for index, event in enumerate(events):
            current = make_event(event["project_id"], event["stream_id"], index + 1, event["command_id"], event["recorded_at"],
                                 event["type"], event["payload"], event["event_id"], previous)
            result.append(current)
            previous = current
        return result

    def test_authorization_cannot_be_replayed_against_a_different_human_choice(self):
        events = deepcopy(self.events())
        for event in events:
            if event["type"] == "HumanDecisionRecorded":
                event["payload"]["choice"] = "shared"
        changed = self.rechain(events)
        index = next(i for i, event in enumerate(changed) if event["type"] == "EffectAuthorized")
        self.assertEqual(replay(changed[:index])["human_decisions"]["separation"]["choice"], "shared")
        with self.assertRaises(LedgerError):
            replay(changed)

    def test_new_workspace_observation_cannot_be_ignored_when_replaying_start(self):
        previous = self.events()
        observation = deepcopy(self.authorized["state"]["workspace_observations"][-1])
        observation.pop("source_ref")
        observation["workspace"]["files"]["calc.py"]["sha256"] = "a" * 64
        batch = []
        for kind, payload in (("WorkspaceObserved", observation), ("EvaluationRecorded", {"as_of": previous[-1]["recorded_at"], "evaluator": "m1.v1"}),
                              ("ExecutionStarted", {"lease_id": self.lease_id})):
            before = batch[-1] if batch else previous[-1]
            batch.append(make_event(self.cfg["project"]["id"], "task", before["revision"] + 1, str(uuid.uuid4()),
                previous[-1]["recorded_at"], kind, payload, str(uuid.uuid4()), before))
        with self.assertRaises(LedgerError):
            replay([*previous, *batch])

    def test_successful_receipt_without_completed_suite_output_is_rejected(self):
        execute(self.root, self.cfg, "task", self.lease_id, PRECEDENT, "execute", clock=self.clock, backend=self.backend)
        events = deepcopy(self.events())
        receipt = next(event for event in events if event["type"] == "ExecutionReceipt")
        self.assertTrue(receipt["payload"]["verification"]["result"]["passed"])
        receipt["payload"]["verification"]["result"]["output"] = ""
        with self.assertRaises(LedgerError):
            replay(self.rechain(events))

    def test_incomplete_test_and_runner_error_are_unknown_but_completed_failure_refutes(self):
        raw = {"passed": False, "exit": 1, "reason": None, "output": "", "seconds": 0.1, "backend": "macos-seatbelt"}
        for output, reason in (("", None), ("", "timeout"), ("", "output quota"), ("", "SUITE_COMPLETION_NOT_OBSERVED"),
                               ("Ran 1 test in 0.01s\n\nFAILED (errors=1)\n", None),
                               ("Ran 1 test in 0.01s\n\nOK (skipped=1)\n", None)):
            self.assertEqual(unittest_closure({**raw, "output": output, "reason": reason}), "UNKNOWN")
        self.assertEqual(unittest_closure({**raw, "output": "Ran 1 test in 0.01s\n\nFAILED (failures=1)\n"}), "REFUTED")
        self.assertEqual(unittest_closure({**raw, "passed": True, "exit": 0, "output": "Ran 1 test in 0.01s\n\nOK\n"}), "BOUNDED")

    def incomplete(self):
        document = proposal("incomplete", action=True)
        document["actions"][0]["arguments"]["files"]["calc.py"] = "import os\nos._exit(0)\n"
        self.run_task("incomplete", document)
        self.command("decide", "incomplete", point_id="separation", choice="isolate", reason="fixture")
        auth = authorize(self.root, self.cfg, "incomplete", "writer", PRECEDENT, "allow-incomplete", clock=self.clock, backend=self.backend)
        lease = auth["lease_id"]
        return execute(self.root, self.cfg, "incomplete", lease, PRECEDENT, "execute-incomplete", clock=self.clock, backend=self.backend)

    def test_actual_exit_before_unittest_is_unknown_in_receipt_gate_and_gap(self):
        result = self.incomplete()
        verification = result["execution"]["receipt"]["verification"]
        self.assertFalse(verification["result"]["passed"])
        self.assertEqual(verification["closure"], "UNKNOWN")
        assessment = result["state"]["assessment"]
        self.assertEqual(assessment["actions"][0]["gate"], "CANDIDATE_UNVERIFIED")
        gap = next(item for item in assessment["gaps"] if item["code"] == "CANDIDATE_TEST_INCOMPLETE")
        self.assertEqual((gap["epistemic_status"], gap["blocker"]), ("UNKNOWN", "EVIDENCE_MISSING"))
        self.assertNotIn("CANDIDATE_TEST_FAILED", [item["code"] for item in assessment["gaps"]])

    def test_legacy_incomplete_refuted_history_is_preserved_and_projected_as_unknown(self):
        result = self.incomplete()
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            events = deepcopy(store.events("incomplete"))
        source = next(event for event in events if event["type"] == "ExecutionReceipt")
        source["payload"]["verification"]["closure"] = "REFUTED"
        events = self.rechain(events)
        saved = deepcopy(events)
        state = replay(events)
        effect = state["effects"][result["execution"]["lease"]["id"]]
        self.assertEqual(effect["receipt"]["verification"]["closure"], "UNKNOWN")
        self.assertEqual(effect["verification_annotation"]["recorded_closure"], "REFUTED")
        self.assertEqual(effect["verification_annotation"]["source_ref"], effect["receipt_ref"])
        self.assertEqual(events, saved)


if __name__ == "__main__":
    unittest.main()
