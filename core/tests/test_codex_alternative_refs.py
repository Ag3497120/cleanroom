"""Explicit references preserve selected alternatives, never invent consensus."""
from copy import deepcopy
import unittest

from verantyx.codex_wire import editor_contract, validate_envelope
from verantyx.errors import LedgerError


class AlternativeReferenceTests(unittest.TestCase):
    def setUp(self):
        self.request = {"format": "verantyx.editor-request.v1", "shared_context": {"sha256": "a" * 64},
                        "interpretation_proposal": {"interpretations": [
                            {"id": "intent-1", "alternatives": ["An existing reading.\n", "Another reading."]},
                            {"id": "intent-2", "alternatives": ["A separate source reading."]}],
                            "cases": [{"id": "case-1", "choices": [{"id": "choice-A"}, {"id": "choice-B"}]}]},
                        "response_template": {"plan_sha256": "b" * 64, "files": {}}, "output_contract": ""}
        self.wire, self.schema = editor_contract(self.request)
        self.ref = self.wire["alternative_slots"][0]["ref"]
        self.envelope = {"document": {"context_sha256": "a" * 64, "plan_sha256": "b" * 64,
            "acknowledgements": [{"id": "intent-1", "disposition": "UNRESOLVED", "strength": "OPEN",
                "interpretation": "An unresolved, independently generated interpretation.",
                "alternative_refs": [self.ref], "alternatives": ["A newly proposed reading."]}],
            "relations": [], "case_choices": [{"id": "case-1", "choice": "UNRESOLVED", "reason": "Not decided."}],
            "files": [], "tests": [], "notes": "Not adopted."}}

    def test_selected_and_new_readings_survive_without_filling_missing_acknowledgements(self):
        before = deepcopy(self.envelope)
        result = validate_envelope(self.envelope, self.schema, source_request=self.request)
        self.assertEqual(self.envelope, before)
        self.assertEqual(result["acknowledgements"][0]["alternatives"],
                         ["An existing reading.\n", "A newly proposed reading."])
        self.assertEqual(result["acknowledgements"][0]["disposition"], "UNRESOLVED")
        self.assertEqual(len(result["acknowledgements"]), 1)
        self.assertEqual(result["case_choices"][0]["choice"], "UNRESOLVED")

    def test_rejection_of_all_existing_readings_stays_rejected(self):
        self.envelope["document"]["acknowledgements"][0]["alternative_refs"] = []
        result = validate_envelope(self.envelope, self.schema, source_request=self.request)
        self.assertEqual(result["acknowledgements"][0]["alternatives"], ["A newly proposed reading."])

    def test_unknown_cross_source_duplicate_and_excess_references_are_rejected(self):
        for change in ("unknown", "cross_source", "duplicate", "excess", "authority"):
            bad = deepcopy(self.envelope)
            row = bad["document"]["acknowledgements"][0]
            if change == "unknown":
                row["alternative_refs"] = ["invented"]
            elif change == "cross_source":
                row["alternative_refs"] = [self.wire["alternative_slots"][-1]["ref"]]
            elif change == "duplicate":
                row["alternative_refs"] = [self.ref, self.ref]
            elif change == "excess":
                row["alternatives"] = ["Additional reading"] * 8
            else:
                bad["document"]["authorized"] = True
            with self.subTest(change=change), self.assertRaises(LedgerError):
                validate_envelope(bad, self.schema, source_request=self.request)

    def test_original_request_is_required_and_bound_to_reference_text(self):
        changed = deepcopy(self.request)
        changed["interpretation_proposal"]["interpretations"][0]["alternatives"][0] = "Different bytes."
        for request in (None, changed):
            with self.assertRaises(LedgerError):
                validate_envelope(self.envelope, self.schema, source_request=request)
