"""Bounded delivery must not manufacture agreement or weaken other checks."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from verantyx.coordination import comparison_inputs
from verantyx.domain.codec import digest
from verantyx.judgment_compiler import compile_conditions
from verantyx.partner_delivery import delivery_authorization, deliver_artifact


def fixture():
    plan = {"interpretations": [{"id": "intent-1", "disposition": "NOW", "strength": "MUST",
                                "alternatives": ["missing value"]}],
            "relations": [], "cases": [{"id": "case-1", "expected": "A",
                                       "interpretation_ids": ["intent-1"]}]}
    packet = {"sha256": "context", "sources": []}
    document = {"context_sha256": "context", "plan_sha256": digest(plan),
                "acknowledgements": [{"id": "intent-1", "disposition": "NOW", "strength": "MUST",
                                      "alternatives": ["a different interpretation"]}],
                "relations": [], "case_choices": [{"id": "case-1", "choice": "A"}],
                "files": {"settings.json": '{"enabled":false}'}, "tests": []}
    state = {"revision": 17, "shared_context": packet, "handoff_plan": {"plan": plan},
             "editor_attempt": {"document": document, "validation": {
                 "status": "REPAIR_REQUIRED", "mode": "CROSS_VM", "fallback_reason": None,
                 "mismatch_ids": ["intent-1:alternatives"], "execution_authorized": False}}}
    return state


class ScopedDeliveryTest(unittest.TestCase):
    def test_default_is_still_blocked(self):
        self.assertFalse(delivery_authorization(fixture())["allowed"])

    def test_explicit_exception_does_not_rewrite_agreement(self):
        state = fixture()
        before = deepcopy(state)
        result = delivery_authorization(state, allow_contested_handoff=True)
        self.assertTrue(result["allowed"])
        self.assertEqual(result["status"], "REPAIR_REQUIRED")
        self.assertFalse(result["canonical_adoption_authorized"])
        self.assertEqual(result["semantic_fidelity"], "UNPROVEN")
        self.assertEqual(state, before)

    def test_other_mismatches_still_block(self):
        for field, value in (("disposition", "FORBIDDEN"), ("strength", "OPEN")):
            with self.subTest(field=field):
                state = fixture()
                state["editor_attempt"]["document"]["acknowledgements"][0][field] = value
                checks = comparison_inputs(state["shared_context"], state["handoff_plan"]["plan"],
                                           state["editor_attempt"]["document"])["checks"]
                state["editor_attempt"]["validation"]["mismatch_ids"] = [
                    row["id"] for row in checks if row["expected"] != row["actual"]]
                self.assertFalse(delivery_authorization(state, allow_contested_handoff=True)["allowed"])

    def test_case_or_dependency_disagreement_still_blocks(self):
        for field, value in (("case_choices", [{"id": "case-1", "choice": "B"}]),
                             ("relations", [{"kind": "DEPENDS_ON", "from": "intent-1", "to": "intent-1"}])):
            with self.subTest(field=field):
                state = fixture()
                state["editor_attempt"]["document"][field] = value
                self.assertFalse(delivery_authorization(state, allow_contested_handoff=True)["allowed"])

    def test_stale_or_unknown_validation_does_not_authorize(self):
        for change in ("context", "plan", "unknown", "fallback", "missing"):
            with self.subTest(change=change):
                state = fixture()
                if change == "context":
                    state["editor_attempt"]["document"]["context_sha256"] = "stale"
                elif change == "plan":
                    state["editor_attempt"]["document"]["plan_sha256"] = "stale"
                elif change == "unknown":
                    state["editor_attempt"]["validation"]["status"] = "UNKNOWN"
                elif change == "fallback":
                    state["editor_attempt"]["validation"]["fallback_reason"] = "VM_UNAVAILABLE"
                else:
                    state.pop("handoff_plan")
                self.assertFalse(delivery_authorization(state, allow_contested_handoff=True)["allowed"])

    def test_missing_expected_mismatch_is_not_accepted(self):
        state = fixture()
        state["editor_attempt"]["validation"]["mismatch_ids"] = []
        self.assertFalse(delivery_authorization(state, allow_contested_handoff=True)["allowed"])

    def test_delivery_keeps_conditions_and_negative_result(self):
        state = fixture()
        contract = compile_conditions("settings.json", ["JSON /enabled = false"])
        before = deepcopy(contract)
        with tempfile.TemporaryDirectory() as directory:
            original = Path(directory) / "settings.json"
            original.write_text('{"enabled":true}', encoding="utf-8")
            with patch("verantyx.authority.require_current_approval_valid"), patch(
                    "verantyx.partner_delivery.judge_target", return_value={
                        "status": "REFUTED", "canonical_code_adopted": False}) as judge:
                result = deliver_artifact(directory, {}, {"state": state, "run_id": "work-1"}, contract,
                                          key="job-1", reason="Explicit bounded inspection",
                                          allow_contested_handoff=True)
            self.assertEqual(result["status"], "REFUTED")
            self.assertEqual(original.read_text(encoding="utf-8"), '{"enabled":true}')
            self.assertEqual(judge.call_args.args[3]["spec"], before["spec"])
            self.assertEqual(contract, before)
            self.assertEqual(result["handoff"]["status"], "REPAIR_REQUIRED")
            self.assertTrue(Path(result["handoff_record"]).is_file())

    def test_multiple_files_do_not_expand_permission(self):
        state = fixture()
        state["editor_attempt"]["document"]["files"]["extra.json"] = "{}"
        contract = compile_conditions("settings.json", ["JSON /enabled = false"])
        with patch("verantyx.partner_delivery._write_files") as write:
            result = deliver_artifact("/unused", {}, {"state": state, "run_id": "work-1"}, contract,
                                      key="job-1", reason="Explicit bounded inspection",
                                      allow_contested_handoff=True)
        self.assertEqual(result["status"], "BLOCKED")
        write.assert_not_called()


if __name__ == "__main__":
    unittest.main()
