"""A separate editor must not erase the human choices behind its candidate."""
from copy import deepcopy
from pathlib import Path
from unittest import mock
import json
import os
import subprocess
import unittest

import test_shared_context as shared
from verantyx.application import dispatch, record_run
from verantyx.cli import parse
from verantyx.coordination import candidate_proposal, coordinate, stage_candidate
from verantyx.domain.effects import editor_binding
from verantyx.effects import authorize, execute
from verantyx.errors import LedgerError
from verantyx.responses import ask
from verantyx.storage.sqlite import EventStore


class CandidateDecisionTests(unittest.TestCase):
    def setUp(self):
        self.harness = shared.SharedContextTests()
        self.harness.setUp()
        self.addCleanup(self.harness.doCleanups)
        self.root, self.cfg = self.harness.root, self.harness.cfg
        self.point = {"id": "api-policy", "kind": "VALUE_DECISION", "decision_type": "api_compatibility",
                      "question": "Preserve the public API or change it?", "options": [
                          {"id": "preserve", "label": "Preserve the API"}, {"id": "break", "label": "Change the API"}]}
        self.unknown = {"id": "future-benchmark", "question": "What is the cost on a future dataset?",
                        "needed_observation": "Measure it when that dataset is available."}
        self.claim = {"id": "performance", "statement": "This may improve performance.", "source_refs": []}

    def workflow(self, *, extra_points=(), claims=None):
        vera, editor = self.harness.adapters()
        self.original = {"decision_points": [deepcopy(self.point), *deepcopy(extra_points)],
                         "unknowns": [deepcopy(self.unknown)], "claims": [deepcopy(self.claim)] if claims is None else claims}
        script = self.root / "vera.py"
        body = script.read_text()
        body = body.replace("d['summary']='A proposal, not an execution.'",
                            "d['summary']='A proposal, not an execution.'; d.update(" + repr(self.original) + ")")
        script.write_text(body)
        result = ask(self.root, self.cfg, request="Propose the calculator change while preserving the pending API decision.",
                     adapter_path=vera, editor_adapter=editor, include_paths=["calc.py", "test_calc.py"],
                     key="work", run_id="work", context={"component": "calculator", "workload": "fixture", "risk": "LOW"})
        for args in (["init", "-q"], ["add", "calc.py", "test_calc.py"],
                     ["-c", "user.name=Artificial fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "Frozen tests"]):
            subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True)
        return result

    def decide(self, point, choice):
        _, args = parse(["decide", "work", "--point", point, "--choice", choice,
                         "--reason", "Artificial test decision; not user approval", "--key", "choice-" + point])
        return dispatch(self.root, self.cfg, args, "ja")

    def test_candidate_preserves_original_decisions_unknowns_and_claims(self):
        state = self.workflow()["state"]
        proposal = state["proposal"]
        self.assertIn(self.point, proposal["decision_points"])
        self.assertEqual(proposal["unknowns"], self.original["unknowns"])
        self.assertEqual(proposal["claims"], self.original["claims"])
        self.assertEqual(state["assessment"]["question"]["point_id"], self.point["id"])
        self.assertIn(self.point["id"], state["assessment"]["actions"][0]["unresolved_decision_dependencies"])

    def test_isolation_choice_alone_cannot_authorize_the_editor(self):
        state = self.workflow()["state"]
        action = state["proposal"]["actions"][0]
        self.decide(action["arguments"]["point_id"], "isolate")
        with self.assertRaises(LedgerError) as error:
            authorize(self.root, self.cfg, "work", action["id"], os.environ["VERANTYX_PRECEDENT"], "permit")
        self.assertEqual(error.exception.code, "EDITOR_DECISION_REQUIRED")
        self.assertFalse((self.root / ".verantyx/worktrees").exists())

    def test_unrelated_unknown_is_retained_without_blocking_the_bounded_test(self):
        state = self.workflow()["state"]
        action = state["proposal"]["actions"][0]
        self.decide(action["arguments"]["point_id"], "isolate")
        decided = self.decide(self.point["id"], "preserve")
        # The selected policy must reach the editor before its code is used.
        refreshed = coordinate(self.root, self.cfg, "work", proposer_adapter=self.root / "vera.json",
                               editor_adapter=self.root / "editor.json", key="decided-handoff",
                               expected_revision=decided["recorded_revision"], include_paths=["calc.py", "test_calc.py"])
        stage_candidate(self.root, self.cfg, "work", key="decided-candidate", expected_revision=refreshed["recorded_revision"])
        permission = authorize(self.root, self.cfg, "work", action["id"], os.environ["VERANTYX_PRECEDENT"], "permit")
        result = execute(self.root, self.cfg, "work", permission["lease_id"], os.environ["VERANTYX_PRECEDENT"], "execute")
        self.assertEqual(result["execution"]["receipt"]["verification"]["closure"], "BOUNDED")
        self.assertEqual(result["state"]["proposal"]["unknowns"], [self.unknown])
        self.assertIn("MODEL_UNKNOWN", {gap["code"] for gap in result["state"]["assessment"]["gaps"]})
        self.assertEqual((self.root / "calc.py").read_text(), "def answer():\n    return 1\n")

    def test_resume_cannot_strip_or_change_the_frozen_source_constraints(self):
        state = self.workflow()["state"]
        for field in ("decision_points", "unknowns", "claims"):
            for operation in ("drop", "change"):
                with self.subTest(field=field, operation=operation):
                    altered = deepcopy(state)
                    if operation == "drop":
                        altered["proposal"][field] = []
                    else:
                        key = {"decision_points": "question", "unknowns": "question", "claims": "statement"}[field]
                        altered["proposal"][field][0][key] = "Substituted meaning"
                    with self.assertRaises(LedgerError):
                        editor_binding(altered, altered["proposal"]["actions"][0])

    def test_existing_isolation_point_is_retained_and_reused(self):
        point = {"id": "existing-isolation", "kind": "VALUE_DECISION", "decision_type": "parallel_writers",
                 "question": "Keep writer workspaces separate?", "options": [
                     {"id": "isolate", "label": "Isolate writers"}, {"id": "share", "label": "Share the working tree"}]}
        state = self.workflow(extra_points=[point])["state"]
        self.assertEqual(state["proposal"]["actions"][0]["arguments"]["point_id"], "existing-isolation")
        self.assertEqual(state["proposal"]["decision_points"], [self.point, point])

    def test_reserved_ids_do_not_overwrite_original_items(self):
        self.point["id"] = "editor-isolation"
        self.claim["id"] = "editor-apply"
        state = self.workflow()["state"]
        self.assertIn(self.point, state["proposal"]["decision_points"])
        self.assertIn(self.claim, state["proposal"]["claims"])
        identifiers = [item["id"] for group in ("decision_points", "claims", "unknowns", "actions") for item in state["proposal"][group]]
        self.assertEqual(len(identifiers), len(set(identifiers)))

    def test_replay_gate_also_rejects_authorization_without_the_api_decision(self):
        state = self.workflow()["state"]
        action = state["proposal"]["actions"][0]
        self.decide(action["arguments"]["point_id"], "isolate")
        def only_isolation(store, value, plan, clock, backend):
            from verantyx.governance import policy_context
            return policy_context(store.events(), value, backend)
        with mock.patch("verantyx.effects._gate", side_effect=only_isolation), self.assertRaises(LedgerError):
            authorize(self.root, self.cfg, "work", action["id"], os.environ["VERANTYX_PRECEDENT"], "forged-permission")

    def test_isolation_does_not_silently_remove_a_decision_at_the_size_limit(self):
        state = self.workflow()["state"]
        source = state["handoff_plan"]["source_proposal"]
        source["decision_points"] = [{**deepcopy(self.point), "id": "value-" + str(i)} for i in range(16)]
        with self.assertRaises(LedgerError) as error:
            candidate_proposal(state)
        self.assertEqual(error.exception.code, "EDITOR_DECISION_LIMIT")
        self.assertEqual(len(source["decision_points"]), 16)

    def test_pending_choice_is_classified_as_human_decision_not_missing_evidence(self):
        state = self.workflow()["state"]
        gap = next(item for item in state["assessment"]["gaps"] if item["code"] == "EDITOR_DECISION_REQUIRED")
        self.assertEqual(gap["blocker"], "HUMAN_DECISION_MISSING")
        self.assertEqual(gap["epistemic_status"], "UNKNOWN")

    def test_repeated_handoff_cannot_reset_the_original_constraints(self):
        state = self.workflow()["state"]
        action = state["proposal"]["actions"][0]
        state = self.decide(action["arguments"]["point_id"], "isolate")["state"]
        replacement = deepcopy(state["proposal"])
        replacement["context_revision"] = state["revision"]
        replacement["decision_points"] = [p for p in replacement["decision_points"] if p["id"] != self.point["id"]]
        replacement["unknowns"], replacement["claims"] = [], []
        path = self.root / "replacement.json"
        path.write_text(json.dumps(replacement))
        replaced = record_run(self.root, self.cfg, run_id="work", resume=True, proposal_path=path,
                              expected_revision=state["revision"], key="replacement")
        with self.assertRaises(LedgerError) as error:
            coordinate(self.root, self.cfg, "work", proposer_adapter=self.root / "vera.json",
                       editor_adapter=self.root / "editor.json", key="second-handoff",
                       expected_revision=replaced["state"]["revision"], include_paths=["calc.py", "test_calc.py"])
        self.assertEqual(error.exception.code, "EDITOR_CONSTRAINT_CHANGED")
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            self.assertEqual(sum(e["type"] == "HandoffPlanned" for e in store.events()), 1)
            self.assertFalse(any(e["type"] == "EffectAuthorized" for e in store.events()))

    def test_repeated_handoff_with_preserved_constraints_still_works(self):
        state = self.workflow()["state"]
        result = coordinate(self.root, self.cfg, "work", proposer_adapter=self.root / "vera.json",
                            editor_adapter=self.root / "editor.json", key="second-handoff",
                            expected_revision=state["revision"], include_paths=["calc.py", "test_calc.py"])
        result = stage_candidate(self.root, self.cfg, "work", key="second-candidate",
                                 expected_revision=result["state"]["revision"])
        self.assertEqual(len(result["state"]["handoff_plans"]), 2)
        self.assertIn(self.point, result["state"]["proposal"]["decision_points"])
        self.assertIn(self.point["id"], result["state"]["assessment"]["actions"][0]["unresolved_decision_dependencies"])
