"""Exact-scope policies over real, deterministic verification contracts."""
from datetime import datetime, timezone
import unittest

import test_verification as verification_fixtures
from test_personal_skills_mvp import MVPFixture
from verantyx.application import record_run
from verantyx.assets import project_assets
from verantyx.errors import LedgerError
from verantyx.learning import control_learning, project_learning
from verantyx.personal_skills import read_state, stack
from verantyx.skill_policy import policy_snapshot, reuse, route, set_policy


class SkillPolicyMVPTests(MVPFixture):
    fixture_type = verification_fixtures.VerificationTests

    def setUp(self):
        super().setUp()
        # The existing fixture uses a historic clock; refresh its observed bytes.
        self.h.time = datetime.now(timezone.utc)
        record_run(self.root, self.cfg, run_id="verify", resume=True,
                   observe_paths=["report.json"], clock=self.h.clock)
        planned = self.h.plan()
        verified = self.h.run_check(planned["verification_id"])
        self.method = project_assets(verified["state"])["verification_methods"][0]
        self.candidate = self.raise_skill("verify")
        self.values = dict(candidate_id=self.candidate, asset_id=self.method["id"],
                           claim_id="answer", target_path="report.json")

    def policy(self, **changes):
        values = dict(candidate_id=self.candidate, ai_mode="check", reuse_mode="auto-check",
                      paths=["report.json"], asset_ids=[self.method["id"]], reason="Explicit fixture scope",
                      key="policy", expected_policy_revision=0)
        values.update(changes)
        return set_policy(self.root, self.cfg, "verify", **values)

    def route(self, **changes):
        return route(self.root, self.cfg, "verify", **{**self.values, **changes})

    def execute(self, scope, **changes):
        values = dict(self.values, scope_id=scope, key="reuse", execute=True)
        values.update(changes)
        return reuse(self.root, self.cfg, "verify", **values)

    def test_default_deny_and_ownership_are_independent_of_ai_policy(self):
        for target in ("OWN", "DELEGATE"):
            control_learning(self.root, self.cfg, "verify", "target", candidate_id=self.candidate,
                             target=target, reason="Learning ownership only")
            decision = self.route()
            self.assertEqual((decision["status"], decision["reason"]), ("UNKNOWN", "POLICY_REQUIRED"))
            self.assertFalse(decision["execution_authorized"])
        before = self.events()
        self.policy()
        self.assertEqual(self.events(), before)
        for target in ("OWN", "DELEGATE"):
            control_learning(self.root, self.cfg, "verify", "target", candidate_id=self.candidate,
                             target=target, reason="Keep the same independent AI policy")
            decision = self.route()
            self.assertEqual(decision["status"], "READY")
            self.assertEqual(decision["ownership_target"], target)
            self.assertFalse(decision["execution_performed"])
            self.assertEqual(decision["model_calls"], 0)
        item = next(row for row in project_learning(read_state(self.root, self.cfg, "verify")) if row["id"] == self.candidate)
        self.assertEqual(item["mastery_assessment"], "NOT_ASSESSED")
        view = stack(self.root, self.cfg, run_ids=["verify"])
        item = next(row for row in view["works"][0]["skills"] if row["id"] == self.candidate)
        self.assertEqual(item["ai_policy"]["policy_id"], decision["policy"]["policy_id"])

    def test_cli_policy_is_idempotent_revision_guarded_and_exact_scope(self):
        args = ("skills-policy-set", "verify", "--candidate", self.candidate, "--ai-mode", "check",
                "--reuse-mode", "auto-check", "--path", "report.json", "--asset", self.method["id"],
                "--reason", "Explicit fixture scope", "--key", "cli-policy", "--expected-policy-revision", "0")
        first = self.cli(*args)
        duplicate = self.cli(*args)
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(first["policy_id"], duplicate["policy_id"])
        self.assertEqual(self.cli("skills-policies", "--run", "verify")["revision"], 1)
        with self.assertRaises(LedgerError) as error:
            self.policy(key="stale-policy")
        self.assertEqual(error.exception.details["reason"], "SKILL_POLICY_REVISION_CHANGED")
        with self.assertRaises(LedgerError) as error:
            self.policy(key="cli-policy", ai_mode="explain")
        self.assertEqual(error.exception.details["reason"], "SKILL_POLICY_IDEMPOTENCY_CONFLICT")
        before = self.events()
        for changes in ({"target_path": "report.json.backup"}, {"asset_id": "other-contract"}):
            with self.subTest(changes=changes):
                decision = self.route(**changes)
                self.assertEqual((decision["status"], decision["reason"]), ("BLOCKED", "OUTSIDE_EXPLICIT_SCOPE"))
                self.assertIsNone(decision["scope"])
        with self.assertRaises(LedgerError) as error:
            self.route(claim_id="unrecorded-claim")
        self.assertEqual(error.exception.details["reason"], "SKILL_ROUTE_CLAIM_NOT_FOUND")
        self.assertEqual(self.events(), before)
        self.assertEqual(policy_snapshot(self.root, self.cfg)["revision"], 1)

    def test_explain_and_propose_do_not_execute_a_contract(self):
        for index, (mode, status) in enumerate((("explain", "REFERENCE_ONLY"), ("propose", "PLAN_ONLY"))):
            self.policy(ai_mode=mode, key=mode, expected_policy_revision=index)
            decision = self.route()
            self.assertEqual(decision["status"], status)
            before = self.events()
            with self.assertRaises(LedgerError) as error:
                self.execute(decision["scope"]["id"] if decision["scope"] else "0" * 64, key=mode)
            self.assertEqual(error.exception.details["reason"], "SKILL_REUSE_NOT_ALLOWED")
            self.assertEqual(self.events(), before)

    def test_confirm_requires_the_exact_scope_and_a_human_reason(self):
        self.policy(reuse_mode="confirm")
        scope = self.route()["scope"]["id"]
        before = self.events()
        for options, reason in (({}, "SKILL_REUSE_CONFIRMATION_REQUIRED"),
                                ({"confirm_scope": "0" * 64}, "SKILL_REUSE_CONFIRMATION_REQUIRED"),
                                ({"confirm_scope": scope}, "SKILL_REUSE_JUDGMENT_REASON_REQUIRED")):
            with self.subTest(reason=reason), self.assertRaises(LedgerError) as error:
                self.execute(scope, **options)
            self.assertEqual(error.exception.details["reason"], reason)
        self.assertEqual(self.events(), before)
        result = self.execute(scope, confirm_scope=scope, judgment_reason="Run only the selected finite check")
        self.assertTrue(result["ok"])
        self.assertEqual(result["model_calls"], 0)

    def test_route_context_freezes_target_bytes_before_execution(self):
        self.policy()
        scope = self.route()["scope"]["id"]
        before = self.events()
        (self.root / "report.json").write_text('{"answer":0,"ok":true}')
        with self.assertRaises(LedgerError):
            self.execute(scope)
        self.assertEqual(self.events(), before)

    def test_cli_reuse_runs_real_contract_once_without_models_or_rewriting(self):
        self.policy()
        args = ("verify", "--candidate", self.candidate, "--asset", self.method["id"],
                "--claim", "answer", "--target", "report.json")
        decision = self.cli("skills-route", *args)
        original_checks = decision["method"]["spec"]["checks"]
        execution = ("skills-reuse", *args, "--scope-id", decision["scope"]["id"], "--key", "cli-reuse", "--execute")
        result = self.cli(*execution)
        self.assertTrue(result["ok"])
        self.assertEqual(result["workflow"]["status"], "COMPLETED")
        self.assertEqual(result["workflow"]["results"][0]["closure"], "BOUNDED")
        self.assertEqual(result["workflow"]["plan"]["steps"][0]["spec"]["checks"], original_checks)
        self.assertEqual(result["model_calls"], 0)
        self.assertFalse(result["source_method_rewritten"])
        self.assertFalse(result["authority_granted"])
        before = self.events()
        (self.root / "report.json").write_text('{"answer":0}')
        duplicate = self.cli(*execution)
        self.assertTrue(duplicate["duplicate"])
        self.assertTrue(duplicate["historical_receipt"])
        self.assertFalse(duplicate["execution_performed"])
        self.assertEqual(duplicate["workflow"], result["workflow"])
        self.assertEqual(self.events(), before)

    def test_failed_target_is_refuted_without_weakening_recorded_expectation(self):
        self.policy()
        (self.root / "report.json").write_text('{"answer":0,"ok":true}')
        record_run(self.root, self.cfg, run_id="verify", resume=True, observe_paths=["report.json"])
        decision = self.route()
        result = self.execute(decision["scope"]["id"])
        self.assertFalse(result["ok"])
        self.assertEqual(result["workflow"]["status"], "REFUTED")
        self.assertEqual(result["workflow"]["plan"]["steps"][0]["spec"]["checks"][0]["expected"], 42)
        self.assertEqual(result["automatic_repairs"], 0)
        self.assertEqual(result["model_calls"], 0)


if __name__ == "__main__":
    unittest.main()
