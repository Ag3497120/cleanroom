"""Actual Git/Precedent execution, crash replay, decisions and experience capture."""
from pathlib import Path
from unittest import mock
import contextlib
import io
import json
import os
import subprocess
import unittest

import test_shared_context as fixtures
from verantyx.application import dispatch, get_projection
from verantyx.cli import main, parse
from verantyx.effects import authorize
from verantyx.errors import LedgerError
from verantyx.responses import ask
from verantyx.sovereignty import report
from verantyx.storage.sqlite import EventStore
from verantyx.work_loop import run_candidate


class WorkLoopTests(unittest.TestCase):
    def setUp(self):
        self.h = fixtures.SharedContextTests()
        self.h.setUp()
        self.addCleanup(self.h.doCleanups)
        self.root, self.cfg = self.h.root, self.h.cfg
        self.proposer, self.editor = self.h.adapters()
        for args in (["init", "-q"], ["add", "calc.py", "test_calc.py"],
                     ["-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "Fixed tests"]):
            subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True)
        self.precedent = os.environ["VERANTYX_PRECEDENT"]

    def command(self, *values):
        _, args = parse(list(map(str, values)))
        return dispatch(self.root, self.cfg, args, "ja")

    def ask(self, run_id="first", **options):
        return ask(self.root, self.cfg, request="Correct the calculator using its existing tests.",
                   adapter_path=self.proposer, editor_adapter=self.editor, include_paths=["calc.py", "test_calc.py"],
                   key=run_id, run_id=run_id, context={"component": "calculator", "workload": "local", "risk": "LOW"}, **options)

    def prepared(self):
        state = self.ask()["state"]
        self.action = state["proposal"]["actions"][0]
        return self.command("decide", "first", "--point", self.action["arguments"]["point_id"],
                            "--choice", "isolate", "--reason", "Artificial fixture decision", "--key", "decision")

    def run_work(self, base, **options):
        return run_candidate(self.root, self.cfg, "first", key="work", expected_revision=base["recorded_revision"],
                             precedent_path=self.precedent, execute=True, **options)

    def test_preview_does_not_authorize_or_write_a_workflow_journal(self):
        base = self.prepared()
        before = set((self.root / ".verantyx/bridges").iterdir())
        result = run_candidate(self.root, self.cfg, "first", key="preview", expected_revision=base["recorded_revision"])
        self.assertEqual(result["work_loop"]["status"], "CANDIDATE_READY")
        self.assertEqual(result["work_loop"]["tests"], ["test_calc.py"])
        self.assertEqual(set((self.root / ".verantyx/bridges").iterdir()), before)
        self.assertEqual(result["state"]["effects"], {})

    def test_execution_tests_candidate_and_collects_assets_without_another_model(self):
        base = self.prepared()
        calls = len(self.h.fixture.invocations())
        result = self.run_work(base)
        self.assertTrue(result["ok"])
        self.assertEqual(result["work_loop"]["evidence"], "BOUNDED")
        self.assertEqual(result["work_loop"]["ownership"], "NOT_ASSESSED")
        self.assertEqual(Path(result["work_loop"]["worktree"]).joinpath("calc.py").read_text(), "def answer():\n    return 2\n")
        self.assertEqual(self.root.joinpath("calc.py").read_text(), "def answer():\n    return 1\n")
        self.assertTrue(result["state"]["deltas"]["system_delta"]["verification_assets"])
        self.assertEqual(len(self.h.fixture.invocations()), calls)
        repeated = self.run_work(base)
        self.assertEqual(repeated["projection_hash"], result["projection_hash"])
        self.assertEqual(len(repeated["state"]["effects"]), 1)
        self.assertEqual(report(self.root, self.cfg)["metrics"]["executed_checks"], 1)

    def test_failure_is_not_success_and_becomes_a_learning_candidate(self):
        script = self.root / "editor.py"
        script.write_text(script.read_text().replace("return 2", "return 999"))
        base = self.prepared()
        result = self.run_work(base)
        self.assertFalse(result["ok"])
        self.assertEqual(result["work_loop"]["status"], "REFUTED")
        delta = result["state"]["deltas"]
        self.assertTrue(delta["system_delta"]["failure_assets"])
        self.assertTrue(any(item["concept_id"] == "worktree_failure" for item in result["state"]["learning_candidates"].values()))
        self.assertLessEqual(len(delta["human_delta"]), 3)
        self.assertTrue(all(item["mastery_assessment"] == "NOT_ASSESSED" for item in delta["human_delta"]))

    def test_interruption_after_effect_never_runs_candidate_twice(self):
        base = self.prepared()
        def crash(stage):
            if stage == "after_effect":
                raise RuntimeError("synthetic crash")
        with self.assertRaises(RuntimeError):
            self.run_work(base, fault=crash)
        with mock.patch("verantyx.adapters.precedent_backend.PrecedentBackend.apply_and_test", side_effect=AssertionError("effect repeated")):
            result = self.run_work(base)
        self.assertFalse(result["ok"])
        self.assertEqual(result["work_loop"]["status"], "OUTCOME_UNKNOWN")
        self.assertEqual(len(result["state"]["effects"]), 1)

    def test_interrupt_after_authorization_resumes_one_lease(self):
        base = self.prepared()
        def crash(stage):
            if stage == "after_authorize":
                raise RuntimeError("synthetic crash")
        with self.assertRaises(RuntimeError):
            self.run_work(base, fault=crash)
        result = self.run_work(base)
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["state"]["effects"]), 1)

    def test_stale_review_revision_cannot_authorize_new_candidate(self):
        base = self.prepared()
        result = self.run_work(base)
        with self.assertRaises(LedgerError) as error:
            authorize(self.root, self.cfg, "first", self.action["id"], self.precedent, "stale",
                      expected_revision=base["recorded_revision"])
        self.assertEqual(error.exception.code, "REVISION_CONFLICT")
        self.assertEqual(len(result["state"]["effects"]), 1)

    def test_unknown_decision_stays_visible_in_ordinary_ask(self):
        result = self.ask(execute_candidate=True, precedent_path=self.precedent)
        self.assertFalse(result["execution_ok"])
        self.assertEqual(result["work_loop"]["status"], "BLOCKED")
        self.assertTrue(result["state"]["assessment"]["question"])
        self.assertEqual(result["state"]["effects"], {})
        self.assertTrue(result["state"]["latest_response"])
        repeated = self.ask(execute_candidate=True, precedent_path=self.precedent)
        self.assertEqual(repeated["projection_hash"], result["projection_hash"])

    def test_no_executable_candidate_is_resumable_after_answer_collection(self):
        script = self.root / "editor.py"
        script.write_text(script.read_text().replace("choice='retain'", "choice='cancel'"))
        result = self.ask(execute_candidate=True, precedent_path=self.precedent)
        self.assertFalse(result["execution_ok"])
        self.assertEqual(result["work_loop"]["status"], "NO_CANDIDATE")
        again = self.ask(execute_candidate=True, precedent_path=self.precedent)
        self.assertEqual(result["projection_hash"], again["projection_hash"])

    def test_console_request_decision_execution_and_learning_are_connected(self):
        class Terminal(io.StringIO):
            def isatty(self):
                return True
        script = "Correct the calculator.\n/decide editor-isolation isolate Artificial fixture decision\n/work execute\n/learn\n/sovereignty\n/quit\n"
        output = Terminal()
        with mock.patch("sys.stdin", Terminal(script)), contextlib.redirect_stdout(output):
            code = main(["--project", str(self.root), "--lang", "ja", "start", "--plain", "--adapter", str(self.proposer),
                         "--editor-adapter", str(self.editor), "--execute-candidate", "--precedent", self.precedent,
                         "--include", "calc.py", "--include", "test_calc.py", "--component", "calculator",
                         "--workload", "local", "--risk", "LOW"])
        self.assertEqual(code, 0)
        self.assertIn("候補の実行状況: COMPLETED", output.getvalue())
        self.assertEqual(report(self.root, self.cfg)["metrics"]["executed_checks"], 1)
        self.assertEqual(report(self.root, self.cfg)["metrics"]["human_decisions"], 1)

    def test_same_scope_second_model_uses_rule_and_executes_without_reasking(self):
        base = self.prepared()
        self.command("precedent-accept", base["precedent_id"], "--key", "accept")
        rule = self.command("rule-draft", base["precedent_id"], "--key", "draft")["rule_id"]
        for command in ("rule-shadow", "rule-confirm", "rule-activate"):
            self.command(command, rule, "--key", command)
        replacement = self.root / "replacement.py"
        replacement.write_bytes((self.root / "vera.py").read_bytes())
        config = json.loads(self.proposer.read_text())
        config["argv"][-1] = str(replacement)
        new_adapter = self.root / "replacement.json"
        new_adapter.write_text(json.dumps(config))
        self.proposer.unlink()
        self.root.joinpath("vera.py").unlink()
        self.proposer = new_adapter
        result = self.ask("second", execute_candidate=True, precedent_path=self.precedent)
        self.assertTrue(result["execution_ok"])
        self.assertIsNone(result["state"]["assessment"]["question"])
        self.assertEqual(result["state"]["human_decisions"], {})
        self.assertTrue(result["state"]["deltas"]["system_delta"]["reused_rules"])
        measured = report(self.root, self.cfg)
        self.assertEqual(measured["metrics"]["human_decisions"], 1)
        self.assertEqual(measured["metrics"]["reused_decisions"], 1)
        self.assertIsNone(measured["unmeasured"]["token_savings"])

    def test_auto_check_cannot_check_root_in_place_of_an_executed_candidate(self):
        with self.assertRaises(LedgerError) as error:
            self.ask(auto_check=True, execute_candidate=True, precedent_path=self.precedent)
        self.assertEqual(error.exception.code, "ARGUMENTS")
        self.assertFalse(self.h.fixture.calls.exists())

    def test_new_value_choice_can_refresh_editor_and_continue_to_fixed_tests(self):
        script = self.root / "vera.py"
        point = {"id": "api", "kind": "VALUE_DECISION", "decision_type": "api_compatibility",
                 "question": "Preserve or change the API?", "options": [
                     {"id": "preserve", "label": "Preserve"}, {"id": "change", "label": "Change"}]}
        script.write_text(script.read_text().replace("d['summary']='A proposal, not an execution.'",
                          "d['summary']='A proposal, not an execution.'; d['decision_points']=" + repr([point])))
        base = self.prepared()
        decided = self.command("decide", "first", "--point", "api", "--choice", "preserve",
                               "--reason", "Artificial test decision", "--key", "api-choice")
        blocked = self.run_work(decided)
        self.assertEqual(blocked["work_loop"]["status"], "BLOCKED")
        refreshed = run_candidate(self.root, self.cfg, "first", key="refresh", expected_revision=blocked["recorded_revision"],
                                  precedent_path=self.precedent, execute=True, refresh=True, adapter_path=self.proposer,
                                  editor_adapter=self.editor, include_paths=["calc.py", "test_calc.py"])
        self.assertTrue(refreshed["ok"])
        calls = self.h.fixture.invocations()
        editor = [value for value in calls if value["format"] == "verantyx.editor-request.v1"][-1]
        chosen = next(row for row in editor["decision_context"]["items"] if row["point"]["id"] == "api")
        self.assertEqual(chosen["selected_option"]["id"], "preserve")

    def test_new_mutation_commands_still_require_existing_signature_mode(self):
        base = self.prepared()
        operations = [
            ["work", "first", "--key", "signed", "--expected-revision", base["recorded_revision"], "--execute", "--precedent", self.precedent],
            ["work", "first", "--key", "signed-refresh", "--expected-revision", base["recorded_revision"], "--refresh", "--adapter", self.proposer, "--editor-adapter", self.editor],
            ["asset-loop", "first", "--key", "signed-asset", "--asset", "example", "--claim", "example", "--target", "calc.py"],
        ]
        with mock.patch("verantyx.authority.state", return_value={"enabled": True}):
            for operation in operations:
                with self.subTest(command=operation), self.assertRaises(LedgerError) as error:
                    self.command(*operation)
                self.assertEqual(error.exception.code, "AUTHORITY_REQUIRED")
            self.assertTrue(self.command("sovereignty")["ok"])
            self.assertTrue(self.command("work", "first", "--key", "read", "--expected-revision", base["recorded_revision"])["ok"])

    def test_cli_and_console_expose_work_and_ownership_without_models(self):
        base = self.prepared()
        value = self.command("work", "first", "--key", "cli", "--expected-revision", base["recorded_revision"],
                             "--execute", "--precedent", self.precedent)
        self.assertTrue(value["ok"])
        self.assertEqual(value["recovery_bundle"]["status"], "SAVED")
        class Terminal(io.StringIO):
            def isatty(self):
                return True
        output = Terminal()
        with mock.patch("sys.stdin", Terminal("/sovereignty\n/quit\n")), contextlib.redirect_stdout(output):
            code = main(["--project", str(self.root), "--lang", "ja", "start", "--plain", "--adapter", str(self.proposer)])
        self.assertEqual(code, 0)
        self.assertIn("経験資産の蓄積状況", output.getvalue())
