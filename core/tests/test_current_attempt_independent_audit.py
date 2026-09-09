"""Independent negative cases for plan-event freshness and legacy reply replay."""
from copy import deepcopy
import os
from pathlib import Path
import subprocess
import unittest
from unittest import mock

import test_current_editor_attempt as fixtures
from verantyx.application import dispatch
from verantyx.cli import parse
from verantyx.coordination import candidate_proposal, coordinate
from verantyx.domain.codec import digest
from verantyx.domain.effects import editor_binding
from verantyx.domain.events import make_event
from verantyx.effects import authorize, execute
from verantyx.errors import LedgerError
from verantyx.kernel.evaluate import evaluate
from verantyx.kernel.reducer import replay
from verantyx.responses import _recorded_request
from verantyx.shared_context import current_editor_attempt
from verantyx.storage.sqlite import EventStore, parse_archive


class CurrentAttemptIndependentAudit(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.CurrentEditorAttemptTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root, self.cfg = self.fixture.root, self.fixture.cfg

    def assert_error(self, code, call, *args, **kwargs):
        with self.assertRaises(LedgerError) as caught:
            call(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def prepared(self):
        result = self.fixture.case.workflow(context={"component": "calculator", "workload": "fixture", "risk": "LOW"})
        for args in (["init", "-q"], ["add", "calc.py", "test_calc.py"],
                     ["-c", "user.name=ARTIFICIAL AUDIT", "-c", "user.email=audit@example.invalid", "commit", "-qm", "fixed test"]):
            subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True)
        _, args = parse(["decide", "work", "--point", "editor-isolation", "--choice", "isolate", "--reason",
                         "ARTIFICIAL AUDIT ONLY", "--key", "fixture-decision", "--expected-revision", str(result["recorded_revision"])])
        dispatch(self.root, self.cfg, args, "ja")
        return self.fixture.state()

    def failed_replan(self, state, same_plan=True):
        _, after, _ = self.fixture.replan_failure(same_plan=same_plan, first={"state": state})
        return after

    def legacy(self):
        path = fixtures.VALIDATION / "current-attempt-before-same-plan-response.jsonl"
        events = parse_archive(path.read_bytes())["events"]
        position = max(i for i, event in enumerate(events) if event["type"] == "ResponseComposed")
        return events, position

    def test_real_authorization_rejects_same_hash_plan_after_transport_failure(self):
        before = self.prepared()
        after = self.failed_replan(before)
        self.assertEqual(digest(before["handoff_plan"]["plan"]), digest(after["handoff_plan"]["plan"]))
        with mock.patch("verantyx.effects.PrecedentBackend", side_effect=AssertionError("stale candidate reached executor")):
            self.assert_error("HANDOFF_REPAIR_REQUIRED", authorize, self.root, self.cfg, "work", "editor-apply",
                              os.environ["VERANTYX_PRECEDENT"], "stale-authorization")
        self.assertFalse(self.fixture.state()["effects"])

    def test_existing_lease_cannot_execute_after_same_hash_replan(self):
        self.prepared()
        auth = authorize(self.root, self.cfg, "work", "editor-apply", os.environ["VERANTYX_PRECEDENT"], "before-replan")
        state = self.failed_replan(auth["state"])
        self.assertIsNone(current_editor_attempt(state))
        with mock.patch("verantyx.effects.PrecedentBackend", side_effect=AssertionError("stale lease reached executor")):
            result = execute(self.root, self.cfg, "work", auth["lease_id"], os.environ["VERANTYX_PRECEDENT"], "attempt-execute")
        effect = result["state"]["effects"][auth["lease_id"]]
        self.assertFalse(result["ok"])
        self.assertEqual(effect["status"], "INVALIDATED")
        self.assertEqual(effect["reason"], "CONTEXT_CHANGED")
        self.assertFalse(Path(effect["lease"]["resource_scope"]).exists())

    def test_legacy_comparison_cannot_change_live_gate_or_current_pointer(self):
        events, position = self.legacy()
        state = replay(events[:position])
        before = deepcopy(state)
        self.assertEqual(_recorded_request(events[position]["payload"], state), events[position]["payload"]["request_snapshot"])
        self.assertEqual(state, before)
        self.assertIsNone(current_editor_attempt(state))
        self.assertEqual(evaluate(state, state["evaluated_at"])["actions"][0]["gate"], "DENY")
        self.assert_error("HANDOFF_REPAIR_REQUIRED", editor_binding, state, state["proposal"]["actions"][0])
        self.assert_error("HANDOFF_REPAIR_REQUIRED", candidate_proposal, state)

    def test_current_evaluation_never_calls_the_legacy_response_check(self):
        state = self.prepared()
        after = self.failed_replan(state)
        with mock.patch("verantyx.responses._v063_editor_response_check", side_effect=AssertionError("live evaluation used compatibility")):
            assessment = evaluate(after, after["evaluated_at"])
            self.assertEqual(assessment["actions"][0]["reason"], "HANDOFF_REPAIR_REQUIRED")
            self.assert_error("HANDOFF_REPAIR_REQUIRED", authorize, self.root, self.cfg, "work", "editor-apply",
                              os.environ["VERANTYX_PRECEDENT"], "no-legacy-authorization")

    def test_non_object_response_structure_is_a_domain_error_not_a_crash(self):
        events, position = self.legacy()
        original = events[position]
        for bad in ([1], 7, "invalid", True, [], None):
            with self.subTest(structure=bad):
                payload = deepcopy(original["payload"])
                payload["response_structure"] = bad
                forged = make_event(original["project_id"], original["stream_id"], original["revision"], original["command_id"],
                                    original["recorded_at"], original["type"], payload, original["event_id"], events[position - 1])
                with mock.patch("subprocess.run", side_effect=AssertionError("replay ran a process")):
                    self.assert_error("STORE_INTEGRITY", replay, [*events[:position], forged])

    def test_legacy_prompt_cannot_upgrade_reply_to_execution_permission(self):
        events, position = self.legacy()
        state = replay(events[:position])
        payload = deepcopy(events[position]["payload"])
        payload["response_structure"]["result"]["can_execute"] = True
        payload["request_snapshot"]["response_structure"] = deepcopy(payload["response_structure"])
        payload["request_sha256"] = digest(payload["request_snapshot"])
        self.assert_error("STORE_INTEGRITY", _recorded_request, payload, state)
        self.assertFalse(state["effects"])

    def test_model_cannot_supply_its_own_plan_event_binding(self):
        self.fixture.case.workflow()
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            events = store.events("work")
        position = next(i for i, event in enumerate(events) if event["type"] == "EditorAttemptRecorded")
        original = events[position]
        payload = deepcopy(original["payload"])
        payload["plan_ref"] = "invented-plan-event"
        self.assert_error("SHARED_CONTEXT_INVALID", make_event, original["project_id"], original["stream_id"],
                          original["revision"], original["command_id"], original["recorded_at"], original["type"], payload,
                          original["event_id"], events[position - 1])

    def test_interrupted_editor_record_retry_does_not_restore_before_plan_history(self):
        state = self.prepared()
        vera, editor = self.fixture.case.adapters("d['files']['calc.py'] += '# fresh\\n'")
        kwargs = dict(proposer_adapter=vera, editor_adapter=editor, key="interrupted-current", expected_revision=state["revision"],
                      include_paths=["calc.py", "test_calc.py"], max_repairs=0)
        from verantyx.coordination import append as real_append
        def interruption(*args, **options):
            result = real_append(*args, **options)
            if args[3] == "EditorAttemptRecorded":
                raise RuntimeError("artificial post-record interruption")
            return result
        with mock.patch("verantyx.coordination.append", side_effect=interruption), self.assertRaises(RuntimeError):
            coordinate(self.root, self.cfg, "work", **kwargs)
        recorded = self.fixture.state()
        calls = len(self.fixture.case.fixture.invocations())
        resumed = coordinate(self.root, self.cfg, "work", **kwargs)
        self.assertEqual(len(self.fixture.case.fixture.invocations()), calls)
        current = current_editor_attempt(resumed["state"])
        self.assertEqual(current, current_editor_attempt(recorded))
        self.assertEqual(current["plan_ref"], recorded["handoff_plan"]["source_ref"])
        self.assertNotEqual(current["plan_ref"], state["handoff_plan"]["source_ref"])


if __name__ == "__main__":
    unittest.main()
