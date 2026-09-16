"""End-to-end read-only ownership view over an explicitly captured AI work item."""

import contextlib
import io
import tempfile
import unittest
from unittest import mock
import json
import sys
from pathlib import Path

from verantyx import config
from verantyx.application import record_run
from verantyx.cli import main
from verantyx.constitution import prepare, set_constitution
from verantyx.constitution import gaps
from verantyx.development import run_work
from verantyx.development import import_job
from verantyx.domain.codec import canonical
from verantyx.external_capture import capture
from verantyx.ownership_report import _candidate_changes, report


class OwnershipMvpTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.cfg = config.defaults(self.root, "ja")
        self.cfg["project"]["name"] = "Ownership fixture"
        self.cfg["project"]["purpose"] = "AI作業から人間の判断と理解を回収する"
        config.save(self.root, self.cfg, None)

    def test_report_keeps_six_deltas_and_marks_unstated_ai_assumptions_unknown(self):
        set_constitution(self.root, self.cfg, purpose=self.cfg["project"]["purpose"],
                         non_negotiables=["根拠不足を完成扱いしない"],
                         human_owned_decisions=["公開範囲"])
        base = record_run(self.root, self.cfg, request="内部CLIを改善する", run_id="ownership", key="base")
        gate = prepare(self.root, self.cfg, "内部CLIを改善する")
        capture(self.root, self.cfg, "ownership", key="capture", expected_revision=base["recorded_revision"],
                provider="fixture", model="none", content_format="json", source_label="fixture",
                body=canonical({"format": "verantyx.work-recovery.v1", "request": "内部CLIを改善する",
                                "summary": {"status": "CANDIDATE_SAVED"}, "task_gate": gate}))
        value = report(self.root, self.cfg, "ownership")
        self.assertTrue(value["ok"])
        self.assertEqual(value["command"], "ownership")
        self.assertEqual(value["task_gate"]["status"], "EXECUTE")
        self.assertEqual(value["ai_decisions_and_assumptions"]["assumption_capture"], "NOT_EXPLICITLY_CAPTURED")
        self.assertIn("project_delta", value)
        self.assertIn("human_decisions", value)
        self.assertIn("evidence_and_unknowns", value)
        self.assertIn("human_learning_delta", value)
        self.assertIn("system_delta", value)

    def test_cli_is_read_only_and_renders_ownership(self):
        record_run(self.root, self.cfg, request="記録だけを確認する", run_id="ownership", key="base")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["--project", str(self.root), "ownership", "ownership"]), 0)
        self.assertIn("PROJECT OWNERSHIP", output.getvalue())

    def test_request_words_do_not_reintroduce_a_semantic_gate(self):
        set_constitution(self.root, self.cfg, purpose=self.cfg["project"]["purpose"],
                         human_owned_decisions=["公開範囲"])
        adapter = self.root / "fixture.json"
        adapter.write_text(json.dumps({"argv": [sys.executable, "-c", "raise SystemExit(99)"]}))
        from verantyx.agent_models import identity
        proposal = {"format": "verantyx.work-proposal.v1", "status": "COMPLETE",
                    "answer": "Investigated the requested change; no publication performed.",
                    "tool_requests": [], "owner_question": "", "assumptions": []}
        with mock.patch("verantyx.work_harness.invoke", return_value={
                    "document": proposal, "model": identity(adapter)}) as work_call, \
                mock.patch("verantyx.agent_runtime.invoke", side_effect=RuntimeError("Reflection unavailable")), \
                mock.patch("verantyx.constitution.prepare", side_effect=AssertionError("Legacy keyword gate")):
            result = run_work(self.root, self.cfg, request="公開するCLIの出力を変更する",
                              work_adapter=str(adapter), key="no-keyword-gate")
        self.assertTrue(result["ok"])
        self.assertEqual(result["work"]["status"], "SUCCEEDED")
        self.assertEqual(result["work"]["tool_counts"]["succeeded"], 0)
        work_call.assert_called_once()
        self.assertEqual(gaps(self.root), [])

    def test_constitution_commands_are_readable_from_the_actual_cli(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["--project", str(self.root), "constitution-set", "--purpose", "人間側に理解を残す"]), 0)
            self.assertEqual(main(["--project", str(self.root), "--json", "constitution"]), 0)
        self.assertIn("人間側に理解を残す", output.getvalue())

    def test_auto_import_cannot_bypass_a_human_decision_gate(self):
        set_constitution(self.root, self.cfg, purpose=self.cfg["project"]["purpose"],
                         human_owned_decisions=["公開範囲"])
        result = import_job(self.root, self.cfg, path=self.root / "not-read.txt", origin="external",
                            label="公開範囲に関わる外部AI仕事", mode="auto", key="import-gate")
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "DECISION_REQUIRED")
        self.assertEqual(result["model_calls"], 0)

    def test_low_level_partner_entry_cannot_bypass_a_human_decision_gate(self):
        set_constitution(self.root, self.cfg, purpose=self.cfg["project"]["purpose"],
                         human_owned_decisions=["公開範囲"])
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["--project", str(self.root), "--json", "partner", "公開する変更を実装する",
                                   "--creator-adapter", "missing-creator.json",
                                   "--reviewer-adapter", "missing-reviewer.json", "--key", "partner-gate"]), 4)
        self.assertIn("DECISION_REQUIRED", output.getvalue())

    def test_unapplied_editor_candidate_is_exposed_as_a_project_delta(self):
        changes = _candidate_changes(
            {"welcome.txt": "Veraへようこそ"},
            [{"path": "welcome.txt", "sha256": "before", "source_ref": "observation-ref"}],
            "editor-ref",
        )
        self.assertEqual(changes, [{
            "path": "welcome.txt", "status": "CANDIDATE_NOT_APPLIED",
            "candidate_sha256": "b71ffac6c25685a973c12ad9fbd1dcb0871f7dcd9aab26297232719578b477d7",
            "candidate_bytes": len("Veraへようこそ".encode("utf-8")),
            "baseline_observation_ref": "observation-ref", "baseline_sha256": "before", "source_ref": "editor-ref",
        }])
