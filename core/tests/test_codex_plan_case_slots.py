"""Plan coverage is transport structure, never evidence of semantic agreement."""
from copy import deepcopy
import unittest

from verantyx.codex_wire import plan_contract, validate_envelope
from verantyx.errors import LedgerError


class PlanCaseSlotsTests(unittest.TestCase):
    def test_every_slot_reaches_a_generated_case_without_filling_model_choices(self):
        for count in (1, 3, 4):
            request = {"format": "verantyx.handoff-plan-request.v1",
                       "shared_context": {"sha256": "a" * 64, "sources": [
                           {"id": "source-1", "text": "".join("Requirement %s.\n" % i for i in range(count))}]},
                       "output_contract": "Preserve genuine uncertainty."}
            wire, schema = plan_contract(request)
            document = {"context_sha256": "a" * 64, "relations": [], "interpretations": [
                {"id": slot["id"], "source_id": slot["source_id"], "quote_ref": slot["quote_ref"],
                 "meaning": "Uncertain meaning from this artificial fixture.",
                 "disposition": "UNRESOLVED", "strength": "OPEN", "alternatives": ["Unconfirmed alternative"]}
                for slot in wire["citation_slots"]], "cases": [
                {**slot, "situation": "An artificial boundary.",
                 "choices": [{"id": "choice-A", "text": "Keep."}, {"id": "choice-B", "text": "Discard."}],
                 "expected": "choice-B"} for slot in wire["case_slots"]]}
            before = deepcopy(document)
            result = validate_envelope({"document": document}, schema, editor=False, source_request=request)
            self.assertEqual(document, before)
            self.assertEqual(result["cases"], document["cases"])
            self.assertTrue(all(row["disposition"] == "UNRESOLVED" for row in result["interpretations"]))
            self.assertEqual("".join(row["quote"] for row in result["interpretations"]),
                             request["shared_context"]["sources"][0]["text"])
            for change in ("missing_case", "missing_slot", "duplicate_case", "duplicate_slot", "wrong_case"):
                if count == 1 and change in ("duplicate_slot", "duplicate_case", "wrong_case"):
                    continue
                bad = deepcopy(document)
                if change == "missing_case":
                    bad["cases"].pop()
                elif change == "missing_slot":
                    bad["cases"][-1]["interpretation_ids"].pop()
                elif change == "duplicate_case":
                    bad["cases"][-1] = deepcopy(bad["cases"][0])
                elif change == "duplicate_slot":
                    bad["cases"][0]["interpretation_ids"][1] = bad["cases"][0]["interpretation_ids"][0]
                else:
                    bad["cases"][-1]["interpretation_ids"] = bad["cases"][0]["interpretation_ids"]
                with self.subTest(count=count, change=change), self.assertRaises(LedgerError):
                    validate_envelope({"document": bad}, schema, editor=False, source_request=request)
