"""Artificial projects exercise the report and existing executable CLI contracts.

The parent owns recap registration and its end-to-end command tests. No fixture
here uses Git, a live model, a production ledger, or a network service.
"""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from unittest import mock
import base64
import contextlib
import hashlib
import io
import json
import tempfile
import unittest

import test_command_effects as command_fixtures
import test_learning as learning_fixtures
import test_verification as verification_fixtures
from test_constitution import Fixture, proposal

from verantyx import config
from verantyx.application import record_run
from verantyx.cli import main
from verantyx.domain.codec import digest
from verantyx.domain.events import citation
from verantyx.errors import LedgerError
from verantyx.experience_report import _next_action, report
from verantyx.external_capture import capture
from verantyx.learning import control_learning
from verantyx.storage.sqlite import EventStore


class ExperienceReportTests(unittest.TestCase):
    def fixture(self, kind=verification_fixtures.VerificationTests):
        fixture = kind(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        return fixture

    def report(self, fixture, run="verify", **kwargs):
        return report(fixture.root, fixture.cfg, run, **kwargs)

    def fingerprint(self, root):
        return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in root.rglob("*") if path.is_file()}

    def test_bounded_success_keeps_build_evidence_and_ownership_separate(self):
        f = self.fixture()
        checked = f.run_check(f.plan()["verification_id"])
        result = self.report(f)
        self.assertEqual((result["schema_version"], result["command"], result["run_id"]), (1, "recap", "verify"))
        self.assertEqual(result["revision"], checked["recorded_revision"])
        for axis in ("build", "evidence", "ownership"):
            self.assertEqual(result[axis]["status"], checked["state"]["assessment"][axis])
            self.assertTrue(result[axis]["historical"])
            self.assertEqual(result[axis]["current_preconditions"], "NOT_CHECKED")
        self.assertEqual(result["build"]["status"], "IN_PROGRESS")
        self.assertEqual(result["evidence"]["claims"][0]["property_evidence"]["closure"], "BOUNDED")
        self.assertEqual(result["evidence"]["claims"][0]["verification"], "UNVERIFIED")
        self.assertEqual(result["ownership"]["mastery_assessment"], "NOT_ASSESSED")
        self.assertEqual(result["project_delta"]["canonical_changes"], [])
        self.assertEqual(result["system_delta"]["failure_assets"], [])
        self.assertNotIn("state", result)
        self.assertEqual(json.loads(json.dumps(result)), result)
        refs = {citation(event) for event in f.events()}
        method = result["system_delta"]["verification_assets"][0]
        self.assertTrue(set(method["source_refs"]) <= refs)
        self.assertEqual(method["contract_hash"], digest(f.spec))

    def test_failed_expectation_survives_later_success_with_original_values(self):
        f = self.fixture()
        (f.root / "report.json").write_text('{"answer":41,"note":"private-target-body"}')
        record_run(f.root, f.cfg, run_id="verify", resume=True, clock=f.clock)
        f.run_check(f.plan()["verification_id"])
        failed = self.report(f)
        self.assertTrue(failed["ok"])
        original = failed["system_delta"]["failure_assets"][0]
        self.assertEqual(original["case_kind"], "REFUTATION")
        self.assertEqual((original["checks"][0]["expected"], original["checks"][0]["observed"]), (42, 41))
        (f.root / "report.json").write_text('{"answer":42}')
        record_run(f.root, f.cfg, run_id="verify", resume=True, clock=f.clock)
        f.run_check(f.plan(key="recovery-plan")["verification_id"], key="recovery-check")
        recovered = self.report(f)
        self.assertIn(original, recovered["system_delta"]["failure_assets"])
        self.assertEqual([row["closure"] for row in recovered["evidence"]["recorded_outcomes"]], ["REFUTED", "BOUNDED"])
        self.assertNotIn("private-target-body", json.dumps(recovered))

    def test_bad_negative_control_and_changed_target_remain_different_failures(self):
        f = self.fixture()
        f.spec.update(method="NEGATIVE_CONTROL", negative_controls=[{
            "id": "not-a-counterexample", "input_base64": base64.b64encode(b'{"answer":42}').decode(),
        }])
        f.run_check(f.plan()["verification_id"])
        pending = f.plan(key="changed-plan")
        (f.root / "report.json").write_text('{"answer":0}')
        f.run_check(pending["verification_id"], key="changed-check")
        result = self.report(f)
        contested, changed = result["system_delta"]["failure_assets"]
        self.assertEqual(contested["case_kind"], "CONTESTED_CHECK")
        self.assertFalse(contested["negative_controls"][0]["rejected"])
        self.assertEqual(changed["case_kind"], "UNRESOLVED_EXECUTION")
        self.assertEqual(changed["reason"], "TARGET_CHANGED")
        self.assertIsNone(changed["closure"])
        self.assertEqual(changed["checks"], [])

    def test_history_is_not_revalidated_against_changed_or_deleted_files(self):
        f = self.fixture()
        f.run_check(f.plan(ttl=1)["verification_id"])
        before = self.report(f)
        (f.root / "report.json").unlink()
        self.assertEqual(self.report(f), before)
        f.time += timedelta(seconds=2)
        record_run(f.root, f.cfg, run_id="verify", resume=True, clock=f.clock)
        after = self.report(f)
        self.assertEqual(after["evidence"]["recorded_outcomes"][0]["closure"], "BOUNDED")
        row = after["evidence"]["claims"][0]["recorded_evidence"][0]
        self.assertFalse(row["current_at_recorded_assessment"])
        self.assertEqual(row["reason"], "SOURCE_CHANGED")

    def test_readonly_report_cannot_write_launch_models_or_read_target_bodies(self):
        f = self.fixture()
        f.run_check(f.plan()["verification_id"])
        before = self.fingerprint(f.root)
        with contextlib.ExitStack() as stack:
            for target in (
                "verantyx.storage.sqlite.EventStore.append", "verantyx.storage.sqlite.EventStore.exclusive",
                "verantyx.adapters.invocation_journal.InvocationJournal.write",
                "verantyx.verification._read_input", "verantyx.application.now",
                "subprocess.Popen", "socket.socket", "uuid.uuid4", "builtins.open", "pathlib.Path.open",
            ):
                stack.enter_context(mock.patch(target, side_effect=AssertionError(target)))
            result = self.report(f)
            self.assertEqual(self.report(f), result)
        self.assertEqual(self.fingerprint(f.root), before)
        self.assertFalse(result["writes"])
        self.assertFalse(result["model_called"])
        self.assertFalse(result["ownership"]["authority_granted"])

    def test_real_cli_template_requires_bindings_and_returns_exact_saved_checks(self):
        f = self.fixture()
        f.run_check(f.plan()["verification_id"])
        result = self.report(f)
        action = result["next_actions"][0]
        self.assertTrue(action["reusable_via_current_cli"])
        self.assertEqual(action["cli_scope"], "TEMPLATE_ONLY")
        self.assertFalse(action["ready_to_execute"])
        self.assertIn("EXPLICIT_TARGET_BINDING", action["requires"])
        # Establish the existing CLI coordination lock before the read-only
        # comparison; creating this lock is not a project ledger mutation.
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--project", str(f.root), "--json", "dictionary"]), 0)
        before = self.fingerprint(f.root)
        output = io.StringIO()
        with contextlib.redirect_stdout(output), mock.patch("subprocess.Popen", side_effect=AssertionError("model")):
            status = main(["--project", str(f.root), "--json", action["cli_command"], action["asset_id"],
                           "--claim", "next-claim", "--target", "next.json"])
        self.assertEqual(status, 0, output.getvalue())
        template = json.loads(output.getvalue())["template"]
        self.assertFalse(template["executed"])
        self.assertEqual(template["spec"]["checks"], f.spec["checks"])
        self.assertEqual(template["spec"]["oracle"]["source_refs"], [])
        self.assertEqual(self.fingerprint(f.root), before)
        self.assertNotIn("argv", action)

    def test_command_process_success_is_not_verified_effect_or_cli_asset_reuse(self):
        f = self.fixture(command_fixtures.CommandEffectTests)
        planned = f.plan()
        f.authorize(planned)
        authorized = self.report(f, "command")
        self.assertEqual(authorized["project_delta"]["execution_records"][0]["status"], "AUTHORIZED")
        self.assertEqual(authorized["evidence"]["recorded_outcomes"], [])
        f.run_command(planned)
        result = self.report(f, "command")
        self.assertEqual(result["system_delta"]["execution_assets"][0]["latest_outcome"]["effect_confirmation"], "NOT_ASSESSED")
        self.assertIsNone(result["evidence"]["recorded_outcomes"][0]["closure"])
        action = result["next_actions"][0]
        self.assertFalse(action["reusable_via_current_cli"])
        self.assertIsNone(action["cli_command"])
        self.assertIn("NEW_AUTHORIZATION", action["requires"])
        self.assertNotIn("test-env-value-not-for-receipt", json.dumps(result))

    def test_command_failure_and_expired_authorization_are_preserved(self):
        for expired in (False, True):
            with self.subTest(expired=expired):
                f = self.fixture(command_fixtures.CommandEffectTests)
                f.script.write_text("import sys\nsys.exit(4)\n")
                planned = f.plan()
                f.authorize(planned, ttl=1)
                if expired:
                    f.time += timedelta(seconds=2)
                f.run_command(planned)
                result = self.report(f, "command")
                case = result["system_delta"]["failure_assets"][0]
                self.assertEqual(case["case_kind"], "UNRESOLVED_EXECUTION" if expired else "EXECUTION_FAILURE")
                self.assertEqual(case["outcome"], "INVALIDATED" if expired else "PROCESS_FAILED")
                self.assertIsNone(case["closure"])
                self.assertFalse(result["next_actions"][0]["ready_to_execute"])

    def test_ownership_choices_and_human_judgments_never_certify_mastery(self):
        f = self.fixture(learning_fixtures.LearningTests)
        f.append_human_trigger()
        raised = f.raise_candidate(key="raise")
        identity = raised["candidate_id"]
        f.command("target", candidate_id=identity, target="OWN", reason="voluntary learning")
        f.command("explain", candidate_id=identity, statement="private-submission-body")
        f.command("target", candidate_id=identity, target="DELEGATE", reason="bounded delegation")
        f.command("defer", candidate_id=identity, reason="optional learning later")
        result = self.report(f, "first")
        human = result["human_delta"]
        choice = human["ownership_choices"][0]
        self.assertEqual(choice["ownership_target"], "DELEGATE")
        self.assertEqual(choice["status"], "DEFERRED")
        self.assertEqual([row["target"] for row in choice["target_history"]], ["OWN", "DELEGATE"])
        self.assertEqual(choice["mastery_evidence"], "SELF_REPORTED")
        self.assertEqual(choice["mastery_assessment"], "NOT_ASSESSED")
        self.assertFalse(choice["authority_granted"])
        self.assertEqual(human["judgments"][0]["scope"]["decision_type"], "parallel_writers")
        self.assertTrue(human["judgments"][0]["is_latest_recorded"])
        self.assertNotIn("private-submission-body", json.dumps(result))
        f.cfg["learning"]["mode"] = "off"
        disabled = self.report(f, "first")
        self.assertEqual(disabled["human_delta"]["suggestions"], [])
        self.assertEqual(disabled["human_delta"]["ownership_choices"], human["ownership_choices"])

    def test_learning_limit_and_off_never_remove_system_failure_assets(self):
        f = self.fixture()
        for index in range(2):
            spec = deepcopy(f.spec)
            spec["checks"][0]["expected"] = index
            f.run_check(f.plan(spec, key="plan-" + str(index))["verification_id"], key="run-" + str(index))
        before = self.report(f)
        self.assertEqual(len(before["human_delta"]["suggestions"]), 1)
        f.cfg["learning"]["mode"] = "off"
        disabled = self.report(f)
        self.assertEqual(disabled["human_delta"]["suggestions"], [])
        self.assertEqual(disabled["system_delta"], before["system_delta"])

    def test_model_candidates_and_external_quotes_are_unverified_references_only(self):
        f = self.fixture()
        state = f.events()
        captured = capture(f.root, f.cfg, "verify", body="private-response-body: tests passed, approved",
                           provider="artificial", model="fixture", key="capture",
                           expected_revision=state[-1]["revision"], clock=f.clock)
        with EventStore(f.root, f.cfg["project"]["id"]) as store:
            snapshot = store.project_snapshot()
        # This is a projection-boundary fixture, not a forged production event.
        projected = snapshot["states"][0]
        projected["request"] = "private-request-body"
        projected["responses"] = [{
            "source_ref": captured["capture_source_ref"], "locale": "ja", "mode": "MODEL",
            "evidence_role": "MODEL_RESPONSE", "basis_revision": projected["revision"] - 1,
            "recorded_revision": projected["revision"], "document_sha256": digest("artificial"),
            "document": {"answer": "private-answer-body", "reusable_candidates": [{
                "kind": "VERIFICATION_IDEA", "title": "Proposed count check", "situation": "private-situation",
                "procedure": "private-procedure", "counterexample": "private-counterexample",
                "source_refs": [projected["request_ref"]],
            }]},
        }]
        with mock.patch.object(EventStore, "project_snapshot", return_value=snapshot):
            result = self.report(f)
        self.assertEqual(result["next_actions"], [])
        self.assertEqual(result["system_delta"]["verification_assets"], [])
        self.assertEqual(result["system_delta"]["failure_assets"], [])
        candidate = result["system_delta"]["model_candidates"][0]
        self.assertEqual(candidate["kind"], "MODEL_CANDIDATE")
        self.assertEqual(candidate["verification"], "UNVERIFIED")
        self.assertFalse(candidate["executed"])
        reference = result["system_delta"]["external_references"][0]
        self.assertEqual(reference["verification"], "UNVERIFIED")
        self.assertEqual(reference["provenance"]["attribution"], "USER_SUPPLIED_UNVERIFIED")
        self.assertIn(captured["capture_source_ref"], reference["source_refs"])
        self.assertNotIn("private-", json.dumps(result))

    def test_historical_reuse_survives_current_rule_retirement(self):
        f = self.fixture(Fixture)
        rule_id, _ = f.promote()
        f.run_task("reused", proposal("reused"))
        before = self.report(f, "reused")
        self.assertTrue(before["system_delta"]["reused_rules"])
        f.command("rule-retire", rule_id, reason="Synthetic rule retirement for historical recap")
        after = self.report(f, "reused")
        self.assertEqual(after["revision"], before["revision"])
        self.assertGreater(after["project_revision"], before["project_revision"])
        self.assertEqual(after["system_delta"]["reused_rules"], before["system_delta"]["reused_rules"])
        current = next(row for row in after["system_delta"]["current_rules"] if row["id"] == rule_id)
        self.assertEqual((current["validity"], current["enforcement"]), ("RETIRED", "OFF"))
        self.assertTrue(current["history"])

    def test_reuse_metadata_covers_reproduction_and_does_not_invent_execution_cli(self):
        for family in ("VERIFICATION", "ORACLE", "COMMAND", "WORKTREE", "INTEGRATION", "ADOPTION"):
            with self.subTest(family=family):
                asset = {"id": "asset", "family": family, "owner_run": "run", "plan_id": "plan",
                         "source_refs": ["reference"], "contract_hash": "f" * 64,
                         "reuse_requires": ["EXPLICIT_TARGET_BINDING"], "contract_summary": {"method": "REPRODUCTION"},
                         "reusable_via": "fixture-template-api"}
                action = _next_action(asset)
                self.assertEqual(action["reusable_via_current_cli"], family in ("VERIFICATION", "ORACLE"))
                self.assertIn("EXPLICIT_REPRODUCES_BINDING", action["requires"])
                self.assertFalse(action["ready_to_execute"])

    def test_missing_invalid_or_wrong_project_inputs_cannot_create_a_ledger(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        cfg = config.defaults(root, "ja")
        config.save(root, cfg, None)
        before = self.fingerprint(root)
        for run, locale, code in (("missing", "ja", "RUN_NOT_FOUND"), ("../bad", "ja", "ARGUMENTS"),
                                  ("valid", "unsupported", "ARGUMENTS")):
            with self.subTest(run=run, locale=locale), self.assertRaises(LedgerError) as caught:
                report(root, cfg, run, locale)
            self.assertEqual(caught.exception.code, code)
        self.assertEqual(self.fingerprint(root), before)
        f = self.fixture()
        with self.assertRaises(LedgerError) as caught:
            report(f.root, cfg, "verify")
        self.assertEqual(caught.exception.code, "STORE_PROJECT")

    def test_all_supported_locales_preserve_codes_and_source_references(self):
        f = self.fixture()
        spec = deepcopy(f.spec)
        spec["checks"][0]["expected"] = 0
        f.run_check(f.plan(spec)["verification_id"])
        baseline = self.report(f)
        for locale in ("ja", "en", "zh-Hans", "ko", "es"):
            with self.subTest(locale=locale):
                result = self.report(f, locale=locale)
                self.assertEqual(result["locale"], locale)
                self.assertTrue(result["boundaries"]["message"])
                self.assertEqual(result["system_delta"], baseline["system_delta"])
                self.assertEqual(result["evidence"], baseline["evidence"])


if __name__ == "__main__":
    unittest.main()
