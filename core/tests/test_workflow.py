"""One actual CLI demonstration, inspected as a later handoff would inspect it."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest

from verantyx.commands_v03 import COMMANDS

ROOT = Path(__file__).resolve().parents[1]
CROSS = os.environ.get("VERANTYX_CROSS")
PRECEDENT = os.environ.get("VERANTYX_PRECEDENT")
VERA_SOURCE = Path(os.environ.get("VERANTYX_VERA_SOURCE", str(Path(__file__).resolve().parents[2] / "dependencies/call-me-vera")))
VERA_PYTHON = Path(os.environ.get("VERANTYX_VERA_PYTHON", str(VERA_SOURCE / ".venv/bin/python")))


@unittest.skipUnless(CROSS and PRECEDENT, "Set VERANTYX_CROSS and VERANTYX_PRECEDENT for the actual CLI workflow")
class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="verantyx-workflow-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.output = Path(cls.temporary.name).resolve() / "demo"
        cls.argv = [sys.executable, str(ROOT / "examples/end-to-end.py"), "--output", str(cls.output),
                    "--cross", CROSS, "--precedent", PRECEDENT]
        cls.memory_available = VERA_SOURCE.is_dir() and VERA_PYTHON.is_file()
        if cls.memory_available:
            cls.argv.extend(["--vera-source", str(VERA_SOURCE), "--vera-python", str(VERA_PYTHON)])
        else:
            cls.argv.append("--skip-memory")
        cls.environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        process = subprocess.run(cls.argv, cwd=ROOT, env=cls.environment, stdin=subprocess.DEVNULL,
                                 capture_output=True, text=True, timeout=180)
        report_path = cls.output / "report.json"
        cls.report = json.loads(report_path.read_text()) if report_path.is_file() else {}
        if process.returncode != 0 or not cls.report.get("passed"):
            receipts = sorted((cls.output / "receipts").glob("*.json"))
            last = receipts[-1].read_text()[:4000] if receipts else "no receipts"
            raise AssertionError(json.dumps({"returncode": process.returncode, "stdout": process.stdout,
                "stderr": process.stderr, "error": cls.report.get("error"), "last_receipt": last}, ensure_ascii=False))
        cls.commands = json.loads((cls.output / "commands.json").read_text())
        cls.project = cls.output / "project"

    def receipt(self, label):
        command = next(item for item in self.commands if item["label"] == label)
        return json.loads((self.output / command["receipt"]).read_text())

    def git(self, *arguments):
        return subprocess.run(["git", "-C", str(self.project), "-c", "core.hooksPath=/dev/null",
                               "-c", "core.fsmonitor=false", *arguments], check=True,
                              capture_output=True, env=self.environment, timeout=30).stdout

    def test_real_cli_connects_every_required_stage_with_artificial_provenance(self):
        self.assertTrue(self.report["fixtures_only"])
        self.assertEqual(self.report["live_model_calls"], 0)
        self.assertEqual(self.report["human_decisions"], "SCRIPTED_ARTIFICIAL_FIXTURE_NOT_USER_APPROVAL")
        labels = {item["label"] for item in self.commands}
        self.assertTrue({"setup", "run-decision", "propose-decision", "human-decision", "precedent-accept", "rule-draft",
                         "rule-shadow", "rule-confirm", "rule-activate", "run-candidate", "propose-candidate",
                         "authorize-candidate", "raise-candidate", "learning-collect", "learning-target", "learning-defer",
                         "learning-resume", "learning-explain", "learning-counterexample", "learning-apply", "learning-transfer",
                         "execute-candidate", "adoption-propose", "adoption-review", "adoption-authorize", "adopt", "learn",
                         "handoff-packet"}.issubset(labels))
        first = self.receipt("propose-decision")["result"]
        second = self.receipt("propose-candidate")["result"]
        self.assertIsNotNone(first["state"]["assessment"]["question"])
        self.assertIsNone(second["state"]["assessment"]["question"])
        self.assertEqual(second["state"]["assessment"]["judgments"][0]["status"], "PRECEDENT_MATCHED")
        self.assertNotEqual(first["executor_sha256"], second["executor_sha256"])
        input_files = json.loads((self.output / "adapter-inputs/candidate.json").read_text())["selected_files"]
        self.assertEqual([item["path"] for item in input_files], ["calc.py"])
        self.assertTrue(all(item["passed"] for item in self.report["checks"]))

    def test_actual_git_adoption_preserves_uncommitted_work_and_staged_index(self):
        self.assertEqual(self.report["execution"]["status"], "CANDIDATE_TESTED")
        self.assertEqual(self.report["adoption"]["outcome"], "ADOPTED")
        self.assertEqual(self.git("show", "verantyx/canonical:calc.py"), b"def add(a, b):\n    return a + b\n")
        self.assertEqual(self.git("show", "verantyx/canonical:notes.txt"), b"committed baseline\n")
        self.assertEqual(self.git("show", ":notes.txt"), b"artificial staged unfinished work\n")
        self.assertEqual((self.project / "notes.txt").read_text(), "artificial staged and unstaged unfinished work\n")
        self.assertEqual((self.project / "scratch.txt").read_text(), "untracked unfinished work\n")
        self.assertIn("ARTIFICIAL_PRIVATE_FILE_DO_NOT_EXPORT", (self.project / "calc.py").read_text())
        self.assertEqual(self.git("rev-parse", "HEAD").decode().strip(), self.report["preservation"]["head"])
        self.assertEqual(hashlib.sha256((self.project / ".git/index").read_bytes()).hexdigest(),
                         self.report["preservation"]["index_sha256"])
        adoption = self.receipt("adopt")["result"]["adoption"]
        self.assertEqual(self.git("rev-parse", "verantyx/canonical").decode().strip(), adoption["receipt"]["commit"])

    def test_intervening_nonlearning_changes_are_not_hidden_by_later_learning(self):
        denied = self.receipt("execute-stale")
        self.assertEqual(denied["returncode"], 4)
        effect = denied["result"]["execution"]
        self.assertEqual((effect["status"], effect["reason"]), ("INVALIDATED", "CONTEXT_CHANGED"))
        self.assertFalse(Path(effect["lease"]["resource_scope"]).exists())
        before_approval = self.receipt("adopt-without-permission")
        self.assertEqual(before_approval["result"]["error"]["code"], "ADOPTION_STAGE")
        self.assertEqual(before_approval["returncode"], 2)

    def test_saved_learning_is_explicit_self_report_with_citations(self):
        learned = self.receipt("learn")["result"]
        candidate = next(item for item in learned["candidates"] if item["id"] == self.report["learning"]["id"])
        self.assertEqual(candidate["cycle"], 2)
        self.assertEqual(candidate["ownership_target"], "REVIEW")
        self.assertFalse(candidate["target_is_suggestion"])
        self.assertEqual(candidate["submission_state"], "TRANSFERRED")
        self.assertEqual(candidate["mastery_evidence"], "SELF_REPORTED")
        self.assertEqual(candidate["mastery_assessment"], "NOT_ASSESSED")
        self.assertIsNone(candidate["assessment"])
        self.assertFalse(candidate["externally_verified"])
        self.assertEqual({entry["kind"] for entry in candidate["evidence"]}, {
            "SelfExplanationSubmitted", "CounterexampleIdentified", "AppliedInProject", "TransferredToNewProblem"})
        for evidence in candidate["evidence"]:
            self.assertTrue(evidence["source_refs"])
            self.assertEqual(evidence["evidence_basis"], "SELF_REPORT")
            self.assertFalse(evidence["externally_verified"])

    def test_all_new_cli_commands_have_localized_error_paths_in_five_languages(self):
        checks = self.report["locale_checks"]
        self.assertEqual({item["locale"] for item in checks}, {"en", "ja", "zh-Hans", "ko", "es"})
        for item in checks:
            self.assertTrue(item["passed"])
            self.assertEqual(set(item["argument_errors"]), COMMANDS)
            self.assertTrue(item["json_success"])
            locale = item["locale"]
            for code, prefix in (("LEARNING_NOT_FOUND", "locale-learning-error-"),
                                 ("ADOPTION_STAGE", "locale-adoption-error-"),
                                 ("MEMORY_NAME_REQUIRED", "locale-memory-error-")):
                receipt = self.receipt(prefix + locale)
                self.assertEqual(receipt["result"]["error"]["code"], code)
                self.assertTrue(receipt["result"]["error"]["message"])
                self.assertNotIn("KeyError", receipt["stderr"])
            self.assertTrue(self.receipt("locale-display-" + locale)["stdout"])

    def test_handoff_and_optional_real_mcp_never_use_production_memory(self):
        packet = json.loads((self.output / "handoff.json").read_text())
        self.assertEqual(packet["authority"], "REFERENCE_ONLY")
        self.assertFalse(packet["automatic_conversation_collection"])
        self.assertEqual({item["run_id"] for item in packet["runs"]}, {"decision", "candidate", "stale-control"})
        raw = json.dumps(packet)
        for excluded in ("ARTIFICIAL_REQUEST_DO_NOT_EXPORT", "ARTIFICIAL_PROPOSAL_DO_NOT_EXPORT",
                         "ARTIFICIAL_LEARNING_RESPONSE_DO_NOT_EXPORT", "ARTIFICIAL_PRIVATE_FILE_DO_NOT_EXPORT"):
            self.assertNotIn(excluded, raw)
        memory = self.report["memory"]
        self.assertEqual(memory["performed"], self.memory_available)
        if self.memory_available:
            self.assertTrue(memory["name"].startswith("verantyx-demo-"))
            self.assertFalse(memory["production_memory_used"])
            self.assertEqual(memory["entries"], 6)
            self.assertTrue(Path(memory["home"]).is_relative_to(self.output))
            server = json.loads(Path(memory["server_configuration"]).read_text())
            self.assertEqual(Path(server["env"]["HOME"]), self.output / "memory-home")
            self.assertTrue(self.receipt("memory-save-retry")["result"]["duplicate"])
            read = self.receipt("memory-read")["result"]["result"]
            self.assertEqual(len(read["entries"]), 6)
            self.assertIn(self.report["handoff"]["packet_sha256"], json.dumps(read))
            self.assertEqual(self.receipt("memory-reject-changed-packet")["result"]["error"]["code"], "MEMORY_PACKET_CHANGED")

    def test_demo_refuses_existing_output_without_overwriting_artifacts(self):
        paths = [self.output / "report.json", self.output / "commands.json", self.project / ".verantyx/state.db"]
        before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
        process = subprocess.run(self.argv, cwd=ROOT, env=self.environment, stdin=subprocess.DEVNULL,
                                 capture_output=True, text=True, timeout=15)
        self.assertEqual(process.returncode, 2)
        self.assertIn("Refusing to overwrite", process.stderr)
        self.assertEqual({path: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}, before)


if __name__ == "__main__":
    unittest.main()
