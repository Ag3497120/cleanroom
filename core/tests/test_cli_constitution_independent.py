"""Independent CLI negatives and real isolated runtime portability checks.

Artificial projects only. The adapter fixture returns deterministic JSON and
never contacts a model or network. Historical contracts and current automatic
applicability are tested separately from explicit operator selection.
"""
import base64
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

import test_asset_integration_v070 as asset_fixtures
from verantyx.adapters.precedent_backend import PrecedentBackend
from verantyx.domain.asset_workflow import compile_document, validate_payload
from verantyx.domain.codec import digest
from verantyx.errors import LedgerError
from verantyx.oracles import observe_candidate


@unittest.skipUnless(sys.platform == "darwin" and Path("/usr/bin/sandbox-exec").is_file(),
                     "requires the real macOS Seatbelt boundary")
class RuntimePortabilityTests(unittest.TestCase):
    def test_oracle_starts_current_python_and_denies_unselected_read_and_write(self):
        with tempfile.TemporaryDirectory(prefix="audit-oracle-private-") as temporary:
            private = Path(temporary).resolve()
            secret = private / "private.txt"
            secret.write_text("artificial-private-data")
            marker = private / "forbidden.txt"
            candidate = (
                "from pathlib import Path\n"
                "def answer(value):\n"
                "    denied = []\n"
                f"    try: Path({str(secret)!r}).read_text()\n"
                "    except PermissionError: denied.append('read')\n"
                f"    try: Path({str(marker)!r}).write_text('forbidden')\n"
                "    except PermissionError: denied.append('write')\n"
                "    return [value * 2, denied]\n"
            )
            spec = {"function": "answer", "cases": [{"id": "bounded", "input": 21}],
                    "timeout": 3, "max_output": 4096}
            observations = observe_candidate(candidate.encode(), spec)
            self.assertEqual(observations[0]["outcome"], "RETURNED", observations)
            self.assertEqual(observations[0]["returncode"], 0)
            frame = json.loads(base64.b64decode(observations[0]["stdout_base64"]))
            self.assertEqual(frame["value"], [42, ["read", "write"]])
            self.assertFalse(marker.exists())

    @unittest.skipUnless(os.environ.get("VERANTYX_PRECEDENT"), "set absolute VERANTYX_PRECEDENT")
    def test_frozen_unittest_starts_current_python_and_retains_isolation(self):
        with tempfile.TemporaryDirectory(prefix="audit-unittest-project-") as temporary, \
                tempfile.TemporaryDirectory(prefix="audit-unittest-private-") as outside:
            root = Path(temporary).resolve()
            secret = Path(outside).resolve() / "private.txt"
            secret.write_text("artificial-private-data")
            marker = root / "forbidden.txt"
            test = root / "test_frozen.py"
            test.write_text(
                "import unittest\nfrom pathlib import Path\n"
                "class Frozen(unittest.TestCase):\n"
                "    def test_finite_arithmetic_and_isolation(self):\n"
                "        self.assertEqual(21 * 2, 42)\n"
                "        with self.assertRaises(PermissionError):\n"
                f"            Path({str(secret)!r}).read_text()\n"
                "        with self.assertRaises(PermissionError):\n"
                f"            Path({str(marker)!r}).write_text('forbidden')\n"
            )
            backend = PrecedentBackend(os.environ["VERANTYX_PRECEDENT"])
            result = backend.module.run_tests(root, [test], timeout=5)
            self.assertTrue(result["passed"], result)
            self.assertEqual(result["exit"], 0)
            self.assertIn("Ran 1 test", result["output"])
            self.assertFalse(marker.exists())


class IndependentCliBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.h = asset_fixtures.AssetIntegrationTests()
        self.h.setUp()
        self.addCleanup(self.h.doCleanups)

    def test_explicit_model_free_reuse_preserves_failure_and_target_permission(self):
        first = self.h.ask("original", "old-result.json", "--auto-check")
        self.assertFalse(first["checks_ok"])
        self.h.ask("next", "new-result.json")
        asset = first["state"]["deltas"]["system_delta"]["verification_assets"][0]["id"]
        self.h.adapter.unlink()
        self.h.root.joinpath("normal.py").unlink()
        result = self.h.cli("asset-loop", "next", "--asset", asset, "--claim", "claim-property",
                            "--target", "new-result.json", "--key", "explicit")
        self.assertEqual(result["model_calls"], 0)
        self.assertEqual(result["workflow"]["status"], "COMPLETED")
        self.assertFalse(result["authority_granted"])
        self.assertEqual(result["state"]["effects"], {})
        self.h.root.joinpath("unselected.json").write_text('{"count":1}')
        refused = self.h.cli("asset-loop", "next", "--asset", asset, "--claim", "claim-property",
                             "--target", "unselected.json", "--key", "unselected", expected=2)
        self.assertEqual(refused["error"]["code"], "PATH_SCOPE")
        catalog = self.h.cli("dictionary")["catalog"]
        self.assertTrue(any(row["closure"] == "REFUTED" for row in catalog["failure_cases"]))
        self.assertTrue(all(row["authority"] == "REFERENCE_ONLY" for row in catalog["verification_methods"]))

    def test_dictionary_default_target_is_not_human_choice_or_mastery(self):
        first = self.h.ask("learning", "new-result.json", "--auto-check")
        candidate_id = next(iter(first["state"]["learning_candidates"]))
        catalog = self.h.cli("dictionary", "--run", "learning")["catalog"]
        before = next(row for row in catalog["learning"] if row["id"] == candidate_id)
        self.assertTrue(before["target_is_suggestion"])
        counts = self.h.cli("sovereignty")["human_selected_targets"]
        self.assertEqual(sum(counts.values()), 0)
        self.h.cli("learn-target", "learning", "--candidate", candidate_id, "--target", "DELEGATE",
                   "--reason", "Artificial voluntary delegation", "--key", "delegate")
        catalog = self.h.cli("dictionary", "--run", "learning")["catalog"]
        after = next(row for row in catalog["learning"] if row["id"] == candidate_id)
        self.assertFalse(after["target_is_suggestion"])
        self.assertEqual(after["ownership_target"], "DELEGATE")
        self.assertEqual(after["mastery_assessment"], "NOT_ASSESSED")
        self.assertEqual(catalog["rules"], [])
        measured = self.h.cli("sovereignty")
        self.assertEqual(measured["human_selected_targets"]["DELEGATE"], 1)
        self.assertFalse(measured["authority_granted"])

    def test_automatic_reuse_revalidates_changed_literal_requirement(self):
        first = self.h.ask("original", "new-result.json", "--auto-check")
        self.assertTrue(first["checks_ok"])
        failed = self.h.ask("original-failure", "old-result.json", "--auto-check")
        self.assertFalse(failed["checks_ok"])
        before = self.h.cli("dictionary")["catalog"]
        self.h.root.joinpath("requirements.json").write_text('{"expected":2}')
        changed = self.h.ask("changed", "new-result.json", "--auto-check")
        negative = self.h.ask("new-requirement-satisfied", "old-result.json", "--auto-check")
        # Neither the old success nor an output satisfying the new requirement
        # may be classified by the obsolete automatically selected expectation.
        for result in (changed, negative):
            self.assertFalse(result["checks_ok"])
            workflow = result["asset_workflow"]
            self.assertEqual(workflow["status"], "NO_PLAN")
            self.assertEqual(workflow["plan"]["steps"], [])
            self.assertEqual(result["state"].get("verifications", {}), {})
            self.assertEqual(workflow["plan"]["document"]["unresolved"], ["PLANNING_REJECTED"])
            self.assertTrue(workflow["plan"]["rejected"])
            self.assertTrue(all(row["reason"] == "EXPECTATION_LITERAL_MISMATCH"
                                for row in workflow["plan"]["rejected"]))
        after = self.h.cli("dictionary")["catalog"]
        for category in ("verification_methods", "failure_cases"):
            current = {row["id"]: row for row in after[category]}
            self.assertTrue(before[category])
            for original in before[category]:
                self.assertEqual(current[original["id"]], original)

    def test_automatic_reuse_binds_current_source_without_extra_planning_calls(self):
        first = self.h.ask("original", "new-result.json", "--auto-check")
        current_text = '{"note":"new source revision","expected":1}'
        self.h.root.joinpath("requirements.json").write_text(current_text)
        second = self.h.ask("current", "new-result.json", "--auto-check")
        self.assertTrue(second["checks_ok"])
        plan = second["asset_workflow"]["plan"]
        step = plan["steps"][0]
        self.assertEqual(step["mode"], "REUSE")
        self.assertEqual(step["current_requirement_binding_version"], 1)
        requirement = next(row for row in plan["context"]["selected_files"] if row["path"] == "requirements.json")
        binding = step["expectation_bindings"][0]
        self.assertEqual(binding["source_ref"], requirement["source_ref"])
        self.assertEqual(binding["source_sha256"], hashlib.sha256(current_text.encode()).hexdigest())
        self.assertEqual(binding["source_pointer"], "/expected")
        old_spec = first["asset_workflow"]["plan"]["steps"][0]["spec"]
        for field in ("checks", "negative_controls", "property", "method", "provenance"):
            self.assertEqual(step["spec"][field], old_spec[field])
        planning_calls = [row for row in self.h.invocations() if row["format"] == "verantyx.asset-workflow-request.v1"]
        self.assertEqual(len(planning_calls), 2)  # One each for compilation and reuse.
        tampered = deepcopy(plan)
        tampered["steps"][0]["expectation_bindings"][0]["source_sha256"] = "0" * 64
        with self.assertRaises(LedgerError):
            validate_payload("AssetWorkflowPlanned", tampered)
        forged_document = deepcopy(plan["document"])
        forged_document["steps"][0]["current_requirement_binding_version"] = 0
        with self.assertRaises(LedgerError):
            compile_document(plan["context"], forged_document, plan["max_checks"])
        # The host's stronger new binding must not rewrite markerless history.
        historical = deepcopy(plan)
        historical["steps"] = compile_document(plan["context"], plan["document"], plan["max_checks"],
                                                _legacy_reuse_bindings=True)
        self.assertNotIn("current_requirement_binding_version", historical["steps"][0])
        saved = deepcopy(historical)
        validate_payload("AssetWorkflowPlanned", historical)
        self.assertEqual(historical, saved)
        legacy_context = deepcopy(plan["context"])
        legacy_context["expectation_binding_version"] = 1
        legacy_document = deepcopy(plan["document"])
        legacy_document["context_sha256"] = digest(legacy_context)
        self.assertEqual(compile_document(legacy_context, legacy_document, plan["max_checks"]),
                         compile_document(legacy_context, legacy_document, plan["max_checks"],
                                          _legacy_reuse_bindings=True))

    def test_explicit_historical_contract_survives_changed_requirement_without_model(self):
        first = self.h.ask("original", "new-result.json", "--auto-check")
        asset = first["state"]["deltas"]["system_delta"]["verification_assets"][0]["id"]
        self.h.root.joinpath("requirements.json").write_text('{"expected":2}')
        self.h.ask("current", "new-result.json")
        self.h.adapter.unlink()
        self.h.root.joinpath("normal.py").unlink()
        result = self.h.cli("asset-loop", "current", "--asset", asset, "--claim", "claim-property",
                            "--target", "new-result.json", "--key", "explicit-historical")
        self.assertEqual(result["model_calls"], 0)
        self.assertEqual(result["selection"], "EXPLICIT_REUSE")
        self.assertEqual(result["workflow"]["status"], "COMPLETED")
        step = result["workflow"]["plan"]["steps"][0]
        self.assertEqual(step["spec"]["checks"], first["asset_workflow"]["plan"]["steps"][0]["spec"]["checks"])
        self.assertNotIn("current_requirement_binding_version", step)
        self.assertFalse(result["authority_granted"])


if __name__ == "__main__":
    unittest.main()
