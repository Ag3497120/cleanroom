"""Two role calls, no model-generated ceremony and no silent repair fan-out."""
import unittest
from unittest import mock

import test_shared_context as fixtures
from verantyx.domain.codec import canonical
from verantyx.errors import LedgerError
from verantyx.responses import ask


class EconomyWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.SharedContextTests()
        self.f.setUp()
        self.addCleanup(self.f.fixture.tearDown)

    def test_two_roles_instead_of_four_generation_calls(self):
        result = self.f.workflow(economy=True, max_repairs=0)
        calls = self.f.fixture.invocations()
        self.assertEqual([row["format"] for row in calls],
                         ["verantyx.handoff-plan-request.v1", "verantyx.editor-request.v1"])
        self.assertEqual(result["model_call_policy"]["max_role_calls"], 2)
        state = result["state"]
        self.assertEqual(state["latest_response"]["mode"], "FALLBACK")
        self.assertIsNone(state["latest_response"]["generator_error"])
        self.assertEqual(state["editor_attempt"]["validation"]["mode"], "CROSS_VM")
        self.assertEqual(state["editor_attempt"]["validation"]["status"], "MATCHED")
        self.assertEqual(state["effects"], {})
        self.assertEqual(state["human_decisions"], {})
        self.assertEqual((self.f.root / "calc.py").read_text(), "def answer():\n    return 1\n")

    def test_duplicate_economy_workflow_has_zero_additional_calls(self):
        verification, implementation = self.f.adapters()
        kwargs = dict(request="Connect first; independence is deferred.", adapter_path=verification,
                      editor_adapter=implementation, include_paths=["calc.py", "test_calc.py"],
                      key="economy-repeat", run_id="economy-repeat", economy=True, max_repairs=0)
        first = ask(self.f.root, self.f.cfg, **kwargs)
        second = ask(self.f.root, self.f.cfg, **kwargs)
        self.assertEqual(len(self.f.fixture.invocations()), 2)
        self.assertEqual(first["projection_hash"], second["projection_hash"])
        self.assertEqual(second["state"]["effects"], {})
        with self.assertRaises(LedgerError) as caught:
            ask(self.f.root, self.f.cfg, **{**kwargs, "economy": False})
        self.assertEqual(caught.exception.code, "IDEMPOTENCY_CONFLICT")
        self.assertEqual(len(self.f.fixture.invocations()), 2)

    def test_economy_rejects_implicit_repair_or_model_check_expansion(self):
        verification, implementation = self.f.adapters()
        base = dict(request="Work", adapter_path=verification, editor_adapter=implementation,
                    key="invalid", economy=True, max_repairs=0)
        for extra in ({"max_repairs": 1}, {"auto_check": True}, {"editor_adapter": None}):
            with self.subTest(extra=extra), self.assertRaises(LedgerError) as caught:
                ask(self.f.root, self.f.cfg, **{**base, **extra})
            self.assertEqual(caught.exception.code, "ARGUMENTS")
        self.assertEqual(self.f.fixture.invocations(), [])

    def test_disagreement_is_retained_without_an_extra_model_call(self):
        result = self.f.workflow("d['relations']=[]", economy=True, max_repairs=0)
        state = result["state"]
        self.assertEqual(len(self.f.fixture.invocations()), 2)
        self.assertEqual(state["editor_attempt"]["validation"]["status"], "REPAIR_REQUIRED")
        self.assertEqual(state["effects"], {})
        self.assertTrue(state["deltas"]["system_delta"]["failure_assets"])
        self.assertNotIn("human_decisions", canonical(result["model_call_policy"]))


if __name__ == "__main__":
    unittest.main()
