"""Transport/authority regression contracts; no theme-specific classifier."""
from contextlib import redirect_stdout
from copy import deepcopy
from io import StringIO
from unittest import TestCase
from jsonschema import Draft202012Validator

from verantyx.agent_schema import WORK_REQUEST, REFLECTION_REQUEST, schema, native_contract, validate_output
from verantyx.errors import LedgerError
from verantyx.owner_notebook import show_receipt


class NativeContract(TestCase):
    def test_every_schema_node_has_explicit_type(self):
        def walk(node):
            self.assertIn("type", node)
            self.assertNotIn("const", node)
            self.assertNotIn("uniqueItems", node)
            for item in node.get("properties", {}).values():
                walk(item)
            if "items" in node:
                walk(node["items"])
        for kind in (WORK_REQUEST, REFLECTION_REQUEST):
            request, envelope = native_contract({"format": kind})
            walk(envelope)
            self.assertEqual(request["output_schema"], schema({"format": kind}))

    def test_transport_is_independent_of_task_theme(self):
        for kind in (WORK_REQUEST, REFLECTION_REQUEST):
            envelopes = [native_contract({"format": kind, "request": text})[1]
                         for text in ("mouth input", "terrain bicycle", "rhythm", "inventory")]
            self.assertTrue(all(value == envelopes[0] for value in envelopes))

    def test_local_bounds_and_duplicate_sources_remain_enforced(self):
        request = {"format": REFLECTION_REQUEST, "trace": {"events": [
            {"source_ref": "source-1", "type": "WorkTurnRecorded"}]}}
        item = {"kind": "REVIEW", "text": "A principle from the work", "reason": "A recorded tradeoff",
                "source_event_ids": ["source-1"], "minimum_model": "",
                "counterexample": "", "understanding_check": ""}
        valid = {"format": "verantyx.reflection-proposal.v1", "owner_items": [item]}
        self.assertEqual(validate_output(request, valid), valid)
        for invalid in (deepcopy(valid), deepcopy(valid)):
            if invalid == valid:
                invalid["owner_items"][0]["source_event_ids"] = ["source-1", "source-1"]
            with self.assertRaises(LedgerError):
                validate_output(request, invalid)
        oversized = deepcopy(valid)
        oversized["owner_items"][0]["text"] = "x" * 4001
        with self.assertRaises(LedgerError):
            validate_output(request, oversized)

    def test_no_unrecorded_human_decision(self):
        request = {"format": REFLECTION_REQUEST, "trace": {"events": [
            {"source_ref": "source-1", "type": "WorkTurnRecorded"}]}}
        proposal = {"format": "verantyx.reflection-proposal.v1", "owner_items": [{
            "kind": "HUMAN_DECISION", "text": "A claimed choice", "reason": "No human event",
            "source_event_ids": ["source-1"], "minimum_model": "",
            "counterexample": "", "understanding_check": ""}]}
        with self.assertRaises(LedgerError):
            validate_output(request, proposal)

    def test_failure_receipt_does_not_claim_an_answer_or_reflection_only_failure(self):
        state = {"request": "A test request", "work_result": {
            "status": "FAILED", "answer": "", "question": "", "artifacts": [],
            "reason": "BRIDGE_PROTOCOL"}}
        output = StringIO()
        with redirect_stdout(output):
            show_receipt(None, {"state": state, "reflection": {
                "status": "FAILED", "failure_code": "BRIDGE_PROTOCOL"}})
        text = output.getvalue()
        self.assertIn("BRIDGE_PROTOCOL", text)
        self.assertNotIn("回答を作業ノートへ保存しました", text)
        self.assertNotIn("ノートの意味整理だけ未完了", text)
        self.assertIn("回答・成果物はまだありません", text)

    def test_reflection_failure_preserves_a_real_work_answer(self):
        state = {"request": "A test request", "work_result": {
            "status": "SUCCEEDED", "answer": "Actual recorded answer", "question": "", "artifacts": [],
            "reason": ""}}
        output = StringIO()
        with redirect_stdout(output):
            show_receipt(None, {"state": state, "reflection": {
                "status": "FAILED", "failure_code": "REFLECTION_SOURCE_UNKNOWN"}})
        self.assertIn("Actual recorded answer", output.getvalue())
        self.assertIn("ノートの意味整理だけ未完了", output.getvalue())
