"""Recorded processes become bounded methods, failure cases and voluntary lessons.

All inputs, proposals and personal submissions in these tests are artificial.
The existing fixtures create temporary projects and run the real local adapters.
"""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from unittest import mock
import base64
import json
import os
import unittest

import test_verification as verification_fixture
import test_oracles as oracle_fixture
import test_command_effects as command_fixture
import test_integration as integration_fixture
from test_constitution import Fixture, SCOPE, PRECEDENT, proposal

from verantyx import assets
from verantyx.application import record_run
from verantyx.domain.codec import canonical, digest
from verantyx.domain.events import citation
from verantyx.domain.rule_extensions import options_contract
from verantyx.errors import LedgerError
from verantyx.growth import deltas, failure_candidates, template_candidates
from verantyx.kernel.reducer import replay, projection
from verantyx.learning import control_learning
from verantyx.storage.sqlite import EventStore, parse_archive
from verantyx.verification import plan_verification, run_verification


class RecordedAssetTests(unittest.TestCase):
    def fixture(self, fixture_type):
        value = fixture_type(methodName="runTest")
        value.setUp()
        self.addCleanup(value.tearDown)
        return value

    def store(self, fixture):
        store = EventStore(fixture.root, fixture.cfg["project"]["id"])
        store.__enter__()
        self.addCleanup(store.__exit__, None, None, None)
        return store

    def json_failure(self):
        f = self.fixture(verification_fixture.VerificationTests)
        (f.root / "report.json").write_text('{"applied_count":2,"private_note":"raw-file-secret"}')
        record_run(f.root, f.cfg, run_id="verify", resume=True, clock=f.clock)
        f.spec.update(property="HTTP retry applies the same operation once",
                      checks=[{"id": "once", "kind": "json.equals", "pointer": "/applied_count", "expected": 1}])
        planned = f.plan()
        result = f.run_check(planned["verification_id"])
        return f, planned, result

    def new_json_run(self, f, run_id, payload, *, learning_mode=None, max_items=None):
        (f.root / "next.json").write_text(json.dumps(payload))
        configuration = deepcopy(f.cfg)
        if learning_mode is not None:
            configuration["learning"]["mode"] = learning_mode
        if max_items is not None:
            configuration["learning"]["max_items"] = max_items
        initial = record_run(f.root, configuration, request="synthetic reuse", run_id=run_id,
                             observe_paths=["next.json"], clock=f.clock)
        document = {"schema_version": 1, "task_id": run_id, "context_revision": initial["state"]["revision"],
                    "response_locale": "ja", "summary": "synthetic test", "claims": [
                        {"id": "next_claim", "statement": "Synthetic retry contract", "source_refs": [initial["state"]["latest_observations"]["next.json"]]}],
                    "actions": [], "unknowns": []}
        (f.root / "next-proposal.json").write_text(json.dumps(document))
        return record_run(f.root, configuration, run_id=run_id, resume=True,
                          proposal_path=f.root / "next-proposal.json", clock=f.clock)

    def test_actual_failure_yields_concrete_sourced_lesson_without_claiming_mastery(self):
        f, planned, result = self.json_failure()
        delta = result["state"]["deltas"]
        case = delta["system_delta"]["failure_assets"][0]
        self.assertEqual(case["case_kind"], "REFUTATION")
        self.assertEqual(case["checks"][0], {"id": "once", "passed": False, "actual_hash": digest(2),
                         "kind": "json.equals", "pointer": "/applied_count", "expected": 1, "observed": 2, "error": None})
        method = delta["system_delta"]["verification_assets"][0]
        self.assertEqual(method["id"], case["method_id"])
        self.assertEqual(method["contract_hash"], digest(f.spec))
        self.assertEqual(method["outcome_count"], 1)
        candidate = delta["human_delta"][0]
        self.assertEqual(candidate["concept_id"], "verification_failure")
        self.assertIn("/applied_count", candidate["minimum_model"])
        self.assertIn("期待値 1", candidate["minimum_model"])
        self.assertIn("観測値 2", candidate["minimum_model"])
        self.assertEqual(candidate["ownership_target"], "REVIEW")
        self.assertTrue(candidate["target_is_suggestion"])
        self.assertEqual(candidate["mastery_evidence"], "NONE")
        refs = {citation(event) for event in f.events()}
        self.assertTrue(set(candidate["source_refs"]) <= refs)
        self.assertEqual(candidate["source_refs"], case["source_refs"])
        self.assertNotIn("raw-file-secret", canonical(delta["system_delta"]))
        self.assertEqual(result["state"]["assessment"]["claims"][0]["prose_entailment"], "NOT_ASSESSED")

    def test_failure_collection_retries_and_self_report_do_not_duplicate_or_certify(self):
        f, planned, result = self.json_failure()
        candidate_id = result["state"]["deltas"]["human_delta"][0]["id"]
        first = control_learning(f.root, f.cfg, "verify", "collect", key="collect", clock=f.clock)
        before = len(f.events())
        again = control_learning(f.root, f.cfg, "verify", "collect", key="collect", clock=f.clock)
        self.assertTrue(again["duplicate"])
        self.assertEqual(len(f.events()), before)
        self.assertEqual(first["projection_hash"], again["projection_hash"])
        reported = control_learning(f.root, f.cfg, "verify", "explain", candidate_id=candidate_id,
                                    statement="synthetic-human-answer-secret", key="answer", clock=f.clock)
        candidate = next(row for row in reported["candidates"] if row["id"] == candidate_id)
        self.assertEqual(candidate["evidence"][0]["evidence_basis"], "SELF_REPORT")
        self.assertIsNone(candidate["assessment"])
        with self.store(f) as store:
            catalog = assets.project_catalog(store, reported["state"], "ja")
        self.assertNotIn("synthetic-human-answer-secret", canonical(catalog))
        self.assertEqual(catalog["learning"][0]["mastery_assessment"], "NOT_ASSESSED")
        self.assertEqual(len([e for e in f.events() if e["type"] == "LearningCandidateRaised"]), 1)

    def test_explicit_copy_preserves_checks_and_reexecutes_in_another_task(self):
        f, planned, failed = self.json_failure()
        original = failed["state"]["deltas"]["system_delta"]["verification_assets"][0]
        next_state = self.new_json_run(f, "next", {"applied_count": 1})["state"]
        store = self.store(f)
        before = len(store.events())
        with mock.patch("verantyx.verification._read_input", side_effect=AssertionError("template ran check")):
            template = assets.verification_template_from_asset(store, original["id"], claim_id="next_claim", target_path="next.json")
        self.assertEqual(len(store.events()), before)
        self.assertFalse(template["executed"])
        self.assertEqual(template["spec"]["checks"], f.spec["checks"])
        self.assertEqual(template["source_contract_hash"], original["contract_hash"])
        self.assertEqual(template["spec"]["oracle"]["source_refs"], [])
        copied = plan_verification(f.root, f.cfg, "next", template["spec"], "copy", clock=f.clock)
        self.assertEqual(copied["verification"]["status"], "PLANNED")
        checked = run_verification(f.root, f.cfg, "next", copied["verification_id"], "copy-check", clock=f.clock)
        self.assertEqual(checked["verification"]["receipt"]["result"]["closure"], "BOUNDED")
        catalog = assets.project_catalog(store, checked["state"], "ja", "applied_count")
        self.assertEqual({row["owner_run"] for row in catalog["verification_methods"]}, {"verify", "next"})
        self.assertEqual(catalog["verification_methods"][0]["owner_run"], "next")
        self.assertEqual(len(catalog["failure_cases"]), 1)
        self.assertFalse(checked["state"]["can_execute_effects"])
        with self.assertRaises(LedgerError):
            bad = deepcopy(template["spec"])
            bad["oracle"]["source_refs"] = original["source_refs"]
            plan_verification(f.root, f.cfg, "next", bad, "foreign-sources", clock=f.clock)

    def test_learning_off_and_maximum_do_not_remove_system_assets_or_block_verification(self):
        f = self.fixture(verification_fixture.VerificationTests)
        self.new_json_run(f, "off", {"answer": 0}, learning_mode="off")
        spec = deepcopy(f.spec)
        spec.update(claim_id="next_claim", target_path="next.json")
        planned = plan_verification(f.root, f.cfg, "off", spec, "off-plan", clock=f.clock)
        failed = run_verification(f.root, f.cfg, "off", planned["verification_id"], "off-check", clock=f.clock)
        self.assertEqual(failed["state"]["deltas"]["human_delta"], [])
        self.assertEqual(len(failed["state"]["deltas"]["system_delta"]["failure_assets"]), 1)
        collected = control_learning(f.root, f.cfg, "off", "collect", key="off-collect", clock=f.clock)
        self.assertEqual(collected["state"]["learning_candidates"], {})
        catalog = assets.project_catalog(self.store(f), failed["state"], "ja")
        self.assertFalse(any(row["owner_run"] == "off" for row in catalog["learning"]))
        self.new_json_run(f, "limited", {"answer": 0}, max_items=1)
        for number in range(2):
            spec["checks"][0]["expected"] = number + 1
            planned = plan_verification(f.root, f.cfg, "limited", spec, "plan-" + str(number), clock=f.clock)
            failed = run_verification(f.root, f.cfg, "limited", planned["verification_id"], "check-" + str(number), clock=f.clock)
        self.assertEqual(len(failed["state"]["deltas"]["human_delta"]), 1)
        self.assertEqual(len(failed["state"]["deltas"]["system_delta"]["failure_assets"]), 2)
        catalog = assets.project_catalog(self.store(f), failed["state"], "ja")
        self.assertEqual(len([row for row in catalog["learning"] if row["owner_run"] == "limited"]), 1)

    def test_all_five_locales_keep_failures_concrete_and_ownership_optional(self):
        f, planned, result = self.json_failure()
        translations = []
        for locale in ("ja", "en", "zh-Hans", "ko", "es"):
            state = deepcopy(result["state"])
            state["locale"] = locale
            candidate = failure_candidates(state)[0]
            translations.append(candidate["minimum_model"])
            self.assertIn("/applied_count", candidate["minimum_model"])
            self.assertEqual(candidate["mastery_evidence"], "NONE")
            catalog = assets.project_catalog(self.store(f), state, locale)
            self.assertEqual(catalog["locale"], locale)
            self.assertTrue(catalog["boundary"])
        self.assertEqual(len(set(translations)), 5)

    def test_unknown_and_bad_negative_control_are_not_refutations(self):
        f = self.fixture(verification_fixture.VerificationTests)
        f.spec.update(method="NEGATIVE_CONTROL", negative_controls=[{
            "id": "not-a-counterexample", "input_base64": base64.b64encode(b'{"answer":42}').decode()}])
        contested = f.run_check(f.plan()["verification_id"])
        asset = assets.project_assets(contested["state"])["failure_cases"][0]
        self.assertEqual(asset["case_kind"], "CONTESTED_CHECK")
        self.assertFalse(asset["negative_controls"][0]["rejected"])
        planned = f.plan(key="stale-plan")
        (f.root / "report.json").write_text('{"answer":41}')
        unknown = f.run_check(planned["verification_id"], key="stale-check")
        asset = assets.project_assets(unknown["state"])["failure_cases"][-1]
        self.assertEqual(asset["case_kind"], "UNRESOLVED_EXECUTION")
        self.assertEqual(asset["reason"], "TARGET_CHANGED")
        self.assertEqual(asset["checks"], [])
        self.assertNotEqual(asset["closure"], "REFUTED")

    def test_observation_and_reproduction_are_distinct_reusable_contracts(self):
        f = self.fixture(verification_fixture.VerificationTests)
        observation = deepcopy(f.spec)
        observation.update(method="OBSERVATION", checks=[])
        observed = f.run_check(f.plan(observation)["verification_id"])
        asset = assets.project_assets(observed["state"])["verification_methods"][0]
        self.assertEqual(asset["latest_outcome"]["closure"], "SUPPORTED")
        self.assertEqual(asset["prose_entailment"], "NOT_ASSESSED")
        self.assertEqual(assets.project_assets(observed["state"])["failure_cases"], [])
        original = f.plan(key="original")["verification_id"]
        f.run_check(original, key="original-check")
        spec = deepcopy(f.spec)
        spec.update(method="REPRODUCTION", reproduces=original)
        reproduced = f.run_check(f.plan(spec, key="reproduce")["verification_id"], key="reproduce-check")
        asset = assets.project_assets(reproduced["state"])["verification_methods"][-1]
        self.assertEqual(asset["contract_summary"]["method"], "REPRODUCTION")
        with self.assertRaises(LedgerError):
            assets.verification_template_from_asset(self.store(f), asset["id"], claim_id="answer", target_path="report.json")
        template = assets.verification_template_from_asset(self.store(f), asset["id"], claim_id="answer", target_path="report.json", reproduces=original)
        self.assertEqual(template["spec"]["reproduces"], original)

    @unittest.skipUnless(PRECEDENT, "set VERANTYX_PRECEDENT")
    def test_actual_oracle_failure_and_protocol_failure_have_different_assets(self):
        f = self.fixture(oracle_fixture.OracleTests)
        f.change("def answer(value):\n    return value * 3\n")
        failed = f.run_oracle(f.plan()["oracle_id"])
        case = assets.project_assets(failed["state"])["failure_cases"][0]
        self.assertEqual(case["case_kind"], "REFUTATION")
        self.assertEqual(case["checks"][0]["expected"], 42)
        self.assertEqual(case["checks"][0]["observed"], 63)
        self.assertEqual(failed["state"]["deltas"]["human_delta"][0]["concept_id"], "oracle_failure")
        template = assets.verification_template_from_asset(self.store(f), case["id"], claim_id="claim", target_path="candidate.py")
        self.assertEqual(template["command"], "oracle-plan")
        self.assertEqual(template["spec"]["cases"], f.spec["cases"])
        other = self.fixture(oracle_fixture.OracleTests)
        other.change("import os\nprint('fake success',flush=True)\nos._exit(0)\n")
        unknown = other.run_oracle(other.plan()["oracle_id"])
        case = assets.project_assets(unknown["state"])["failure_cases"][0]
        self.assertEqual(case["case_kind"], "UNRESOLVED_EXECUTION")
        self.assertEqual(case["closure"], "UNKNOWN")
        self.assertNotIn("fake success", canonical(assets.project_assets(unknown["state"])))

    def test_actual_command_success_is_not_verified_effect_and_template_does_not_run(self):
        f = self.fixture(command_fixture.CommandEffectTests)
        f.spec["input"]["text"] = "private-command-input"
        planned = f.plan()
        f.authorize(planned)
        result = f.run_command(planned)
        projected = assets.project_assets(result["state"])
        self.assertEqual(projected["failure_cases"], [])
        asset = projected["execution_methods"][0]
        self.assertEqual(asset["latest_outcome"]["effect_confirmation"], "NOT_ASSESSED")
        self.assertIsNone(asset["latest_outcome"]["closure"])
        self.assertEqual(asset["contract_summary"]["isolation"], "NONE_TRUSTED_COMMAND")
        catalog = assets.project_catalog(self.store(f), result["state"], "ja")
        self.assertNotIn("test-env-value-not-for-receipt", canonical(catalog))
        self.assertNotIn("private-command-input", canonical(catalog))
        before = f.target.read_bytes()
        with mock.patch("subprocess.Popen", side_effect=AssertionError("template launched command")):
            template = assets.execution_template_from_asset(self.store(f), asset["id"])
        self.assertFalse(template["executed"])
        self.assertEqual(template["recipe"]["spec"], f.spec)
        self.assertIn("NEW_AUTHORIZATION", template["recipe"]["requires"])
        self.assertEqual(f.target.read_bytes(), before)

    def test_command_nonzero_and_timeout_keep_failure_and_unknown_separate(self):
        for script, outcome, case_kind in (("import sys\nsys.exit(4)\n", "PROCESS_FAILED", "EXECUTION_FAILURE"),
                                           ("import time\ntime.sleep(1)\n", "OUTCOME_UNKNOWN", "UNRESOLVED_EXECUTION")):
            with self.subTest(outcome=outcome):
                f = self.fixture(command_fixture.CommandEffectTests)
                f.script.write_text(script)
                f.spec["timeout"] = 0.1
                planned = f.plan()
                f.authorize(planned)
                result = f.run_command(planned)
                case = assets.project_assets(result["state"])["failure_cases"][0]
                self.assertEqual(case["outcome"], outcome)
                self.assertEqual(case["case_kind"], case_kind)
                self.assertIsNone(case["closure"])
                self.assertEqual(result["state"]["deltas"]["human_delta"][0]["concept_id"], "command_failure")

    @unittest.skipUnless(PRECEDENT, "set VERANTYX_PRECEDENT")
    def test_actual_worktree_failure_and_expired_lease_remain_sourced_and_reusable(self):
        f = self.fixture(Fixture)
        f.init_git()
        canonical_before = (f.root / "calc.py").read_bytes()
        f.promote()
        document = proposal("wrong-candidate", action=True)
        document["actions"][0]["arguments"]["files"]["calc.py"] = "def add(a,b):\n    return 0\n"
        f.run_task("wrong-candidate", document)
        from verantyx.effects import authorize, execute
        lease = authorize(f.root, f.cfg, "wrong-candidate", "writer", PRECEDENT, "authorize-wrong", clock=f.clock)
        failed = execute(f.root, f.cfg, "wrong-candidate", lease["lease_id"], PRECEDENT, "execute-wrong", clock=f.clock)
        case = assets.project_assets(failed["state"])["failure_cases"][0]
        self.assertEqual((case["family"], case["closure"]), ("WORKTREE", "REFUTED"))
        self.assertIn("test_calc.py", case["target"])
        self.assertEqual(case["test_summary"]["exit"], 1)
        self.assertTrue(any(row["concept_id"] == "worktree_failure" for row in failed["state"]["deltas"]["human_delta"]))
        with mock.patch("subprocess.run", side_effect=AssertionError("template executed Git")):
            template = assets.execution_template_from_asset(self.store(f), case["id"])
        self.assertEqual(template["recipe"]["proposed_action"]["arguments"]["files"], document["actions"][0]["arguments"]["files"])
        self.assertEqual(template["recipe"]["tests"], ["test_calc.py"])
        self.assertEqual((f.root / "calc.py").read_bytes(), canonical_before)
        lease = authorize(f.root, f.cfg, "wrong-candidate", "writer", PRECEDENT, "expires", ttl=1, clock=f.clock)
        f.time += timedelta(seconds=1)
        expired = execute(f.root, f.cfg, "wrong-candidate", lease["lease_id"], PRECEDENT, "expired-execution", clock=f.clock)
        case = assets.project_assets(expired["state"])["failure_cases"][-1]
        self.assertEqual(case["event_type"], "AuthorizationInvalidated")
        self.assertEqual(case["case_kind"], "UNRESOLVED_EXECUTION")
        self.assertIsNone(case["closure"])
        self.assertEqual((f.root / "calc.py").read_bytes(), canonical_before)

    def test_bounded_search_limits_input_output_and_excludes_unrelated_data(self):
        f, planned, result = self.json_failure()
        for number in range(2):
            spec = deepcopy(f.spec)
            spec["checks"][0]["expected"] = number + 4
            result = f.run_check(f.plan(spec, key="more-" + str(number))["verification_id"], key="more-check-" + str(number))
        store = self.store(f)
        limited = assets.project_catalog(store, result["state"], "ja", limit=1)
        self.assertEqual(len(limited["verification_methods"]), 1)
        self.assertEqual(limited["truncated"]["verification_methods"], 2)
        for locale in ("ja", "en", "zh-Hans", "ko", "es"):
            bounded = assets.project_catalog(store, result["state"], locale, max_bytes=2048)
            self.assertLessEqual(len(canonical(bounded).encode("utf-8")), 2048)
        empty = assets.project_catalog(store, result["state"], "ja", query="absent-nonce")
        self.assertFalse(any(empty[key] for key in ("rules", "verification_methods", "execution_methods", "failure_cases", "learning")))
        self.assertNotIn("raw-file-secret", canonical(limited))
        for kwargs in ({"query": "x" * 513}, {"query": []}, {"limit": True}, {"max_bytes": 1024}, {"limit": 0}):
            with self.assertRaises(LedgerError):
                assets.project_catalog(store, result["state"], "ja", **kwargs)

    def test_catalog_and_asset_ids_resolve_only_validated_local_project_history(self):
        f, planned, result = self.json_failure()
        store = self.store(f)
        asset = result["state"]["deltas"]["system_delta"]["failure_assets"][0]
        self.assertEqual(assets.get_asset(store, asset["id"]), asset)
        with self.assertRaises(LedgerError) as error:
            assets.get_asset(store, "f" * 64)
        self.assertEqual(error.exception.code, "ASSET_NOT_FOUND")
        with self.assertRaises(LedgerError):
            assets.get_asset(store, "../bad")
        state = deepcopy(result["state"])
        state["project_id"] = "not-this-project"
        with self.assertRaises(LedgerError) as error:
            assets.project_catalog(store, state, "ja")
        self.assertEqual(error.exception.code, "STORE_PROJECT")
        other = self.fixture(verification_fixture.VerificationTests)
        another = self.store(other)
        with EventStore(other.root, other.cfg["project"]["id"], create=True) as writable:
            writable.import_archive(store.export().encode(), "2026-09-06T00:00:00.000000Z")
        self.assertEqual(assets.project_catalog(another, None, "ja")["failure_cases"], [])
        with self.assertRaises(LedgerError):
            assets.get_asset(another, asset["id"])

    def test_replay_and_archive_are_pure_and_receipt_tampering_is_still_rejected(self):
        f, planned, result = self.json_failure()
        events = f.events()
        store = self.store(f)
        archive = store.export().encode()
        expected = projection(replay(events))
        (f.root / "report.json").unlink()
        with mock.patch("builtins.open", side_effect=AssertionError("file I/O")), \
             mock.patch("pathlib.Path.open", side_effect=AssertionError("file I/O")), \
             mock.patch("subprocess.run", side_effect=AssertionError("process")), \
             mock.patch("uuid.uuid4", side_effect=AssertionError("random")), \
             mock.patch("time.time", side_effect=AssertionError("wall clock")), \
             mock.patch("socket.socket", side_effect=AssertionError("network")):
            self.assertEqual(projection(replay(events)), expected)
            parse_archive(archive)
            self.assertEqual(assets.project_catalog(store, expected["state"], "ja")["failure_cases"],
                             expected["state"]["deltas"]["system_delta"]["failure_assets"])
        index = next(i for i, event in enumerate(events) if event["type"] == "VerificationRecorded")
        bad = deepcopy(events[index])
        bad["payload"]["result"]["checks"][0]["passed"] = True
        bad["event_hash"] = digest({k: v for k, v in bad.items() if k != "event_hash"})
        with self.assertRaises(LedgerError):
            replay([*events[:index], bad])

    def test_response_candidates_are_unverified_and_exclude_response_body(self):
        f = self.fixture(verification_fixture.VerificationTests)
        state = replay(f.events())
        ref = state["proposal_ref"]
        # The parent response reducer is tested separately; this exercises its
        # documented state projection contract without inventing event authority.
        state["responses"] = [{"source_ref": ref, "locale": "ja", "recorded_revision": state["revision"],
            "basis_revision": state["revision"] - 1, "document_sha256": digest("artificial response"),
            "mode": "MODEL", "evidence_role": "MODEL_RESPONSE", "document": {
                "answer": "private-response-body", "reusable_candidates": [{"kind": "VERIFICATION_IDEA",
                    "title": "Check retry counts", "situation": "When delivery repeats", "procedure": "Compare count against one",
                    "counterexample": "An operation applied twice", "source_refs": [state["request_ref"]]}]}}]
        row = assets.project_assets(state)["reuse_candidates"][0]
        self.assertEqual(row["kind"], "MODEL_CANDIDATE")
        self.assertEqual(row["verification"], "UNVERIFIED")
        self.assertEqual(row["enforcement"], "OFF")
        self.assertFalse(row["executed"])
        self.assertNotIn("private-response-body", canonical(assets.project_assets(state)))
        self.assertEqual(deltas(state)["system_delta"]["reuse_candidates"], [row])
        # The template gate rejects even an otherwise resolved model candidate.
        with mock.patch.object(assets, "get_asset", return_value=row):
            for call in (lambda: assets.verification_template_from_asset(None, row["id"], claim_id="answer", target_path="report.json"),
                         lambda: assets.execution_template_from_asset(None, row["id"])):
                with self.assertRaises(LedgerError) as error:
                    call()
                self.assertEqual(error.exception.code, "ASSET_NOT_REUSABLE")


class CanonicalDictionaryTests(Fixture):
    def test_exact_choice_labels_and_hash_remain_required_across_tasks_and_languages(self):
        rule_id, active = self.promote()
        next_task = self.run_task("next")
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            for locale in ("ja", "en", "zh-Hans", "ko", "es"):
                row = assets.project_catalog(store, next_task["state"], locale)["rules"][0]
                self.assertEqual(row["id"], rule_id)
                self.assertEqual(row["decision_type"], "parallel_writers")
                self.assertEqual(row["options"], proposal("unused")["decision_points"][0]["options"])
                self.assertEqual(row["options_contract_hash"], options_contract(row["options"]))
                self.assertTrue(row["applicable_to_requested_context"])
                self.assertTrue(row["source_refs"])
        changed = proposal("different-label")
        changed["decision_points"][0]["options"][0]["label"] = "a different meaning"
        rejected = self.run_task("different-label", changed)
        self.assertEqual(rejected["state"]["assessment"]["judgments"][0]["reason"], "RULE_OPTION_CHANGED")

    def test_contested_and_retired_rules_are_not_current_dictionary_contracts(self):
        rule_id, active = self.promote()
        self.command("rule-contest", rule_id, reason="artificial counterexample")
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            self.assertEqual(assets.project_catalog(store, active["state"], "ja")["rules"], [])
        self.command("rule-retire", rule_id, reason="artificial retirement")
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            self.assertEqual(assets.project_catalog(store, active["state"], "ja")["rules"], [])

    def test_expiry_uses_recorded_project_time_and_other_scopes_are_labelled(self):
        rule_id, active = self.promote()
        different = self.run_task("other", context={**SCOPE, "risk": "LOW"})
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            row = assets.project_catalog(store, different["state"], "ja")["rules"][0]
            self.assertFalse(row["applicable_to_requested_context"])
            old = assets.project_catalog(store, active["state"], "ja")
            with mock.patch("time.time", return_value=99999999999999):
                self.assertEqual(assets.project_catalog(store, active["state"], "ja"), old)
        self.time += timedelta(days=365)
        later = self.run_task("later")
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            self.assertEqual(assets.project_catalog(store, later["state"], "ja")["rules"], [])


@unittest.skipUnless(PRECEDENT, "set VERANTYX_PRECEDENT")
class IntegrationAssetTests(unittest.TestCase):
    def test_actual_failed_recheck_is_preserved_after_resolution_and_success(self):
        f = integration_fixture.IntegrationTests(methodName="runTest")
        f.setUp()
        self.addCleanup(f.tearDown)
        planned = f.prepare(diverge={"calc.py": "def add(a,b):\n    return a - b\n"})
        from verantyx.integration import resolve_integration, check_integration
        conflicted = assets.project_assets(planned["state"])["failure_cases"]
        self.assertEqual(conflicted[-1]["reason"], "INTEGRATION_CONFLICT")
        resolve_integration(f.root, f.cfg, "candidate", f.identifier, PRECEDENT, "bad-resolution",
                            files={"calc.py": "def add(a,b):\n    return 9\n"}, reason="synthetic wrong resolution", clock=f.clock)
        failed = check_integration(f.root, f.cfg, "candidate", f.identifier, PRECEDENT, "first-check", clock=f.clock)
        self.assertEqual(failed["integration"]["status"], "CHECK_FAILED")
        case = assets.project_assets(failed["state"])["failure_cases"][-1]
        self.assertEqual(case["closure"], "REFUTED")
        self.assertIn("output_hash", case["test_summary"])
        self.assertNotIn("output", case["test_summary"])
        resolve_integration(f.root, f.cfg, "candidate", f.identifier, PRECEDENT, "good-resolution",
                            files={"calc.py": "def add(a,b):\n    return a + b\n"}, reason="synthetic corrected resolution", clock=f.clock)
        passed = check_integration(f.root, f.cfg, "candidate", f.identifier, PRECEDENT, "second-check", clock=f.clock)
        self.assertEqual(passed["integration"]["status"], "VERIFIED")
        rows = assets.project_assets(passed["state"])
        method = next(row for row in rows["verification_methods"] if row["family"] == "INTEGRATION")
        self.assertEqual(method["outcome_count"], 3)
        self.assertEqual(method["latest_outcome"]["closure"], "BOUNDED")
        self.assertEqual(method["contract_summary"]["target_version"], f.before)
        self.assertEqual(set(method["contract_summary"]["test_file_hashes"]), {"test_calc.py"})
        self.assertTrue(any(row["id"] == case["id"] for row in rows["failure_cases"]))
        self.assertEqual(f.git("rev-parse", "HEAD"), f.before)
        self.assertEqual(next(row for row in rows["execution_methods"] if row["family"] == "ADOPTION")["status"], "ADOPTED")
        with EventStore(f.root, f.cfg["project"]["id"]) as store:
            template = assets.execution_template_from_asset(store, method["id"])
            events = store.events("candidate")
        self.assertEqual(template["recipe"]["command"], "integration-plan")
        self.assertIn("NEW_AUTHORIZATION", template["recipe"]["requires"])
        with mock.patch("subprocess.run", side_effect=AssertionError("Git during replay")):
            self.assertEqual(assets.project_assets(replay(events)), rows)


if __name__ == "__main__":
    unittest.main()
