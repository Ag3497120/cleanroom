"""Independent command sequences for candidate decision retention.

All model responses, decisions, files and repositories are artificial. Actual
Cross and Precedent processes test enforcement, not semantic understanding.
"""
from copy import deepcopy
import json
import os
import unittest
from unittest import mock

import test_candidate_decisions_v064 as candidate_fixtures
from verantyx.application import record_run
from verantyx.coordination import coordinate, stage_candidate
from verantyx.domain.codec import digest
from verantyx.effects import authorize, execute
from verantyx.errors import LedgerError
from verantyx.kernel.reducer import projection, replay
from verantyx.storage.sqlite import EventStore


class CandidateDecisionAuditTests(unittest.TestCase):
    def setUp(self):
        self.harness = candidate_fixtures.CandidateDecisionTests(methodName="runTest")
        self.harness.setUp()
        self.addCleanup(self.harness.doCleanups)
        self.root, self.cfg = self.harness.root, self.harness.cfg
        self.state = self.harness.workflow()["state"]
        self.isolation = self.state["proposal"]["actions"][0]["arguments"]["point_id"]
        self.state = self.harness.decide(self.isolation, "isolate")["state"]

    def replace(self, document, key):
        document["context_revision"] = self.state["revision"]
        path = self.root / (key + ".json")
        path.write_text(json.dumps(document))
        value = record_run(self.root, self.cfg, run_id="work", resume=True, proposal_path=path,
                           expected_revision=self.state["revision"], key=key)
        self.state = value["state"]
        return value

    def rehandoff(self, key):
        value = coordinate(self.root, self.cfg, "work", proposer_adapter=self.root / "vera.json",
                           editor_adapter=self.root / "editor.json", key=key,
                           expected_revision=self.state["revision"], include_paths=["calc.py", "test_calc.py"])
        self.state = value["state"]
        return value

    def permit(self, key):
        action = self.state["proposal"]["actions"][0]
        return authorize(self.root, self.cfg, "work", action["id"], os.environ["VERANTYX_PRECEDENT"], key)

    def test_rehandoff_cannot_replace_the_original_constraints_with_an_erased_proposal(self):
        altered = deepcopy(self.state["proposal"])
        altered["decision_points"] = [point for point in altered["decision_points"] if point["id"] != self.harness.point["id"]]
        altered["unknowns"] = []
        altered["claims"] = []
        self.replace(altered, "erased-proposal")
        self.assertEqual(self.state["assessment"]["actions"][0]["reason"], "EDITOR_CONSTRAINT_CHANGED")
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            before = store.events()
        with self.assertRaises(LedgerError) as caught:
            self.rehandoff("launder-original")
        self.assertEqual(caught.exception.code, "EDITOR_CONSTRAINT_CHANGED")
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            self.assertEqual(store.events(), before)
        self.assertFalse((self.root / ".verantyx/worktrees").exists())

    def test_added_value_decision_is_required_without_erasing_original_items(self):
        self.state = self.harness.decide(self.harness.point["id"], "preserve")["state"]
        altered = deepcopy(self.state["proposal"])
        added = {"id": "retention", "kind": "VALUE_DECISION", "decision_type": "retention_policy",
                 "question": "Retain or discard the audit record?", "options": [
                     {"id": "keep", "label": "Retain the audit record"},
                     {"id": "discard", "label": "Discard the audit record"}]}
        altered["decision_points"].append(added)
        self.replace(altered, "additional-value")
        self.rehandoff("retain-new-value")
        staged = stage_candidate(self.root, self.cfg, "work", key="retain-new-value-candidate",
                                 expected_revision=self.state["revision"])
        self.state = staged["state"]
        self.assertIn(self.harness.point, self.state["proposal"]["decision_points"])
        self.assertIn(added, self.state["proposal"]["decision_points"])
        self.assertEqual(self.state["assessment"]["actions"][0]["unresolved_decision_dependencies"], ["retention"])
        with self.assertRaises(LedgerError) as caught:
            self.permit("unanswered-addition")
        self.assertEqual(caught.exception.code, "EDITOR_DECISION_REQUIRED")
        # A subsequent model proposal cannot drop a newly added condition either.
        altered = deepcopy(self.state["proposal"])
        altered["decision_points"] = [point for point in altered["decision_points"] if point["id"] != "retention"]
        self.replace(altered, "drop-addition")
        with self.assertRaises(LedgerError) as caught:
            self.rehandoff("launder-addition")
        self.assertEqual(caught.exception.code, "EDITOR_CONSTRAINT_CHANGED")

    def test_kind_and_option_label_substitution_cannot_reuse_a_human_choice(self):
        self.state = self.harness.decide(self.harness.point["id"], "preserve")["state"]
        original = deepcopy(self.state["proposal"])
        for change in ("kind", "option-label"):
            with self.subTest(change=change):
                altered = deepcopy(original)
                point = next(point for point in altered["decision_points"] if point["id"] == self.harness.point["id"])
                if change == "kind":
                    point["kind"] = "IMPLEMENTATION_CHOICE"
                else:
                    point["options"][0]["label"] = "Change the public API without review"
                self.replace(altered, "substitution-" + change)
                self.assertEqual(self.state["assessment"]["actions"][0]["gate"], "DENY")
                with self.assertRaises(LedgerError) as caught:
                    self.permit("permit-" + change)
                self.assertEqual(caught.exception.code, "EDITOR_CONSTRAINT_CHANGED")
        self.assertFalse((self.root / ".verantyx/worktrees").exists())

    def test_unchanged_rehandoff_still_requires_pending_choice_then_executes_and_replays(self):
        self.rehandoff("unchanged-handoff")
        staged = stage_candidate(self.root, self.cfg, "work", key="unchanged-candidate",
                                 expected_revision=self.state["revision"])
        self.state = staged["state"]
        self.assertEqual(len(self.state["handoff_plans"]), 2)
        self.assertEqual(self.state["proposal"]["unknowns"], [self.harness.unknown])
        with self.assertRaises(LedgerError) as caught:
            self.permit("still-pending")
        self.assertEqual(caught.exception.code, "EDITOR_DECISION_REQUIRED")
        self.state = self.harness.decide(self.harness.point["id"], "preserve")["state"]
        with self.assertRaises(LedgerError) as caught:
            self.permit("choice-not-delivered")
        self.assertEqual(caught.exception.code, "EDITOR_DECISION_CHANGED")
        self.rehandoff("deliver-choice")
        self.state = stage_candidate(self.root, self.cfg, "work", key="decided-candidate",
                                     expected_revision=self.state["revision"])["state"]
        permission = self.permit("all-values-decided")
        result = execute(self.root, self.cfg, "work", permission["lease_id"],
                         os.environ["VERANTYX_PRECEDENT"], "execute-decided")
        self.assertEqual(result["execution"]["receipt"]["verification"]["closure"], "BOUNDED")
        self.assertEqual((self.root / "calc.py").read_text(), "def answer():\n    return 1\n")
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            events = store.events("work")
        expected = projection(replay(events))
        calls_before = self.harness.harness.fixture.calls.read_bytes()
        with mock.patch("subprocess.Popen", side_effect=AssertionError("replay launched a process")), \
             mock.patch("subprocess.run", side_effect=AssertionError("replay ran an external command")), \
             mock.patch("verantyx.application.now", side_effect=AssertionError("replay read the clock")):
            self.assertEqual(digest(projection(replay(events))), digest(expected))
        self.assertEqual(self.harness.harness.fixture.calls.read_bytes(), calls_before)
