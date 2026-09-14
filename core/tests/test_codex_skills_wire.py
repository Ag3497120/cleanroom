"""Native skills proposal transport is reference-only and preserves provenance."""
import copy
import unittest

from verantyx.codex_wire import is_skill_proposal, skill_proposal_contract, validate_envelope
from verantyx.errors import LedgerError
from verantyx.personal_skills import REQUEST


class CodexSkillProposalWireTests(unittest.TestCase):
    def test_reference_only_native_document(self):
        document = {
            "schema_version": 1, "task_id": "task-1", "context_revision": 5,
            "response_locale": "ja", "summary": "Retain the explicit retry bound.",
            "claims": [{"id": "claim-1", "statement": "The source specifies a bound.",
                        "source_refs": ["source-1"]}],
            "actions": [],
            "unknowns": [{"id": "unknown-1", "question": "Was the bound tested?",
                          "needed_observation": "An actual execution receipt."}],
        }
        value = {
            "format": "verantyx.proposal-request.v1",
            "task": {"request": REQUEST},
            "selected_files": [],
            "observations": [{"source_ref": "source-1"}],
            "proposal_template": copy.deepcopy(document),
            "output_contract": "Return a proposal.",
        }
        before = copy.deepcopy(value)
        request, schema = skill_proposal_contract(value)
        self.assertEqual(value, before)
        self.assertIn("JSON OBJECT", request["output_contract"])
        self.assertEqual(validate_envelope({"document": document}, schema, editor=False), document)
        for field, replacement in (
            ("actions", [{}]),
            ("claims", [{"id": "claim-1", "statement": "Invented.",
                         "source_refs": ["invented-source"]}]),
        ):
            bad = copy.deepcopy(document)
            bad[field] = replacement
            with self.subTest(field=field), self.assertRaises(LedgerError):
                validate_envelope({"document": bad}, schema, editor=False)
        value["selected_files"] = [{"path": "code.py"}]
        self.assertFalse(is_skill_proposal(value))
