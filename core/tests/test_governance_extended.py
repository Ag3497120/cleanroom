"""Real task shadow observations, finite scope boundaries and authority regressions."""
import argparse
from contextlib import redirect_stdout
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
from unittest import mock
import unittest
import uuid

from test_constitution import Fixture, proposal, SCOPE, PRECEDENT
from verantyx import commands_governance, i18n
from verantyx.application import record_run
from verantyx.adapters.cross_policy import CrossPolicyBackend
from verantyx.domain.codec import digest
from verantyx.domain.events import make_event
from verantyx.domain.rule_extensions import exact_policy, validate_policy
from verantyx.effects import authorize, execute
from verantyx.errors import LedgerError
from verantyx.governance import policy_report
from verantyx.kernel.reducer import projection, replay
from verantyx.kernel.rules import catalog
from verantyx.storage.sqlite import EventStore, parse_archive


class ExtendedFixture(Fixture):
    def draft(self, task="first", choice="isolate"):
        self.run_task(task)
        case = self.command("decide", task, point_id="separation", choice=choice, reason="人工検査の判断")["precedent_id"]
        self.command("precedent-accept", case)
        return self.command("rule-draft", case)["rule_id"]

    def finite(self, rule, minimum=2, exception=False):
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            original = catalog(store.events())[rule]["scope"]
        policy = exact_policy(original, minimum)
        policy["scope"]["component"] = ["compiler", "writer"]
        policy["scope"]["workload"] = ["batch", "parallel"]
        if exception:
            policy["exceptions"] = [{"id": "batch-exception", "scope": {**original, "component": "compiler", "workload": "batch"},
                                      "reason": "人工検査で明示的に別判断を要求"}]
        return policy

    def accepted_policy(self, rule, policy):
        result = self.command("rule-policy-propose", rule, policy=policy, reason="有限の範囲を確認する", key="propose-" + rule)
        self.assertEqual(result["policy_sha256"], digest(policy))
        accepted = self.command("rule-policy-accept", rule, expected_policy_sha256=digest(policy), reason="変更案の内容を確認", key="accept-" + rule)
        self.assertEqual(accepted["rule"]["enforcement"], "OFF")
        self.command("rule-shadow", rule)

    def pilot(self, run_id, component="writer", workload="parallel", choice="isolate"):
        view = self.run_task(run_id, context={**SCOPE, "component": component, "workload": workload})
        self.assertIsNotNone(view["state"]["assessment"]["question"])
        return self.command("decide", run_id, point_id="separation", choice=choice, reason="人工検査用の個別判断")

    def activate_finite(self, exception=False, minimum=1):
        rule = self.draft()
        policy = self.finite(rule, minimum, exception)
        self.accepted_policy(rule, policy)
        for index in range(minimum):
            self.pilot("pilot-" + str(index))
        self.command("rule-policy-confirm", rule, expected_policy_sha256=digest(policy), reason="実タスクの観測を確認")
        self.command("rule-enforce", rule, expected_policy_sha256=digest(policy), enforcement="BLOCK", reason="この範囲に適用")
        return rule, policy

    def report(self, rule):
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            return policy_report(store, rule)


class FiniteGovernanceTests(ExtendedFixture):
    def test_policy_change_needs_a_separate_reviewed_hash_and_resets_enforcement(self):
        rule, _ = self.promote()
        policy = self.finite(rule)
        first = self.command("rule-policy-propose", rule, policy=policy, reason="限定的に広げる", key="proposal")
        repeat = self.command("rule-policy-propose", rule, policy=policy, reason="限定的に広げる", key="proposal")
        self.assertEqual(first["policy_sha256"], repeat["policy_sha256"])
        self.assertTrue(repeat["duplicate"])
        self.assertEqual(self.run_task("still-exact")["state"]["assessment"]["judgments"][0]["status"], "PRECEDENT_MATCHED")
        self.assertIsNotNone(self.run_task("still-outside", context={**SCOPE, "component": "compiler"})["state"]["assessment"]["question"])
        with self.assertRaises(LedgerError) as error:
            self.command("rule-policy-accept", rule, expected_policy_sha256="0" * 64, reason="別内容")
        self.assertEqual(error.exception.code, "RULE_POLICY_CHANGED")
        accepted = self.command("rule-policy-accept", rule, expected_policy_sha256=digest(policy), reason="内容を確認")
        self.assertEqual((accepted["rule"]["enforcement"], accepted["rule"]["maturity"]), ("OFF", "DRAFT"))
        with self.assertRaises(LedgerError):
            self.command("rule-activate", rule)

    def test_scope_dsl_rejects_project_risk_type_wildcards_and_outside_exceptions(self):
        rule = self.draft()
        policy = self.finite(rule)
        original = self.report(rule)["rule"]["scope"]
        mutations = []
        for key, value in (("project_id", str(uuid.uuid4())), ("risk", "LOW"), ("decision_type", "different")):
            item = deepcopy(policy)
            item["scope"][key] = [value]
            mutations.append(item)
        item = deepcopy(policy)
        item["scope"]["component"] = ["*"]
        mutations.append(item)
        item = deepcopy(policy)
        item["exceptions"] = [{"id": "escape", "scope": {**original, "component": "outside"}, "reason": "無関係"}]
        mutations.append(item)
        item = deepcopy(policy)
        item["approved"] = True
        mutations.append(item)
        for candidate in mutations:
            with self.subTest(policy=candidate), self.assertRaises(LedgerError):
                self.command("rule-policy-propose", rule, policy=candidate, reason="不正な範囲")
        self.assertEqual(self.report(rule)["rule"]["enforcement"], "OFF")

    def test_actual_cross_covers_every_finite_cell_and_all_five_outside_axes(self):
        rule = self.draft()
        policy = self.finite(rule, exception=True)
        check = self.backend.shadow_policy_check(policy)
        self.assertEqual(len(check["cases"]), 9)
        self.assertEqual(check["closure"], "BOUNDED")
        self.assertEqual(sum(case["expected"] for case in check["cases"]), 3)
        self.assertTrue(all("witness" in case["receipt"] for case in check["cases"]))
        self.assertEqual(check["origin"]["independent_design"], False)
        mutant = self.root / "mutant.cross"
        mutant.write_text(self.backend.program.decode().replace('「規則_risk」と「対象_risk」が等しいか', '「規則_risk」と「規則_risk」が等しいか'))
        with self.assertRaises(LedgerError) as error:
            CrossPolicyBackend(program=mutant).shadow_policy_check(policy)
        self.assertEqual(error.exception.code, "CROSS_DISAGREEMENT")

    def test_live_shadow_needs_distinct_tasks_and_no_automatic_promotion(self):
        rule = self.draft()
        policy = self.finite(rule)
        self.accepted_policy(rule, policy)
        for operation in ("rule-confirm", "rule-activate"):
            with self.assertRaises(LedgerError):
                self.command(operation, rule)
        self.pilot("pilot-one")
        for _ in range(3):
            record_run(self.root, self.cfg, run_id="pilot-one", resume=True, clock=self.clock, backend=self.backend)
        with self.assertRaises(LedgerError) as error:
            self.command("rule-policy-confirm", rule, expected_policy_sha256=digest(policy), reason="まだ一件")
        self.assertEqual(error.exception.code, "RULE_SHADOW_INSUFFICIENT")
        self.pilot("pilot-two", component="compiler")
        self.assertEqual(self.report(rule)["rule"]["enforcement"], "SHADOW")
        confirmed = self.command("rule-policy-confirm", rule, expected_policy_sha256=digest(policy), reason="二件の判断を確認")
        self.assertEqual(confirmed["rule"]["enforcement"], "SHADOW")
        self.assertEqual(len(confirmed["rule"]["shadow_review_refs"]), 2)
        self.command("rule-enforce", rule, expected_policy_sha256=digest(policy), enforcement="BLOCK", reason="二件を確認して適用")
        third = self.run_task("third", context={**SCOPE, "component": "compiler", "workload": "batch"})
        self.assertEqual(third["state"]["assessment"]["judgments"][0]["status"], "PRECEDENT_MATCHED")
        self.assertIsNone(third["state"]["assessment"]["question"])

    def test_shadow_conflict_is_recorded_and_prevents_promotion(self):
        rule = self.draft()
        policy = self.finite(rule, minimum=1)
        self.accepted_policy(rule, policy)
        self.pilot("disagree", choice="shared")
        self.assertIn("HUMAN_DISAGREEMENT", self.report(rule)["outcomes"])
        with self.assertRaises(LedgerError) as error:
            self.command("rule-policy-confirm", rule, expected_policy_sha256=digest(policy), reason="不一致を無視")
        self.assertEqual(error.exception.code, "RULE_SHADOW_CONFLICT")

    def test_shadow_records_rule_to_rule_conflicts(self):
        first = self.draft("first", choice="isolate")
        second = self.draft("second", choice="shared")
        self.command("rule-shadow", first)
        self.command("rule-shadow", second)
        self.run_task("overlap")
        self.assertIn("RULE_CONFLICT", self.report(first)["outcomes"])
        self.assertIn("RULE_CONFLICT", self.report(second)["outcomes"])

    def test_extended_rule_amendment_requires_review_and_preserves_superseded_history(self):
        old, policy = self.activate_finite()
        case = self.command("rule-amend", old, choice="shared", reason="人工検査の方針変更")["precedent_id"]
        self.command("precedent-accept", case)
        new = self.command("rule-draft", case)["rule_id"]
        self.accepted_policy(new, policy)
        self.run_task("amend-pilot")
        judged = self.command("decide", "amend-pilot", point_id="separation", choice="shared", reason="後継規則の判断を確認")
        self.assertEqual(judged["state"]["assessment"]["judgments"][0]["reason"], "RULE_CONFLICT")
        self.assertIn("SUPERSESSION_REVIEW", self.report(new)["outcomes"])
        self.command("rule-policy-confirm", new, expected_policy_sha256=digest(policy), reason="宣言した旧規則との違いを確認")
        self.command("rule-enforce", new, expected_policy_sha256=digest(policy), enforcement="WARN", reason="後継を受理")
        self.command("rule-enforce", new, expected_policy_sha256=digest(policy), enforcement="BLOCK", reason="後継を適用")
        self.assertEqual(self.report(old)["rule"]["validity"], "SUPERSEDED")
        view = self.run_task("after-amend")
        self.assertEqual(view["state"]["assessment"]["judgments"][0]["choice"], "shared")
        self.assertGreater(len(self.report(old)["rule"]["history"]), 4)

    def test_warn_preserves_choice_and_records_disagreement_without_granting_authority(self):
        rule = self.draft()
        policy = self.finite(rule, minimum=1)
        self.accepted_policy(rule, policy)
        self.pilot("pilot")
        self.command("rule-policy-confirm", rule, expected_policy_sha256=digest(policy), reason="確認")
        self.command("rule-enforce", rule, expected_policy_sha256=digest(policy), enforcement="WARN", reason="助言として適用")
        undecided = self.run_task("warn")
        self.assertIsNotNone(undecided["state"]["assessment"]["question"])
        decided = self.command("decide", "warn", point_id="separation", choice="shared", reason="このタスクでは共有を選択")
        judgment = decided["state"]["assessment"]["judgments"][0]
        self.assertEqual((judgment["status"], judgment["choice"]), ("HUMAN_DECIDED", "shared"))
        self.assertEqual(judgment["advisories"][0]["outcome"], "HUMAN_DISAGREEMENT")
        with self.assertRaises(LedgerError) as error:
            self.command("rule-enforce", rule, expected_policy_sha256=digest(policy), enforcement="BLOCK", reason="警告中の不一致を無視")
        self.assertEqual(error.exception.code, "RULE_SHADOW_CONFLICT")

    def test_exceptions_and_outside_scopes_are_observed_and_never_expand_authority(self):
        rule, policy = self.activate_finite(exception=True)
        excluded = self.run_task("except", context={**SCOPE, "component": "compiler", "workload": "batch"})
        self.assertEqual(excluded["state"]["assessment"]["judgments"][0]["reason"], "RULE_EXCEPTION_APPLIES")
        self.assertIsNotNone(excluded["state"]["assessment"]["question"])
        allowed = self.run_task("inside", context={**SCOPE, "component": "compiler"})
        self.assertEqual(allowed["state"]["assessment"]["judgments"][0]["status"], "PRECEDENT_MATCHED")
        for axis, value in (("component", "other"), ("workload", "other"), ("risk", "LOW")):
            view = self.run_task("outside-" + axis, context={**SCOPE, axis: value})
            self.assertIsNotNone(view["state"]["assessment"]["question"])
        rows = self.report(rule)["observations"]
        exception = next(row for row in rows if row["run_id"] == "except")
        self.assertEqual(exception["exception_ids"], ["batch-exception"])
        self.assertEqual(exception["outcome"], "EXEMPTED")
        self.assertEqual(len([row for row in rows if row["outcome"] == "OUT_OF_SCOPE"]), 3)

    def test_same_option_id_cannot_change_a_human_decision_or_rule_meaning(self):
        first = self.run_task("human")
        decided = self.command("decide", "human", point_id="separation", choice="isolate", reason="表示した選択肢を判断")
        changed = proposal("human", revision=decided["recorded_revision"])
        changed["decision_points"][0]["options"][0]["label"] = "共有場所へ破壊的に書き込む"
        path = self.root.parent / ("changed-" + uuid.uuid4().hex + ".json")
        try:
            path.write_text(json.dumps(changed))
            result = record_run(self.root, self.cfg, run_id="human", resume=True, proposal_path=path, clock=self.clock, backend=self.backend)
            self.assertIsNotNone(result["state"]["assessment"]["question"])
        finally:
            path.unlink()
        self.promote("rule-owner")
        changed = proposal("different-meaning")
        changed["decision_points"][0]["options"][1]["label"] = "選ばれなかった選択肢の意味も変更"
        result = self.run_task("different-meaning", changed)
        self.assertEqual(result["state"]["assessment"]["judgments"][0]["reason"], "RULE_OPTION_CHANGED")

    def test_legacy_unbound_human_note_stays_readable_but_cannot_approve_a_later_proposal(self):
        from verantyx.application import iso
        start = record_run(self.root, self.cfg, request="旧記録の人工例", run_id="note", context=SCOPE, clock=self.clock)
        with EventStore(self.root, self.cfg["project"]["id"], create=True) as store:
            previous = store.events("note")
            command_id = str(uuid.uuid4())
            note = make_event(store.project_id, "note", len(previous) + 1, command_id, iso(self.clock()), "HumanDecisionRecorded",
                              {"point_id": "separation", "choice": "isolate", "scope": {"project_id": store.project_id, **SCOPE, "decision_type": "parallel_writers"},
                               "reason": "選択肢が固定されていない旧記録"}, str(uuid.uuid4()), previous[-1])
            evaluation = make_event(store.project_id, "note", len(previous) + 2, command_id, iso(self.clock()), "EvaluationRecorded",
                                    {"as_of": iso(self.clock()), "evaluator": "m1.v1"}, str(uuid.uuid4()), note)
            store.append("note", digest("note"), "note", len(previous), [note, evaluation])
            state = replay(store.events("note"))
        self.assertEqual(state["human_decisions"]["separation"]["binding"], "UNBOUND_HISTORY")
        path = self.root.parent / ("note-" + uuid.uuid4().hex + ".json")
        try:
            path.write_text(json.dumps(proposal("note", revision=state["revision"])))
            result = record_run(self.root, self.cfg, run_id="note", resume=True, proposal_path=path, clock=self.clock, backend=self.backend)
        finally:
            path.unlink()
        self.assertIsNotNone(result["state"]["assessment"]["question"])

    def test_a_later_local_choice_cannot_silently_override_block(self):
        rule, _ = self.promote()
        self.run_task("override")
        result = self.command("decide", "override", point_id="separation", choice="shared", reason="反対の選択")
        self.assertEqual(result["state"]["assessment"]["judgments"][0]["reason"], "RULE_CONFLICT")
        self.assertEqual(self.report(rule)["rule"]["enforcement"], "BLOCK")

    def test_forged_match_inputs_are_rejected_and_new_history_replays_without_io(self):
        rule, _ = self.activate_finite()
        self.run_task("recorded", context={**SCOPE, "component": "compiler"})
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            events = store.events("recorded")
            archive = store.export().encode()
        self.assertEqual(len(parse_archive(archive)["events"]), sum(1 for line in archive.splitlines()) - 2)
        expected = projection(replay(events))
        with mock.patch("builtins.open", side_effect=AssertionError("I/O")), mock.patch("subprocess.run", side_effect=AssertionError("process")), \
             mock.patch("uuid.uuid4", side_effect=AssertionError("random")), mock.patch("time.time", side_effect=AssertionError("clock")):
            self.assertEqual(projection(replay(events)), expected)
        bad = deepcopy(events)
        index = next(i for i, event in enumerate(bad) if event["type"] == "PolicyContextRecorded")
        bad[index]["payload"]["matches"]["separation"][rule]["target"]["component"] = "writer"
        bad[index]["event_hash"] = digest({key: value for key, value in bad[index].items() if key != "event_hash"})
        with self.assertRaises(LedgerError):
            replay(bad[:index + 1])

    def test_all_five_language_command_displays_and_parser_dispatch(self):
        rule = self.draft()
        parser = argparse.ArgumentParser()
        commands_governance.register(parser.add_subparsers(dest="command", required=True))
        args = parser.parse_args(["rule-policy-template", rule, "--minimum-shadow-tasks", "3"])
        policy = commands_governance.dispatch(self.root, self.cfg, args, "ja")
        self.assertEqual(policy["minimum_shadow_tasks"], 3)
        translations = json.loads((Path(__file__).parents[1] / "docs/governance-locales.json").read_text())
        args = parser.parse_args(["rule-shadow-report", rule])
        report = commands_governance.dispatch(self.root, self.cfg, args, "ja")
        for locale in i18n.LANGUAGES:
            with mock.patch.dict(i18n.catalog(locale), translations[locale]), redirect_stdout(StringIO()) as output:
                commands_governance.display(report, locale, args.command)
                self.assertIn(translations[locale]["governance.title"], output.getvalue())

    @unittest.skipUnless(PRECEDENT, "set VERANTYX_PRECEDENT")
    def test_extended_block_runs_actual_isolated_writer_and_preserves_canonical(self):
        self.init_git()
        before = (self.root / "calc.py").read_bytes()
        rule, _ = self.activate_finite()
        self.run_task("writer-job", proposal("writer-job", action=True), context={**SCOPE, "component": "compiler"})
        lease = authorize(self.root, self.cfg, "writer-job", "writer", PRECEDENT, "permit", clock=self.clock, backend=self.backend)
        result = execute(self.root, self.cfg, "writer-job", lease["lease_id"], PRECEDENT, "execute", clock=self.clock, backend=self.backend)
        self.assertEqual(result["execution"]["status"], "CANDIDATE_TESTED")
        self.assertEqual(result["execution"]["receipt"]["verification"]["closure"], "BOUNDED")
        self.assertEqual((self.root / "calc.py").read_bytes(), before)

    @unittest.skipUnless(PRECEDENT, "set VERANTYX_PRECEDENT")
    def test_shadow_and_warn_do_not_authorize_effects(self):
        self.init_git()
        rule = self.draft()
        self.command("rule-shadow", rule)
        for stage in ("SHADOW", "WARN"):
            if stage == "WARN":
                self.command("rule-confirm", rule)
                self.command("rule-enforce", rule, enforcement="WARN", reason="助言のみ")
            self.run_task(stage, proposal(stage, action=True))
            with self.assertRaises(LedgerError) as error:
                authorize(self.root, self.cfg, stage, "writer", PRECEDENT, "auth-" + stage, clock=self.clock, backend=self.backend)
            self.assertEqual(error.exception.code, "EXECUTION_BLOCKED")
        self.assertFalse((self.root / ".verantyx/worktrees").exists())


if __name__ == "__main__":
    unittest.main()
