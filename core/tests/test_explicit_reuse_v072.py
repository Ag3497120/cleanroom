"""Frozen contracts run after deleting the originating model adapter."""
from unittest import mock
import unittest

import test_asset_integration_v070 as fixtures
from verantyx.asset_workflow import run_asset_workflow
from verantyx.application import dispatch, record_run
from verantyx.cli import parse
from verantyx.errors import LedgerError
from verantyx.sovereignty import report
from verantyx.storage.sqlite import EventStore


class ExplicitReuseTests(unittest.TestCase):
    def setUp(self):
        self.h = fixtures.AssetIntegrationTests()
        self.h.setUp()
        self.addCleanup(self.h.doCleanups)
        self.root, self.cfg = self.h.root, self.h.cfg
        self.first = self.h.ask("first", "old-result.json", "--auto-check")
        self.next = self.h.ask("second", "new-result.json")
        self.asset = self.first["state"]["deltas"]["system_delta"]["verification_assets"][0]["id"]

    def reuse(self, **options):
        arguments = dict(key="reuse", reuse_asset=self.asset, claim_id="claim-property", target_path="new-result.json")
        arguments.update(options)
        return run_asset_workflow(self.root, self.cfg, "second", **arguments)

    def test_model_removed_fixed_contract_reused_and_failure_retained(self):
        calls = len(self.h.invocations())
        self.h.adapter.unlink()
        self.root.joinpath("normal.py").unlink()
        with mock.patch("verantyx.asset_workflow.load_command", side_effect=AssertionError("model required")):
            result = self.reuse()
        self.assertTrue(result["ok"])
        self.assertEqual(result["model_calls"], 0)
        self.assertEqual(result["selection"], "EXPLICIT_REUSE")
        self.assertEqual(result["workflow"]["plan"]["steps"][0]["spec"]["checks"],
                         self.first["asset_workflow"]["plan"]["steps"][0]["spec"]["checks"])
        self.assertEqual(len(self.h.invocations()), calls)
        again = self.reuse()
        self.assertEqual(again["projection_hash"], result["projection_hash"])
        measured = report(self.root, self.cfg)
        self.assertEqual(measured["metrics"]["model_free_reuses"], 1)
        self.assertGreaterEqual(measured["metrics"]["retained_failures"], 1)

    def test_wrong_result_stays_refuted(self):
        record_run(self.root, self.cfg, run_id="second", resume=True, observe_paths=["old-result.json"], key="observe-failed-target")
        result = self.reuse(target_path="old-result.json", include_paths=["old-result.json"])
        self.assertFalse(result["ok"])
        self.assertEqual(result["workflow"]["status"], "REFUTED")
        self.assertEqual(result["model_calls"], 0)

    def test_unobserved_target_is_rejected_before_verification(self):
        with self.assertRaises(LedgerError) as error:
            self.reuse(target_path="old-result.json")
        self.assertEqual(error.exception.code, "PATH_SCOPE")

    def test_missing_and_reference_only_assets_cannot_become_executable(self):
        for asset in ("nonexistent", self.first["state"]["deltas"]["system_delta"]["reuse_candidates"][0]["id"]):
            with self.subTest(asset=asset), self.assertRaises(LedgerError) as error:
                self.reuse(key=asset, reuse_asset=asset)
            self.assertEqual(error.exception.code, "ASSET_NOT_REUSABLE")

    def test_explicit_selection_is_not_limited_by_dictionary_top_k(self):
        with mock.patch("verantyx.assets.project_catalog", side_effect=AssertionError("ranked selection used")):
            result = self.reuse()
        self.assertTrue(result["ok"])

    def test_changed_target_and_changed_idempotency_arguments_are_rejected(self):
        self.reuse()
        with self.assertRaises(LedgerError) as error:
            self.reuse(claim_id="different")
        self.assertEqual(error.exception.code, "IDEMPOTENCY_CONFLICT")

    def test_preview_is_recorded_but_does_not_run_a_check(self):
        result = self.reuse(execute=False)
        self.assertEqual(result["workflow"]["status"], "PLANNED")
        self.assertEqual(result["state"].get("verifications", {}), {})
        self.assertEqual(report(self.root, self.cfg)["metrics"]["model_free_reuses"], 0)

    def test_cli_accepts_asset_without_adapter(self):
        result = self.h.cli("asset-loop", "second", "--asset", self.asset, "--claim", "claim-property",
                            "--target", "new-result.json", "--key", "cli")
        self.assertEqual(result["model_calls"], 0)

    def test_learning_choices_are_separate_from_rules_and_mastery(self):
        candidate = next(iter(self.first["state"]["learning_candidates"]))
        _, args = parse(["learn-target", "first", "--candidate", candidate, "--target", "DELEGATE",
                         "--reason", "Artificial test choice", "--key", "delegate"])
        dispatch(self.root, self.cfg, args, "ja")
        result = report(self.root, self.cfg)
        self.assertEqual(result["human_selected_targets"]["DELEGATE"], 1)
        self.assertEqual(result["metrics"]["active_rules"], 0)
        self.assertIsNone(result["unmeasured"]["human_mastery"])
        self.assertTrue(result["concepts"])
