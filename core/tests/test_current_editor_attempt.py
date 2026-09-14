"""A plan event owns its current editor result; earlier attempts remain history.

The adapters are real local protocol fixtures and the comparison uses Cross.
They do not measure live model quality or prove the edited code correct.
"""
from contextlib import redirect_stdout
from copy import deepcopy
import io
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

from rich.console import Console

import test_shared_context as context_fixtures
from verantyx.application import get_projection
from verantyx.assets import project_catalog
from verantyx.commands_context import dispatch, display
from verantyx.coordination import candidate_proposal, coordinate, stage_candidate
from verantyx.domain.codec import digest
from verantyx.domain.effects import editor_binding
from verantyx.domain.events import make_event
from verantyx.errors import LedgerError
from verantyx.i18n import text
from verantyx.kernel.reducer import replay
from verantyx.presentation import render_reply, response_freshness
from verantyx.responses import compose
from verantyx.shared_context import current_editor_attempt
from verantyx.storage.sqlite import EventStore, parse_archive
from verantyx.terminal_ui import ConsoleUI

VALIDATION = Path(__file__).resolve().parents[1] / "validation"
LOCALES = ("ja", "en", "zh-Hans", "ko", "es")


class CurrentEditorAttemptTests(unittest.TestCase):
    def setUp(self):
        self.case = context_fixtures.SharedContextTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.root, self.cfg = self.case.root, self.case.cfg

    def error(self, code, fn, *args, **kwargs):
        with self.assertRaises(LedgerError) as error:
            fn(*args, **kwargs)
        self.assertEqual(error.exception.code, code)

    def state(self):
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            return get_projection(store, "work")["state"]

    def view(self):
        return dispatch(self.root, self.cfg, SimpleNamespace(command="shared-context", run_id="work"), "ja")

    def replan_failure(self, *, same_plan=False, first=None):
        first = first or self.case.workflow()
        mutation = "" if same_plan else "d['interpretations'][0]['meaning']='Connect after reviewing the boundary.'"
        vera, editor = self.case.adapters("raise SystemExit(7)", mutation)
        kwargs = dict(proposer_adapter=vera, editor_adapter=editor, key="failed-replan",
                      expected_revision=first["state"]["revision"], include_paths=["calc.py", "test_calc.py"], max_repairs=0)
        self.error("BRIDGE_PROCESS_FAILED", coordinate, self.root, self.cfg, "work", **kwargs)
        return first["state"], self.state(), kwargs

    def test_transport_failure_invalidates_current_candidate_and_preserves_history(self):
        before, after, _ = self.replan_failure()
        self.assertEqual(len(after["handoff_plans"]), 2)
        self.assertEqual(after["editor_attempts"], before["editor_attempts"])
        self.assertEqual(after["editor_attempts"][0]["plan_ref"], before["handoff_plan"]["source_ref"])
        self.assertIsNone(after["editor_attempt"])
        self.assertIsNone(current_editor_attempt(after))
        self.error("HANDOFF_REPAIR_REQUIRED", candidate_proposal, after)
        self.error("HANDOFF_REPAIR_REQUIRED", stage_candidate, self.root, self.cfg, "work",
                   key="old-candidate", expected_revision=after["revision"])
        self.assertEqual(self.state()["revision"], after["revision"])
        self.assertEqual(after["effects"], {})
        self.assertEqual((self.root / "calc.py").read_text(), "def answer():\n    return 1\n")

    def test_same_document_replan_is_a_distinct_attempt_even_with_old_pointer(self):
        before, after, _ = self.replan_failure(same_plan=True)
        self.assertEqual(before["handoff_plan"]["plan"], after["handoff_plan"]["plan"])
        self.assertNotEqual(before["handoff_plan"]["source_ref"], after["handoff_plan"]["source_ref"])
        self.assertIsNone(current_editor_attempt(after))
        # Hash-only checks accepted this result in v0.6.3. A stale cached pointer
        # must not revive it when the plan was recorded again unchanged.
        after["editor_attempt"] = deepcopy(before["editor_attempt"])
        self.assertIsNone(current_editor_attempt(after))
        self.error("HANDOFF_REPAIR_REQUIRED", candidate_proposal, after)
        self.error("HANDOFF_REPAIR_REQUIRED", editor_binding, after, before["proposal"]["actions"][0])

    def test_failed_retry_does_not_redispatch_or_change_current_plan(self):
        _, after, kwargs = self.replan_failure()
        calls = len(self.case.fixture.invocations())
        self.error("BRIDGE_PROCESS_FAILED", coordinate, self.root, self.cfg, "work", **kwargs)
        self.assertEqual(len(self.case.fixture.invocations()), calls)
        self.assertEqual(self.state(), after)
        self.assertIsNone(self.view()["current_editor_attempt"])

    def test_successful_resend_is_idempotent_and_new_plan_result_becomes_current(self):
        before, failed, _ = self.replan_failure()
        vera, editor = self.case.adapters("d['files']['calc.py'] += '# current candidate\\n'")
        kwargs = dict(proposer_adapter=vera, editor_adapter=editor, key="fresh-result",
                      expected_revision=failed["revision"], include_paths=["calc.py", "test_calc.py"], max_repairs=0)
        first = coordinate(self.root, self.cfg, "work", **kwargs)
        calls = len(self.case.fixture.invocations())
        second = coordinate(self.root, self.cfg, "work", **kwargs)
        self.assertTrue(second["duplicate"])
        self.assertEqual(first["projection_hash"], second["projection_hash"])
        self.assertEqual(len(self.case.fixture.invocations()), calls)
        after = self.state()
        current = current_editor_attempt(after)
        self.assertEqual(current["plan_ref"], after["handoff_plan"]["source_ref"])
        self.assertNotEqual(current["source_ref"], before["editor_attempt"]["source_ref"])
        self.assertEqual(len(after["handoff_plans"]), 3)
        self.assertEqual(len(after["editor_attempts"]), 2)
        self.assertEqual(self.view()["current_editor_attempt"], current)
        self.assertIn("# current candidate", candidate_proposal(after)["actions"][0]["arguments"]["files"]["calc.py"])
        self.assertEqual(after["effects"], {})

    def test_cached_historical_success_does_not_restore_current_pointer(self):
        first = self.case.workflow()
        # A completed invocation returns its original receipt on retransmission.
        # It must not append a result or rewind the live context projection.
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            plan_event = next(e for e in store.events("work") if e["type"] == "HandoffPlanned")
        _, failed, _ = self.replan_failure(first=first)
        # Restore exact adapter content required by the old idempotency intent.
        vera, editor = self.case.adapters()
        from verantyx.adapters.invocation_journal import InvocationJournal
        with InvocationJournal(self.root, "ask", "work") as journal:
            old_key = "ask-editor-" + journal.prefix
        calls = len(self.case.fixture.invocations())
        historical = coordinate(self.root, self.cfg, "work", proposer_adapter=vera, editor_adapter=editor,
                                key=old_key, expected_revision=plan_event["payload"]["basis_revision"],
                                include_paths=["calc.py", "test_calc.py"])
        self.assertTrue(historical["duplicate"])
        self.assertTrue(historical["state"]["historical_assessment"])
        self.assertEqual(historical["state"]["editor_attempt"]["source_ref"], first["state"]["editor_attempt"]["source_ref"])
        self.assertEqual(len(self.case.fixture.invocations()), calls)
        self.assertEqual(self.state(), failed)
        self.assertIsNone(self.view()["current_editor_attempt"])

    def test_repair_history_and_failure_assets_survive_new_plan(self):
        first = self.case.workflow("if not v['repair_feedback']: d['acknowledgements'][-1]['disposition']='FORBIDDEN'")
        before, after, _ = self.replan_failure(first=first)
        self.assertEqual([a["validation"]["status"] for a in after["editor_attempts"]], ["REPAIR_REQUIRED", "MATCHED"])
        self.assertEqual(after["editor_attempts"], before["editor_attempts"])
        # Each attempt belongs to its own frozen plan. A bounded repair now
        # reconsiders the proposer as well, without rewriting older attempts.
        self.assertEqual({a["plan_ref"] for a in after["editor_attempts"]},
                         {p["source_ref"] for p in before["handoff_plans"]})
        self.assertEqual(len(before["handoff_plans"]), 2)
        self.assertNotEqual(after["editor_attempts"][0]["plan_ref"], after["editor_attempts"][1]["plan_ref"])
        self.assertEqual(after["editor_attempts"][-1]["plan_ref"], before["handoff_plan"]["source_ref"])
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            catalog = project_catalog(store, after, "ja")
        self.assertEqual(len([f for f in catalog["failure_cases"] if f["family"] == "HANDOFF"]), 1)
        self.assertIsNone(current_editor_attempt(after))

    def test_current_plan_and_pending_state_are_visible_in_five_languages(self):
        _, after, _ = self.replan_failure()
        view = self.view()
        self.assertEqual(view["current_plan"], after["handoff_plan"])
        self.assertIsNone(view["current_editor_attempt"])
        self.assertEqual(view["editor_attempts"], after["editor_attempts"])
        for locale in LOCALES:
            with self.subTest(locale=locale):
                output = io.StringIO()
                with redirect_stdout(output):
                    display(view, locale, "shared-context")
                rendered = output.getvalue()
                self.assertIn("Connect after reviewing the boundary.", rendered)
                self.assertIn(text(locale, "context.AWAITING_EDITOR"), rendered)
                self.assertIn(text(locale, "context.attempt_history", count=1), rendered)
                self.assertNotIn(text(locale, "context.MATCHED"), rendered)
                ordinary = render_reply(after, locale)
                self.assertIn(text(locale, "context.AWAITING_EDITOR"), ordinary)
                self.assertNotIn(text(locale, "context.MATCHED"), ordinary)

    def test_new_answers_and_rich_display_use_only_current_editor_result(self):
        _, _, kwargs = self.replan_failure()
        for locale in LOCALES:
            with self.subTest(locale=locale):
                state = self.state()
                result = compose(self.root, self.cfg, "work", adapter_path=kwargs["proposer_adapter"],
                                 key="answer-" + locale, expected_revision=state["revision"], locale=locale, reuse_assets=False)
                self.assertNotIn("editor_handoff", self.case.fixture.invocations()[-1])
                self.assertEqual(response_freshness(result["state"], locale), "CURRENT")
                with mock.patch("verantyx.terminal_ui.capable_terminal", return_value=True):
                    ui = ConsoleUI(self.root, self.cfg, locale)
                output = io.StringIO()
                ui.console = Console(file=output, width=400, color_system=None)
                ui.response(result, elapsed=0.1)
                self.assertIn(text(locale, "context.AWAITING_EDITOR"), output.getvalue())
                self.assertNotIn(text(locale, "context.MATCHED"), output.getvalue())

    @unittest.skipUnless(any(VALIDATION.glob("current-attempt-before-*.jsonl")),
                         "optional v0.6.3 compatibility archives are not present")
    def test_v063_archives_replay_without_external_calls_and_keep_old_answers_historical(self):
        files = sorted(VALIDATION.glob("current-attempt-before-*.jsonl"))
        self.assertEqual(len(files), 4)
        for path in files:
            with self.subTest(archive=path.name), mock.patch("subprocess.run", side_effect=AssertionError("replay executed a process")), \
                    mock.patch("verantyx.adapters.command_process.BoundedProcess", side_effect=AssertionError("replay dispatched an adapter")):
                parsed = parse_archive(path.read_bytes())
                state = replay(parsed["events"])
                self.assertIsNone(current_editor_attempt(state))
                self.assertEqual(len(state["editor_attempts"]), 1)
                self.assertEqual(state["editor_attempts"][0]["validation"]["status"], "MATCHED")
                self.assertEqual(state["editor_attempts"][0]["plan_ref"], state["handoff_plans"][0]["source_ref"])
                self.error("HANDOFF_REPAIR_REQUIRED", candidate_proposal, state)
                self.assertEqual(state["assessment"]["actions"][0]["gate"], "DENY")
                self.assertEqual(state["assessment"]["actions"][0]["reason"], "HANDOFF_REPAIR_REQUIRED")
                if "-response" in path.name:
                    self.assertIn("editor_handoff", state["latest_response"]["request_snapshot"])
                    self.assertEqual(response_freshness(state, "ja"), "CONTEXT_CHANGED")
                    rendered = render_reply(state, "ja")
                    self.assertIn(text("ja", "context.AWAITING_EDITOR"), rendered)
                    self.assertNotIn(text("ja", "context.MATCHED"), rendered)

    @unittest.skipUnless((VALIDATION / "current-attempt-before-same-plan-response.jsonl").is_file(),
                         "optional v0.6.3 compatibility archive is not present")
    def test_old_successful_answer_can_be_checked_after_assessment_metadata_changes(self):
        from verantyx.responses import _recorded_request, apply_event
        events = parse_archive((VALIDATION / "current-attempt-before-same-plan-response.jsonl").read_bytes())["events"]
        pos = next(i for i, event in enumerate(events) if event["type"] == "ResponseComposed")
        state = replay(events[:pos])
        self.assertIsNotNone(current_editor_attempt(state))
        # Simulate the new decision-dependency metadata added by the parallel
        # gate repair. It changes the assessment hash even for a successful
        # old handoff, whose recorded request must remain inspectable.
        state["assessment"]["actions"][0].update(decision_dependencies=[], unresolved_decision_dependencies=[],
                                                  dependency_source_ref=state["proposal_ref"])
        before = deepcopy(state)
        request = _recorded_request(events[pos]["payload"], state)
        self.assertEqual(request, events[pos]["payload"]["request_snapshot"])
        self.assertEqual(state, before)
        apply_event(state, events[pos])
        self.assertEqual(state["assessment"], before["assessment"])
        self.assertEqual(state["latest_response"]["context_compatibility"], "V063_HANDOFF_HISTORY")
        self.assertEqual(response_freshness(state, "ja"), "CONTEXT_CHANGED")

    @unittest.skipUnless((VALIDATION / "current-attempt-before-same-plan-response.jsonl").is_file(),
                         "optional v0.6.3 compatibility archive is not present")
    def test_legacy_response_compatibility_rejects_fabricated_history(self):
        events = parse_archive((VALIDATION / "current-attempt-before-same-plan-response.jsonl").read_bytes())["events"]
        pos = max(i for i, event in enumerate(events) if event["type"] == "ResponseComposed")
        original = events[pos]
        for field, value in (("status", "REPAIR_REQUIRED"), ("source_ref", "unrecorded"), ("files", ["unrecorded.py"])):
            with self.subTest(field=field):
                payload = deepcopy(original["payload"])
                payload["request_snapshot"]["editor_handoff"][field] = value
                payload["request_sha256"] = digest(payload["request_snapshot"])
                forged = make_event(original["project_id"], original["stream_id"], original["revision"], original["command_id"],
                                    original["recorded_at"], original["type"], payload, original["event_id"], events[pos - 1])
                self.error("RESPONSE_CONTEXT", replay, [*events[:pos], forged])


if __name__ == "__main__":
    unittest.main()
