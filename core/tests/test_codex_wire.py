"""Editor wire tests: deterministic data only, never call an external model."""
from copy import deepcopy
import unittest

from verantyx.codex_wire import editor_contract, plan_contract, validate_envelope
from verantyx.domain.codec import canonical, decode
from verantyx.errors import LedgerError


class CodexWireTests(unittest.TestCase):
    def setUp(self):
        from verantyx.shared_context import DISPOSITIONS, STRENGTHS
        self.value = {
            "format": "verantyx.editor-request.v1",
            "shared_context": {"sha256": "a" * 64},
            "interpretation_proposal": {"interpretations": [{"id": "intent-1"}],
                "cases": [{"id": "case-1", "choices": [{"id": "choice-A"}, {"id": "choice-B"}]}]},
            "response_template": {"plan_sha256": "b" * 64, "files": {}},
            "output_contract": "Original contract remains authoritative.",
        }
        self.envelope = {"document": {
            "context_sha256": "a" * 64, "plan_sha256": "b" * 64,
            "acknowledgements": [{"id": "intent-1", "disposition": list(DISPOSITIONS)[0],
                "strength": list(STRENGTHS)[0], "interpretation": "Artificial interpretation", "alternatives": []}],
            "relations": [], "case_choices": [{"id": "case-1", "choice": "choice-A", "reason": "Artificial reason"}],
            "files": [{"path": "settings.json", "content": '{"retry_limit":3,"enabled":true}\n'}],
            "tests": ["test_settings.py"], "notes": "Not executed or adopted.",
        }}
        self.wire_value, self.schema = editor_contract(self.value)

    def test_json_roundtrip_preserves_quotes_backslashes_unicode_and_physical_lines(self):
        body = 'def example():\r\n    return "Japanese: \\u65e5; literal \\\\n; quote \\""\r\n'
        self.envelope["document"]["files"][0]["content"] = body
        result = validate_envelope(decode(canonical(self.envelope)), self.schema)
        self.assertEqual(result["files"], {"settings.json": body})
        self.assertEqual(result["tests"], ["test_settings.py"])

    def test_wire_conversion_does_not_mutate_context_or_model_choices(self):
        self.assertEqual(self.value["response_template"]["files"], {})
        self.assertEqual(self.wire_value["response_template"]["files"], [])
        document = validate_envelope(self.envelope, self.schema)
        for key, value in self.envelope["document"].items():
            if key != "files":
                self.assertEqual(document[key], value)

    def test_duplicate_file_paths_are_rejected_without_overwrite(self):
        self.envelope["document"]["files"].append({"path": "settings.json", "content": "different"})
        with self.assertRaises(LedgerError):
            validate_envelope(self.envelope, self.schema)

    def test_wrong_context_and_authority_fields_fail_closed(self):
        for key, value in (("context_sha256", "c" * 64), ("approved", True)):
            altered = deepcopy(self.envelope)
            altered["document"][key] = value
            with self.assertRaises(LedgerError):
                validate_envelope(altered, self.schema)

    def test_nested_json_string_is_no_longer_editor_wire_format(self):
        with self.assertRaises(LedgerError):
            validate_envelope({"document": canonical(self.envelope["document"])}, self.schema)

    def test_every_schema_object_is_closed_and_all_fields_required(self):
        def visit(value):
            if type(value) is dict:
                if value.get("type") == "object":
                    self.assertIs(value["additionalProperties"], False)
                    self.assertEqual(set(value["required"]), set(value["properties"]))
                for item in value.values():
                    visit(item)
            elif type(value) is list:
                for item in value:
                    visit(item)
        visit(self.schema)

    def test_plan_uses_structured_object_without_rewriting_generated_semantics(self):
        from verantyx.shared_context import DISPOSITIONS, STRENGTHS
        request = {"format": "verantyx.handoff-plan-request.v1",
            "shared_context": {"sha256": "a" * 64,
                "sources": [{"id": "source-1", "text": 'Set "retry_limit" to 3.\n'}]},
            "output_contract": "Original plan contract."}
        before = deepcopy(request)
        wire, schema = plan_contract(request)
        document = {"context_sha256": "a" * 64,
            "interpretations": [{"id": "intent-1", "source_id": "source-1",
                "quote": 'Set "retry_limit" to 3.\n', "meaning": "Set the specified field to the required integer.",
                "disposition": list(DISPOSITIONS)[0], "strength": list(STRENGTHS)[0], "alternatives": []}],
            "relations": [], "cases": [{"id": "case-1", "situation": "Inspect proposed JSON.",
                "choices": [{"id": "choice-A", "text": "Field is integer 3."},
                            {"id": "choice-B", "text": "Field is unchanged."}],
                "expected": "choice-A", "interpretation_ids": ["intent-1"]}]}
        wire_document = deepcopy(document)
        wire_document["interpretations"][0].pop("quote")
        wire_document["interpretations"][0]["quote_ref"] = wire["citation_slots"][0]["quote_ref"]
        self.assertEqual(validate_envelope(decode(canonical({"document": wire_document})), schema,
                                           editor=False, source_request=request), document)
        self.assertEqual(request, before)
        self.assertIn("JSON OBJECT", wire["output_contract"])
        with self.assertRaises(LedgerError):
            validate_envelope({"document": canonical(document)}, schema, editor=False)


class CodexResponseWireTests(unittest.TestCase):
    def test_plan_citations_are_exact_and_cannot_cross_sources_or_repeat(self):
        from verantyx.coordination_schema import source_units
        request = {"format": "verantyx.handoff-plan-request.v1",
                   "shared_context": {"sha256": "a" * 64, "sources": [
                       {"id": "source-1", "text": 'Keep "original" fields, \\n literally, \\u65e5 and \u65e5\tremain.\r\n'},
                       {"id": "source-2", "text": "Change only the enabled flag.\n"}]},
                   "output_contract": "Uncertainty stays explicit."}
        wire, schema = plan_contract(request)
        units = source_units(request)
        document = {"context_sha256": "a" * 64, "relations": [], "interpretations": [
            {**unit, "meaning": "An attributed interpretation, not permission.",
             "disposition": "NOW", "strength": "MUST", "alternatives": []} for unit in units],
            "cases": [{"id": "case-1", "situation": "Keep unrelated data.",
                       "choices": [{"id": "choice-A", "text": "Keep it."},
                                   {"id": "choice-B", "text": "Discard it."}],
                       "expected": "choice-A", "interpretation_ids": [unit["id"] for unit in units]}]}
        self.assertEqual([{k: v for k, v in unit.items() if k != "quote_ref"}
                          for unit in wire["citation_slots"]], units)
        refs = {unit["id"]: unit["quote_ref"] for unit in wire["citation_slots"]}
        wire_document = deepcopy(document)
        for row in wire_document["interpretations"]:
            row.pop("quote")
            row["quote_ref"] = refs[row["id"]]
        before = deepcopy(wire_document)
        self.assertEqual(validate_envelope({"document": wire_document}, schema,
                                           editor=False, source_request=request), document)
        self.assertEqual(wire_document, before)

        # Reproduce the provider's restriction without calling the model:
        # no source whitespace may become a fixed enum string.
        def check_literals(node):
            if type(node) is dict:
                for literal in node.get("enum", []):
                    if type(literal) is str:
                        self.assertFalse(any(char in literal for char in "\r\n\t"))
                for child in node.values():
                    check_literals(child)
            elif type(node) is list:
                for child in node:
                    check_literals(child)
        check_literals(schema)

        for change in ("paraphrase", "source", "duplicate", "omitted", "reference", "authority"):
            bad = deepcopy(wire_document)
            if change == "paraphrase":
                bad["interpretations"][0]["quote"] = "Preserve the original fields."
            elif change == "source":
                bad["interpretations"][0]["source_id"] = "source-2"
            elif change == "duplicate":
                bad["interpretations"][1] = deepcopy(bad["interpretations"][0])
            elif change == "omitted":
                bad["interpretations"].pop()
            elif change == "reference":
                bad["interpretations"][0]["quote_ref"] = refs[units[1]["id"]]
            else:
                bad["approved"] = True
            with self.subTest(change=change), self.assertRaises(LedgerError):
                validate_envelope({"document": bad}, schema, editor=False, source_request=request)
        changed = deepcopy(request)
        changed["shared_context"]["sources"][0]["text"] += "Changed without updating the claimed context hash."
        for original in (None, changed):
            with self.subTest(original=original is None), self.assertRaises(LedgerError):
                validate_envelope({"document": wire_document}, schema, editor=False, source_request=original)

    def test_response_uses_native_object_and_preserves_skill_sources(self):
        from verantyx.codex_wire import response_contract
        from verantyx.responses import validate_response
        template = {"schema_version": 1, "task_id": "example-task", "basis_revision": 5,
                    "response_locale": "ja", "norms_sha256": "a" * 64, "answer": "Candidate only",
                    "explanations": [{"fact_id": "fact-1", "text": "Not executed"}],
                    "learning_candidates": [], "reusable_candidates": []}
        request = {"format": "verantyx.response-request.v1", "response_template": template,
                   "max_learning_items": 3, "allowed_source_refs": ["source-1"],
                   "output_contract": "Retain uncertainty."}
        before = deepcopy(request)
        _, schema = response_contract(request)
        document = deepcopy(template)
        document["learning_candidates"] = [{
            "concept_id": "retry-boundary", "concept": "Retry boundaries",
            "why_now": "A source discusses the limit", "minimum_model": "Count attempts separately",
            "counterexample": "A fourth attempt", "check": "Inspect the boundary",
            "source_refs": ["source-1"],
        }]
        decoded = validate_envelope({"document": document}, schema, editor=False)
        self.assertEqual(validate_response(decoded, request), document)
        self.assertEqual(request, before)
        for mutate in ("source", "authority", "string", "revision"):
            bad = deepcopy(document)
            if mutate == "source":
                bad["learning_candidates"][0]["source_refs"] = ["invented-source"]
            elif mutate == "authority":
                bad["execution_authorized"] = True
            elif mutate == "revision":
                bad["basis_revision"] += 1
            else:
                bad = canonical(bad)
            with self.subTest(mutate=mutate), self.assertRaises(LedgerError):
                validate_envelope({"document": bad}, schema, editor=False)
