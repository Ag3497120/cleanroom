"""Exercise the integrated v0.4 public commands in actual subprocesses."""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import unittest

from verantyx.commands_v04 import modules
from verantyx.domain.events import ACTORS
from verantyx.i18n import LANGUAGES, catalog

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get("VERANTYX_CROSS") and os.environ.get("VERANTYX_PRECEDENT"),
                     "Real Cross and Precedent paths are required")
class ExtendedWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temporary = tempfile.TemporaryDirectory(prefix="verantyx-v04-workflow-")
        cls.addClassCleanup(temporary.cleanup)
        cls.output = Path(temporary.name) / "demo"
        process = subprocess.run([sys.executable, str(ROOT / "examples/extended-workflow.py"),
            "--output", str(cls.output), "--cross", os.environ["VERANTYX_CROSS"],
            "--precedent", os.environ["VERANTYX_PRECEDENT"]], cwd=ROOT, capture_output=True,
            text=True, stdin=subprocess.DEVNULL, timeout=180)
        cls.report = json.loads((cls.output / "report.json").read_text())
        cls.commands = json.loads((cls.output / "commands.json").read_text())
        if process.returncode or not cls.report["passed"]:
            raise AssertionError(json.dumps({"stdout": process.stdout, "stderr": process.stderr,
                                             "report": cls.report}, ensure_ascii=False))

    def receipt(self, label):
        call = next(item for item in self.commands if item["label"] == label)
        return json.loads((self.output / call["receipt"]).read_text())

    def test_bounded_checks_leave_the_prose_claim_unknown(self):
        for method in ("TEST", "REPRODUCTION", "NEGATIVE_CONTROL"):
            result = self.receipt("verify-run-" + method)["result"]
            claim = result["state"]["assessment"]["claims"][0]
            self.assertEqual(claim["epistemic_status"], "UNKNOWN")
            self.assertEqual(claim["closure"], "UNKNOWN")
            self.assertEqual(claim["property_evidence"]["closure"], "BOUNDED")
            self.assertEqual(result["verification"]["receipt"]["result"]["closure"], "BOUNDED")
            self.assertTrue(any(gap["code"] == "CLAIM_NOT_VERIFIED" for gap in result["state"]["assessment"]["gaps"]))

    def test_finite_policy_reuses_only_covered_non_exempt_decisions(self):
        second = self.receipt("run-policy-second")["result"]["state"]["assessment"]
        self.assertEqual(second["judgments"][0]["status"], "PRECEDENT_MATCHED")
        self.assertIsNone(second["question"])
        for label in ("run-policy-exempt", "run-policy-outside"):
            self.assertIsNotNone(self.receipt(label)["result"]["state"]["assessment"]["question"])
        self.assertGreaterEqual(self.receipt("shadow-report")["result"]["distinct_tasks"], 2)

    def test_five_languages_cover_material_events_warnings_and_help(self):
        self.assertEqual({row["locale"] for row in self.report["locale_checks"]}, set(LANGUAGES))
        for locale in LANGUAGES:
            messages = catalog(locale)
            self.assertTrue(set("event." + event for event in ACTORS).issubset(messages))
            for module in modules():
                for command in module.COMMANDS:
                    self.assertIn(command, messages["commands"])
            for prefix in ("locale-events-", "warning-display-", "exercise-material-"):
                receipt = self.receipt(prefix + locale)
                self.assertTrue(receipt["stdout"])
                self.assertNotIn("Traceback", receipt["stderr"])

    def test_exercise_answers_are_bounded_and_material_excludes_rubrics(self):
        for locale in LANGUAGES:
            raw = json.dumps(self.receipt("material-json-" + locale)["result"])
            self.assertNotIn('"rubric"', raw)
            self.assertNotIn('"answers"', raw)
            result = self.receipt("exercise-answer-" + locale)["result"]
            exercise = next(row for row in result["candidates"] if row["id"] == "practice")["exercises"][0]
            self.assertEqual(exercise["assessments"][-1]["result"]["mastery_claim"], "NOT_ASSESSED")
            self.assertEqual(len(self.receipt("review-due-" + locale)["result"]["items"]), 1)

    def test_queued_real_process_is_not_called_again_during_recovery(self):
        self.assertEqual(self.receipt("worker")["result"]["processed"][0]["status"], "COMPLETED")
        for label in ("job-run", "job-recover"):
            self.assertTrue(self.receipt(label)["result"]["duplicate"])
        self.assertTrue(self.report["fixtures_only"])
        self.assertEqual(self.report["live_model_calls"], 0)
        self.assertTrue(all(row["passed"] for row in self.report["checks"]))
