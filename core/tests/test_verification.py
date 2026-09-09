"""Deterministic bounded evidence, adversarial receipts and interrupted runs."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock
import base64
import json
import tempfile
import unittest

from verantyx import config
from verantyx.application import record_run
from verantyx.domain.codec import digest
from verantyx.domain.events import make_event
from verantyx.domain.verification import AXES, check_input, validate_spec
from verantyx.errors import LedgerError
from verantyx.kernel.reducer import replay, projection
from verantyx.storage.sqlite import EventStore, parse_archive
from verantyx.verification import plan_verification, run_verification, list_verifications


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.cfg = config.defaults(self.root, "ja")
        config.save(self.root, self.cfg, None)
        self.time = datetime(2026, 9, 6, tzinfo=timezone.utc)
        self.clock = lambda: self.time
        (self.root / "report.json").write_text('{"answer":42,"ok":true}')
        first = record_run(self.root, self.cfg, request="検証", run_id="verify", observe_paths=["report.json"], clock=self.clock)
        proposal = {"schema_version": 1, "task_id": "verify", "context_revision": first["state"]["revision"], "response_locale": "ja",
                    "summary": "人工テスト用の提案", "claims": [{"id": "answer", "statement": "The answer is 42.",
                    "source_refs": [first["state"]["latest_observations"]["report.json"]]}], "actions": [], "unknowns": []}
        (self.root / "proposal.json").write_text(json.dumps(proposal))
        record_run(self.root, self.cfg, run_id="verify", proposal_path=self.root / "proposal.json", resume=True, clock=self.clock)
        self.spec = {"claim_id": "answer", "target_path": "report.json", "property": "/answer equals integer 42", "method": "TEST",
                     "checks": [{"id": "answer", "kind": "json.equals", "pointer": "/answer", "expected": 42}],
                     "negative_controls": [], "reproduces": None, "oracle": {"description": "Explicit synthetic expected value", "source_refs": []},
                     "provenance": {axis: "" for axis in AXES}}

    def tearDown(self):
        self.tmp.cleanup()

    def plan(self, spec=None, key="plan", **kwargs):
        return plan_verification(self.root, self.cfg, "verify", spec or self.spec, key, clock=self.clock, **kwargs)

    def run_check(self, identifier, key="check", **kwargs):
        return run_verification(self.root, self.cfg, "verify", identifier, key, clock=self.clock, **kwargs)

    def events(self):
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            return store.events("verify")

    def test_plan_does_not_execute_and_success_is_bounded_property_only(self):
        planned = self.plan()
        self.assertEqual(planned["verification"]["status"], "PLANNED")
        self.assertEqual(planned["state"]["assessment"]["claims"][0]["verification"], "UNVERIFIED")
        result = self.run_check(planned["verification_id"])
        evidence = result["verification"]["receipt"]["result"]
        claim = result["state"]["assessment"]["claims"][0]
        self.assertEqual((evidence["method"], evidence["closure"]), ("TEST", "BOUNDED"))
        self.assertEqual(claim["epistemic_status"], "UNKNOWN")
        self.assertEqual(claim["property_evidence"]["epistemic_status"], "SUPPORTED")
        self.assertEqual(claim["property_evidence"]["closure"], "BOUNDED")
        self.assertEqual(claim["prose_entailment"], "NOT_ASSESSED")
        self.assertEqual(claim["blocker"], "EVIDENCE_MISSING")
        self.assertEqual(result["state"]["assessment"]["gaps"][0]["code"], "CLAIM_NOT_VERIFIED")
        self.assertEqual(result["verification"]["plan"]["origins"]["independence"], "NOT_ESTABLISHED")
        self.assertEqual(result["state"]["can_execute_effects"], False)

    def test_wrong_expected_value_refutes_and_conflicting_evidence_is_contested(self):
        yes = self.plan()
        self.run_check(yes["verification_id"])
        wrong = deepcopy(self.spec)
        wrong["checks"][0]["expected"] = 41
        no = self.plan(wrong, key="wrong-plan")
        result = self.run_check(no["verification_id"], key="wrong-check")
        self.assertEqual(result["verification"]["receipt"]["result"]["closure"], "REFUTED")
        claim = result["state"]["assessment"]["claims"][0]
        self.assertEqual(claim["epistemic_status"], "UNKNOWN")
        self.assertEqual(claim["property_evidence"]["epistemic_status"], "CONTESTED")
        self.assertEqual(result["state"]["assessment"]["gaps"][0]["classification"], "CONTESTED")
        self.assertEqual(result["state"]["assessment"]["strategy"], "UNKNOWN")

    def test_observation_records_evidence_without_verifying_claim(self):
        spec = deepcopy(self.spec)
        spec.update(method="OBSERVATION", checks=[])
        result = self.run_check(self.plan(spec)["verification_id"])
        evidence = result["verification"]["receipt"]["result"]
        self.assertEqual(evidence["closure"], "SUPPORTED")
        self.assertEqual(evidence["epistemic_status"], "UNKNOWN")
        self.assertEqual(result["state"]["assessment"]["claims"][0]["verification"], "UNVERIFIED")

    def test_reproduction_performs_second_read_and_binds_original_contract(self):
        identifier = self.plan()["verification_id"]
        self.run_check(identifier)
        spec = deepcopy(self.spec)
        spec.update(method="REPRODUCTION", reproduces=identifier)
        plan = self.plan(spec, key="reproduction-plan")
        from verantyx.verification import _read_input
        with mock.patch("verantyx.verification._read_input", wraps=_read_input) as reader:
            result = self.run_check(plan["verification_id"], key="reproduction-check")
        self.assertEqual(reader.call_count, 1)
        self.assertTrue(result["verification"]["receipt"]["result"]["reproduction_match"])
        bad = deepcopy(spec)
        bad["checks"][0]["expected"] = 7
        with self.assertRaises(LedgerError):
            self.plan(bad, key="bad-reproduction")

    def test_negative_control_actually_checks_counterexamples(self):
        spec = deepcopy(self.spec)
        spec.update(method="NEGATIVE_CONTROL", negative_controls=[{"id": "wrong", "input_base64": base64.b64encode(b'{"answer":41}').decode()}])
        result = self.run_check(self.plan(spec)["verification_id"])
        self.assertTrue(result["verification"]["receipt"]["result"]["negative_controls"][0]["rejected"])
        spec["negative_controls"][0]["input_base64"] = base64.b64encode(b'{"answer":42}').decode()
        result = self.run_check(self.plan(spec, key="bad-control")["verification_id"], key="bad-control-check")
        self.assertEqual(result["verification"]["receipt"]["result"]["closure"], "CONTESTED")

    def test_target_changed_before_run_invalidates_and_refreshes_observation(self):
        identifier = self.plan()["verification_id"]
        (self.root / "report.json").write_text('{"answer":41}')
        result = self.run_check(identifier)
        self.assertFalse(result["ok"])
        self.assertEqual(result["verification"]["receipt"]["reason"], "TARGET_CHANGED")
        self.assertIsNone(result["verification"]["receipt"]["result"])
        self.assertEqual(result["state"]["assessment"]["claims"][0]["verification"], "UNVERIFIED")

    def test_target_changed_during_check_never_yields_valid_evidence(self):
        identifier = self.plan()["verification_id"]
        def mutate(stage):
            if stage == "after_check":
                (self.root / "report.json").write_text('{"answer":0}')
        result = self.run_check(identifier, fault=mutate)
        self.assertEqual(result["verification"]["receipt"]["reason"], "TARGET_CHANGED")

    def test_deleted_symlink_and_oversized_target_fail_closed(self):
        for mode in ("missing", "symlink", "oversized"):
            (self.root / "report.json").write_text('{"answer":42,"ok":true}')
            record_run(self.root, self.cfg, run_id="verify", resume=True, clock=self.clock)
            identifier = self.plan(key="plan-" + mode)["verification_id"]
            (self.root / "report.json").unlink()
            if mode == "symlink":
                (self.root / "report.json").symlink_to(self.root / "proposal.json")
            elif mode == "oversized":
                (self.root / "report.json").write_bytes(b"a" * 65537)
            result = self.run_check(identifier, key="check-" + mode)
            self.assertFalse(result["ok"])
            self.assertEqual(result["verification"]["receipt"]["reason"], "TARGET_UNAVAILABLE")
            (self.root / "report.json").unlink(missing_ok=True)

    def test_expiry_before_and_during_run_and_historical_success(self):
        identifier = self.plan(ttl=1)["verification_id"]
        self.time += timedelta(seconds=1)
        result = self.run_check(identifier)
        self.assertEqual(result["verification"]["receipt"]["reason"], "PLAN_EXPIRED")
        identifier = self.plan(key="second-plan", ttl=1)["verification_id"]
        def expire(stage):
            if stage == "after_check":
                self.time += timedelta(seconds=1)
        result = self.run_check(identifier, key="second-check", fault=expire)
        self.assertEqual(result["verification"]["receipt"]["reason"], "PLAN_EXPIRED")
        identifier = self.plan(key="third-plan", ttl=1)["verification_id"]
        self.run_check(identifier, key="third-check")
        self.time += timedelta(seconds=2)
        result = record_run(self.root, self.cfg, run_id="verify", resume=True, clock=self.clock)
        self.assertEqual(result["state"]["assessment"]["claims"][0]["blocker"], "OBSERVATION_STALE")

    def test_interrupted_run_is_not_retried_and_duplicate_is_inert(self):
        identifier = self.plan()["verification_id"]
        def crash(stage):
            if stage == "after_start":
                raise RuntimeError("simulated crash")
        with self.assertRaises(RuntimeError):
            self.run_check(identifier, fault=crash)
        with mock.patch("verantyx.verification._read_input", side_effect=AssertionError("automatic retry")):
            result = self.run_check(identifier)
            duplicate = self.run_check(identifier)
        self.assertEqual(result["verification"]["status"], "OUTCOME_UNKNOWN")
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(result["projection_hash"], duplicate["projection_hash"])
        with self.assertRaises(LedgerError):
            self.run_check(identifier, key="different-key")

    def test_replay_and_archive_do_not_read_external_files(self):
        result = self.run_check(self.plan()["verification_id"])
        events = self.events()
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            bundle = store.export().encode()
        (self.root / "report.json").unlink()
        with mock.patch("verantyx.verification._read_input", side_effect=AssertionError("replay read")), mock.patch("verantyx.verification.engine_identity", side_effect=AssertionError("replay identity")):
            self.assertEqual(projection(replay(events))["projection_hash"], result["projection_hash"])
            parse_archive(bundle)
            with EventStore(self.root, self.cfg["project"]["id"], create=True) as store:
                archive = store.import_archive(bundle, "2026-09-06T00:00:00.000000Z")
            archive_view = list_verifications(self.root, self.cfg, "verify", archive["archive_id"])
        self.assertEqual(archive_view["trust"], "ARCHIVE_ONLY")

    def test_forged_receipt_claim_plan_or_proof_is_rejected_even_with_valid_event_hash(self):
        self.run_check(self.plan()["verification_id"])
        events = self.events()
        index = next(i for i, event in enumerate(events) if event["type"] == "VerificationRecorded")
        for mutation in ("passed", "proved", "hash", "result_field"):
            forged = deepcopy(events[index])
            if mutation == "passed":
                forged["payload"]["result"]["checks"][0]["passed"] = False
            elif mutation == "proved":
                forged["payload"]["result"]["closure"] = "PROVED"
            elif mutation == "hash":
                forged["payload"]["plan_hash"] = "f" * 64
            else:
                forged["payload"]["result"]["approved"] = True
            forged["event_hash"] = digest({k: v for k, v in forged.items() if k != "event_hash"})
            with self.assertRaises(LedgerError):
                replay([*events[:index], forged])

    def test_model_proposals_and_declared_independence_cannot_grant_verification(self):
        for key, value in (("approved", True), ("closure", "PROVED"), ("authority", "human")):
            spec = deepcopy(self.spec)
            spec[key] = value
            with self.assertRaises(LedgerError):
                self.plan(spec)
        spec = deepcopy(self.spec)
        spec["provenance"] = {axis: "independent" for axis in AXES}
        result = self.run_check(self.plan(spec)["verification_id"])
        self.assertEqual(result["verification"]["plan"]["origins"]["independence"], "NOT_ESTABLISHED")
        events = self.events()
        planned = next(i for i, event in enumerate(events) if event["type"] == "VerificationPlanned")
        forged = deepcopy(events[planned])
        forged["actor_kind"] = "recorded_proposal"
        forged["event_hash"] = digest({k: v for k, v in forged.items() if k != "event_hash"})
        with self.assertRaises(LedgerError):
            replay([*events[:planned], forged])

    def test_registered_predicates_are_strict_and_invalid_json_is_rejected(self):
        checks = [{"id": "test", "kind": "json.equals", "pointer": "/ok", "expected": 1}]
        self.assertFalse(check_input(b'{"ok":true}', checks)[0]["passed"])
        for raw in (b'{"ok":1,"ok":2}', b'{"ok":NaN}', b'not json'):
            self.assertFalse(check_input(raw, checks)[0]["passed"])
        check = {"id": "p", "kind": "json.equals", "pointer": "/a~1b/~0key/0", "expected": "yes"}
        self.assertTrue(check_input(b'{"a/b":{"~key":["yes"]}}', [check])[0]["passed"])
        spec = deepcopy(self.spec)
        spec["checks"][0]["kind"] = "shell"
        with self.assertRaises(LedgerError):
            validate_spec(spec)

    def test_proposal_replacement_invalidates_planned_verification(self):
        identifier = self.plan()["verification_id"]
        state = replay(self.events())
        proposal = deepcopy(state["proposal"])
        proposal["context_revision"] = state["revision"]
        proposal["claims"][0]["statement"] = "A different claim."
        (self.root / "proposal.json").write_text(json.dumps(proposal))
        record_run(self.root, self.cfg, run_id="verify", resume=True, proposal_path=self.root / "proposal.json", clock=self.clock)
        result = self.run_check(identifier)
        self.assertEqual(result["verification"]["receipt"]["reason"], "PROPOSAL_CHANGED")
        self.assertEqual(result["state"]["assessment"]["claims"][0]["verification"], "UNVERIFIED")

    def test_oracle_source_change_invalidates_evidence_and_declared_refs_are_checked(self):
        (self.root / "oracle.txt").write_text("Expected answer: 42")
        result = record_run(self.root, self.cfg, run_id="verify", resume=True, observe_paths=["oracle.txt"], clock=self.clock)
        spec = deepcopy(self.spec)
        spec["oracle"]["source_refs"] = [result["state"]["latest_observations"]["oracle.txt"]]
        self.run_check(self.plan(spec)["verification_id"])
        (self.root / "oracle.txt").write_text("Expected answer: 41")
        result = record_run(self.root, self.cfg, run_id="verify", resume=True, clock=self.clock)
        self.assertEqual(result["state"]["assessment"]["claims"][0]["blocker"], "OBSERVATION_STALE")
        spec["oracle"]["source_refs"] = ["invented-ref"]
        with self.assertRaises(LedgerError):
            self.plan(spec, key="bad-oracle")

    def test_oracle_change_before_execution_is_observed_without_resume(self):
        (self.root / "oracle.txt").write_text("Expected answer: 42")
        view = record_run(self.root, self.cfg, run_id="verify", resume=True, observe_paths=["oracle.txt"], clock=self.clock)
        spec = deepcopy(self.spec)
        spec["oracle"]["source_refs"] = [view["state"]["latest_observations"]["oracle.txt"]]
        identifier = self.plan(spec)["verification_id"]
        (self.root / "oracle.txt").write_text("Expected answer: 0")
        result = self.run_check(identifier)
        self.assertEqual(result["verification"]["receipt"]["reason"], "ORACLE_CHANGED")
        self.assertFalse(result["ok"])

    def test_engine_changes_do_not_run_and_invalid_specs_do_not_read(self):
        identifier = self.plan()["verification_id"]
        with mock.patch("verantyx.verification.engine_identity", return_value={"changed": True}), mock.patch("verantyx.verification._read_input", side_effect=AssertionError("changed engine executed")):
            result = self.run_check(identifier)
        self.assertEqual(result["verification"]["receipt"]["reason"], "ENGINE_CHANGED")
        for path in ("../outside", "/etc/passwd", ".verantyx/state.db", ".git/config"):
            spec = deepcopy(self.spec)
            spec["target_path"] = path
            with self.assertRaises(LedgerError):
                self.plan(spec, key="invalid-scope")
        spec = deepcopy(self.spec)
        spec["target_path"] = "proposal.json"
        with self.assertRaises(LedgerError):
            self.plan(spec, key="ungranted-file")

    def test_each_registered_predicate_has_positive_and_negative_examples(self):
        import hashlib
        vectors = [
            ("bytes.sha256", "", b"hello", hashlib.sha256(b"hello").hexdigest(), "f" * 64),
            ("bytes.size", "", b"hello", 5, 4),
            ("text.equals", "", "日本語".encode(), "日本語", "英語"),
            ("text.contains", "", b"alpha beta", "beta", "gamma"),
            ("json.type", "/answer", b'{"answer":42}', "integer", "boolean"),
            ("json.equals", "/answer", b'{"answer":42}', 42, 41),
        ]
        for kind, pointer, raw, yes, no in vectors:
            with self.subTest(kind=kind):
                check = {"id": "property", "kind": kind, "pointer": pointer, "expected": yes}
                self.assertTrue(check_input(raw, [check])[0]["passed"])
                check["expected"] = no
                self.assertFalse(check_input(raw, [check])[0]["passed"])

    def test_plan_idempotency_and_invalid_revision_preserve_contract(self):
        first = self.plan()
        with mock.patch("verantyx.verification._read_input", side_effect=AssertionError("duplicate planning read")):
            second = self.plan()
        self.assertTrue(second["duplicate"])
        self.assertEqual(first["plan_hash"], second["plan_hash"])
        with self.assertRaises(LedgerError) as error:
            self.plan(key="stale-revision", expected_revision=0)
        self.assertEqual(error.exception.code, "REVISION_CONFLICT")
        changed = deepcopy(self.spec)
        changed["checks"][0]["expected"] = 41
        with self.assertRaises(LedgerError) as error:
            self.plan(changed)
        self.assertEqual(error.exception.code, "IDEMPOTENCY_CONFLICT")
