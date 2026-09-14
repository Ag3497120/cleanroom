"""Small closed-loop checks for explicit condition compilation and durable reuse."""
import tempfile
import unittest
from pathlib import Path

from verantyx.domain.verification import evidence_result
from verantyx.errors import LedgerError
from verantyx.judgment_compiler import compile_conditions


class ExplicitConditionTests(unittest.TestCase):
    def test_typed_value_is_not_inferred_from_output(self):
        contract = compile_conditions("settings.json", ["JSON /enabled = false", "JSON /retry_limit は 3"])
        self.assertEqual(evidence_result({"spec": contract["spec"]},
                         b'{"enabled":false,"retry_limit":3}')["closure"], "BOUNDED")
        self.assertEqual(evidence_result({"spec": contract["spec"]},
                         b'{"enabled":false,"retry_limit":"3"}')["closure"], "REFUTED")
        self.assertEqual(evidence_result({"spec": contract["spec"]},
                         b'{"enabled":true,"retry_limit":3}')["closure"], "REFUTED")

    def test_explicit_negative_control_is_preserved(self):
        contract = compile_conditions("settings.json", ["JSON /retry_limit = 3"],
                                      ['{"retry_limit":4}'])
        outcome = evidence_result({"spec": contract["spec"]}, b'{"retry_limit":3}')
        self.assertEqual(outcome["closure"], "BOUNDED")
        self.assertTrue(outcome["negative_controls"][0]["rejected"])

    def test_bad_negative_control_cannot_prove_success(self):
        contract = compile_conditions("settings.json", ["JSON /retry_limit = 3"],
                                      ['{"retry_limit":3}'])
        self.assertEqual(evidence_result({"spec": contract["spec"]},
                         b'{"retry_limit":3}')["closure"], "CONTESTED")

    def test_ambiguous_prose_and_conflicts_are_not_compiled(self):
        for lines in (["Make retries safe"], ["JSON /x = 1", "JSON /x = 2"],
                      ["JSON /x = NaN"], ["JSON /x = {\"a\":1,\"a\":2}"]):
            with self.subTest(lines=lines), self.assertRaises(LedgerError):
                compile_conditions("settings.json", lines)

    def test_root_and_type_predicates(self):
        contract = compile_conditions("settings.json", ["JSON $ type object", "JSON /n type integer"])
        self.assertEqual(evidence_result({"spec": contract["spec"]}, b'{"n":1}')["closure"], "BOUNDED")
        self.assertEqual(evidence_result({"spec": contract["spec"]}, b'{"n":true}')["closure"], "REFUTED")

    def test_unknown_path_is_not_an_authorization(self):
        for target in ("../settings.json", "/tmp/settings.json", ".verantyx/private.json"):
            with self.subTest(target=target), self.assertRaises(LedgerError):
                compile_conditions(target, ["JSON $ = {}"])


if __name__ == "__main__":
    unittest.main()
