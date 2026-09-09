"""Recorded human choices reach both generators and cannot reuse an older edit.

All decisions and model responses here are artificial; actual Cross and
Precedent execute only in the fixture's temporary Git project.
"""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import os
from types import SimpleNamespace
import unittest

import test_candidate_decisions_v064 as fixtures
from verantyx.application import dispatch, get_projection
from verantyx.cli import parse
from verantyx.commands_context import dispatch as context_view, display
from verantyx.coordination import coordinate, stage_candidate
from verantyx.decision_context import snapshot
from verantyx.domain.codec import digest
from verantyx.effects import authorize, execute
from verantyx.errors import LedgerError
from verantyx.i18n import text
from verantyx.shared_context import append
from verantyx.storage.sqlite import EventStore


class DecisionContextTests(unittest.TestCase):
    def setUp(self):
        self.case = fixtures.CandidateDecisionTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.root, self.cfg = self.case.root, self.case.cfg
        self.initial = self.case.workflow()
        self.action = self.initial["state"]["proposal"]["actions"][0]
        self.backend = os.environ["VERANTYX_PRECEDENT"]

    def state(self):
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            return get_projection(store, "work")["state"]

    def choose(self, choice, key):
        _, args = parse(["decide", "work", "--point", "api-policy", "--choice", choice,
                         "--reason", "Artificial recorded rationale: " + choice, "--key", key])
        return dispatch(self.root, self.cfg, args, "ja")

    def refresh(self, key):
        result = coordinate(self.root, self.cfg, "work", proposer_adapter=self.root / "vera.json",
                            editor_adapter=self.root / "editor.json", include_paths=["calc.py", "test_calc.py"],
                            key=key, expected_revision=self.state()["revision"], max_repairs=0)
        calls = self.case.harness.fixture.invocations()[-2:]
        staged = stage_candidate(self.root, self.cfg, "work", key=key + "-stage",
                                 expected_revision=result["recorded_revision"])
        return calls, staged

    def denied(self, code, call, *args, **kwargs):
        with self.assertRaises(LedgerError) as error:
            call(*args, **kwargs)
        self.assertEqual(error.exception.code, code)

    def test_both_model_inputs_share_the_exact_effective_choice_reason_and_provenance(self):
        self.choose("preserve", "preserve")
        calls, first = self.refresh("first-refresh")
        self.assertEqual(calls[0]["decision_context"], calls[1]["decision_context"])
        packet = calls[0]["decision_context"]
        row = next(row for row in packet["items"] if row["point"]["id"] == "api-policy")
        self.assertEqual(row["selected_option"], {"id": "preserve", "label": "Preserve the API"})
        self.assertEqual(row["reason"], "Artificial recorded rationale: preserve")
        self.assertEqual(row["status"], "HUMAN_DECIDED")
        self.assertEqual(row["source_refs"], [first["state"]["human_decisions"]["api-policy"]["source_ref"]])
        self.assertFalse(packet["execution_authorized"])
        self.assertEqual(packet["code_conformance"], "UNPROVEN")
        self.assertEqual(packet, first["state"]["handoff_plan"]["decision_context"])
        self.choose("break", "change")
        changed, _ = self.refresh("second-refresh")
        self.assertEqual(changed[0]["decision_context"], changed[1]["decision_context"])
        self.assertNotEqual(packet["sha256"], changed[0]["decision_context"]["sha256"])
        row = next(row for row in changed[1]["decision_context"]["items"] if row["point"]["id"] == "api-policy")
        self.assertEqual(row["selected_option"]["id"], "break")

    def test_resolved_choice_requires_a_fresh_edit_then_the_bounded_execution_works(self):
        self.case.decide(self.action["arguments"]["point_id"], "isolate")
        self.choose("preserve", "preserve")
        self.denied("EDITOR_DECISION_CHANGED", authorize, self.root, self.cfg, "work", self.action["id"], self.backend, "old")
        calls, staged = self.refresh("updated")
        self.assertEqual(len(calls), 2)
        permission = authorize(self.root, self.cfg, "work", staged["state"]["proposal"]["actions"][0]["id"], self.backend, "current")
        result = execute(self.root, self.cfg, "work", permission["lease_id"], self.backend, "execute")
        self.assertEqual(result["execution"]["receipt"]["verification"]["closure"], "BOUNDED")
        self.assertEqual((self.root / "calc.py").read_text(), "def answer():\n    return 1\n")

    def test_an_already_authorized_edit_cannot_survive_a_new_value_choice(self):
        self.case.decide(self.action["arguments"]["point_id"], "isolate")
        self.choose("preserve", "preserve")
        _, staged = self.refresh("updated")
        permission = authorize(self.root, self.cfg, "work", staged["state"]["proposal"]["actions"][0]["id"], self.backend, "permission")
        self.choose("break", "changed")
        self.denied("EDITOR_DECISION_CHANGED", authorize, self.root, self.cfg, "work", self.action["id"], self.backend, "new-permission")
        result = execute(self.root, self.cfg, "work", permission["lease_id"], self.backend, "stale-execute")
        self.assertFalse(result["ok"])
        self.assertEqual(result["execution"]["status"], "INVALIDATED")
        self.assertFalse((self.root / ".verantyx/worktrees").exists())

    def test_pending_values_remain_pending_and_isolation_is_a_separate_gate(self):
        before = snapshot(self.state())
        row = next(row for row in before["items"] if row["point"]["id"] == "api-policy")
        self.assertIsNone(row["selected_option"])
        self.assertEqual(row["source_refs"], [])
        self.case.decide(self.action["arguments"]["point_id"], "isolate")
        self.denied("EDITOR_DECISION_REQUIRED", authorize, self.root, self.cfg, "work", self.action["id"], self.backend, "pending")

    def test_general_proposal_bridge_also_receives_the_recorded_choice(self):
        from verantyx.bridges import _input
        self.choose("preserve", "preserve")
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            request, _ = _input(self.root, store, "work", "ja", [], reuse_assets=True)
        self.assertEqual(request["decision_context"], snapshot(self.state()))
        row = next(row for row in request["decision_context"]["items"] if row["point"]["id"] == "api-policy")
        self.assertEqual(row["selected_option"]["id"], "preserve")

    def test_handoff_event_cannot_invent_a_human_choice_snapshot(self):
        state = self.state()
        forged = snapshot(state)
        forged["items"][0].update(status="HUMAN_DECIDED", selected_option={"id": "break", "label": "Change the API"})
        forged["sha256"] = digest({key: value for key, value in forged.items() if key != "sha256"})
        payload = {"basis_revision": state["revision"], "context_sha256": state["shared_context"]["sha256"],
                   "plan": deepcopy(state["handoff_plan"]["plan"]), "provenance": deepcopy(state["handoff_plan"]["provenance"]),
                   "request_sha256": digest(forged), "decision_context": forged}
        self.denied("SHARED_CONTEXT_INVALID", append, self.root, self.cfg, "work", "HandoffPlanned", payload,
                    key="forged-context", expected_revision=state["revision"])
        self.assertEqual(self.state()["revision"], state["revision"])

    def test_five_languages_show_recorded_choice_and_need_for_new_editor_input(self):
        self.choose("preserve", "preserve")
        view = context_view(self.root, self.cfg, SimpleNamespace(command="shared-context", run_id="work"), "ja")
        self.assertEqual(view["handoff_status"], "EDITOR_DECISION_CHANGED")
        for locale in ("en", "ja", "zh-Hans", "ko", "es"):
            with self.subTest(locale=locale):
                output = io.StringIO()
                with redirect_stdout(output):
                    display(view, locale, "shared-context")
                self.assertIn("Preserve the API", output.getvalue())
                self.assertIn(text(locale, "context.EDITOR_DECISION_CHANGED"), output.getvalue())
                self.assertNotIn(text(locale, "context.MATCHED"), output.getvalue())

    def test_model_receives_the_choice_and_proposes_different_code_after_refresh(self):
        editor = self.root / "editor.py"
        editor.write_text(editor.read_text().replace("print(json.dumps(d", "choice=next(x for x in v['decision_context']['items'] if x['point']['id']=='api-policy')['selected_option']['id']; d['files']['calc.py'] += '# chosen: '+choice+'\\n'; print(json.dumps(d"))
        self.choose("preserve", "preserve")
        _, first = self.refresh("preserved")
        self.choose("break", "break")
        _, second = self.refresh("changed")
        a = first["state"]["editor_attempt"]["document"]["files"]["calc.py"]
        b = second["state"]["editor_attempt"]["document"]["files"]["calc.py"]
        self.assertIn("# chosen: preserve", a)
        self.assertIn("# chosen: break", b)
        self.assertNotEqual(a, b)


class EffectiveRuleContextTests(unittest.TestCase):
    def test_only_current_in_scope_rules_supply_an_effective_selected_option(self):
        from datetime import timedelta
        import test_constitution as rules
        from verantyx.application import iso
        case = rules.Fixture()
        case.setUp()
        self.addCleanup(case.tearDown)
        case.promote()
        state = case.run_task("second")["state"]
        self.assertEqual(state["human_decisions"], {})
        row = snapshot(state)["items"][0]
        self.assertEqual(row["status"], "PRECEDENT_MATCHED")
        self.assertEqual(row["selected_option"]["id"], "isolate")
        self.assertTrue(row["source_refs"])
        self.assertIsNone(row["reason"])
        expired = snapshot(state, iso(case.time + timedelta(days=400)))["items"][0]
        self.assertIsNone(expired["selected_option"])
        self.assertEqual(expired["blocker_reason"], "RULE_ENGINE_CHANGED")
        outside = case.run_task("outside", context={**rules.SCOPE, "component": "other"})["state"]
        self.assertIsNone(snapshot(outside)["items"][0]["selected_option"])
        conflicted = case.command("decide", "second", point_id="separation", choice="shared",
                                  reason="Artificial choice conflicting with the active rule", key="conflict")["state"]
        conflict = snapshot(conflicted)["items"][0]
        self.assertIsNone(conflict["selected_option"])
        self.assertEqual(conflict["blocker_reason"], "RULE_CONFLICT")
